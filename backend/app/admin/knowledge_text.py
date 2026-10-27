"""Turning documents and web pages into knowledge-base entries (PRD FR-18, FR-24), and screening the text first.

Uploaded files and fetched pages are untrusted. Sentences that read like instructions to an AI are removed before
anything reaches the knowledge base, and the editor sees how many were removed."""
import csv
import io
import re
import zipfile
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

MAX_FILE_BYTES = 8 * 1024 * 1024
# A .docx is a zip: a small file can unpack to gigabytes. Its contents are measured before anything is opened.
MAX_UNPACKED_BYTES = 60 * 1024 * 1024
MAX_ENTRIES = 200
CHUNK_CHARS = 1600

_INJECTION = re.compile(
    r"(?i)\b(ignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|messages|rules)"
    r"|disregard (all |any )?(the )?(previous|prior|above|earlier|your) (instructions|rules)"
    r"|forget (all |your )?(previous |prior )?instructions"
    r"|(reveal|print|show|repeat) (your |the )?(system prompt|hidden instructions|instructions above)"
    r"|you are now (a|an|in) |new instructions:|system prompt|developer mode|jailbreak"
    r"|act as (a|an) (?!advisor)|pretend (to be|you are)|override (your |the )?(rules|safety|instructions))")


class IngestError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def find_injection(text: str) -> Optional[str]:
    match = _INJECTION.search(text or "")
    return match.group(0) if match else None


def screen(text: str) -> Tuple[str, int]:
    """Removes sentences that read like instructions to an AI; returns the clean text and how many were removed."""
    removed = 0
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", text or ""):
        if find_injection(sentence):
            removed += 1
        elif sentence.strip():
            kept.append(sentence.strip())
    return " ".join(kept), removed


def _first_sentences(text: str, limit: int = 320) -> str:
    out = ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + len(sentence) > limit:
            break
        out = f"{out} {sentence}".strip()
    return out[:limit].rstrip() if out else text[:limit]


def to_entries(sections: List[Tuple[str, str]], fallback_title: str, source: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    """(heading, text) sections → entry proposals of a readable size. Returns proposals and removed-sentence count."""
    entries: List[Dict[str, Any]] = []
    removed_total = 0
    for heading, text in sections:
        clean, removed = screen(" ".join(text.split()))
        removed_total += removed
        if len(clean) < 40:
            continue
        parts, current = [], ""
        for sentence in re.split(r"(?<=[.!?])\s+", clean):
            if current and len(current) + len(sentence) > CHUNK_CHARS:
                parts.append(current)
                current = ""
            current = f"{current} {sentence}".strip()
        if current:
            parts.append(current)
        base = (heading or fallback_title).strip()[:160]
        for i, part in enumerate(parts):
            title = base if len(parts) == 1 else f"{base} ({i + 1} of {len(parts)})"
            entries.append({"type": "article", "title": title, "short_answer": _first_sentences(part), "detail": part,
                            "tags": [], "source": source})
        if len(entries) >= MAX_ENTRIES:
            break
    return entries[:MAX_ENTRIES], removed_total


# ---- Files ----

def _csv(raw: bytes, name: str) -> Tuple[List[Dict[str, Any]], int]:
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    fields = {(f or "").strip().lower(): f for f in reader.fieldnames or []}
    title_col = fields.get("title") or fields.get("question")
    answer_col = fields.get("answer") or fields.get("short_answer")
    if not title_col or not answer_col:
        raise IngestError("csv_columns", "The CSV needs a “title” (or “question”) column and an “answer” column. "
                                         "Optional: “detail”, “tags”, “type”.")
    entries, removed = [], 0
    for row in reader:
        title, _ = screen(row.get(title_col) or "")
        answer, r1 = screen(row.get(answer_col) or "")
        detail, r2 = screen(row.get(fields.get("detail", ""), "") or "")
        removed += r1 + r2
        if not title or not answer:
            continue
        kind = (row.get(fields.get("type", ""), "") or "").strip().lower()
        tags = [t.strip() for t in re.split(r"[,;|]", row.get(fields.get("tags", ""), "") or "") if t.strip()]
        entries.append({"type": "glossary" if kind == "glossary" else "article", "title": title, "short_answer": answer,
                        "detail": detail or answer, "tags": tags, "source": {"kind": "upload", "file": name}})
        if len(entries) >= MAX_ENTRIES:
            break
    return entries, removed


def _pdf(raw: bytes, name: str) -> Tuple[List[Dict[str, Any]], int]:
    from pypdf import PdfReader
    try:
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise IngestError("pdf_locked", "This PDF is password-protected. Upload an unlocked copy.")
        pages = [(page.extract_text() or "") for page in reader.pages[:300]]
    except IngestError:
        raise
    except Exception:
        raise IngestError("unreadable", "This PDF could not be read. Try saving it again as PDF, or upload a Word file.")
    text = "\n".join(pages)
    if len(text.strip()) < 40:
        raise IngestError("no_text", "No text was found in this PDF. Scanned pages (images) cannot be read; upload a text PDF or Word file.")
    sections = [(None, block) for block in re.split(r"\n\s*\n", text) if block.strip()] or [(None, text)]
    # Merge short blocks so entries are not single lines.
    merged: List[Tuple[Optional[str], str]] = []
    for _, block in sections:
        if merged and len(merged[-1][1]) < CHUNK_CHARS // 2:
            merged[-1] = (None, f"{merged[-1][1]} {block}")
        else:
            merged.append((None, block))
    return to_entries(merged, name.rsplit(".", 1)[0], {"kind": "upload", "file": name})


def _docx(raw: bytes, name: str) -> Tuple[List[Dict[str, Any]], int]:
    import docx
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as package:
            unpacked = sum(info.file_size for info in package.infolist())
    except (zipfile.BadZipFile, ValueError):
        raise IngestError("unreadable", "This Word file could not be read. Save it as .docx and try again.")
    if unpacked > MAX_UNPACKED_BYTES:
        raise IngestError("too_large", "This Word file is too large once opened. Split it into smaller files.")
    try:
        document = docx.Document(io.BytesIO(raw))
    except Exception:
        raise IngestError("unreadable", "This Word file could not be read. Save it as .docx and try again.")
    sections: List[Tuple[Optional[str], str]] = []
    heading, buffer = None, []
    for p in document.paragraphs:
        style = (p.style.name if p.style is not None else "") or ""
        if style.lower().startswith(("heading", "title")) and p.text.strip():
            if buffer:
                sections.append((heading, " ".join(buffer)))
            heading, buffer = p.text.strip(), []
        elif p.text.strip():
            buffer.append(p.text.strip())
    if buffer:
        sections.append((heading, " ".join(buffer)))
    for table in document.tables:
        rows = [" | ".join(c.text.strip() for c in row.cells) for row in table.rows]
        sections.append((heading, ". ".join(r for r in rows if r.strip(" |"))))
    if not sections:
        raise IngestError("no_text", "No text was found in this Word file.")
    return to_entries(sections, name.rsplit(".", 1)[0], {"kind": "upload", "file": name})


def extract_file(name: str, raw: bytes) -> Dict[str, Any]:
    """Entry proposals from an uploaded PDF, DOCX or CSV. Nothing is saved; the editor reviews them first."""
    if len(raw) > MAX_FILE_BYTES:
        raise IngestError("too_large", "Files can be up to 8 MB.")
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    readers = {"pdf": _pdf, "docx": _docx, "csv": _csv}
    if ext not in readers:
        raise IngestError("file_type", "Upload a PDF, Word (.docx) or CSV file.")
    if ext == "pdf" and not raw.startswith(b"%PDF"):
        raise IngestError("file_type", "This file is not a PDF.")
    if ext == "docx" and not raw.startswith(b"PK"):
        raise IngestError("file_type", "This file is not a Word .docx file.")
    entries, removed = readers[ext](raw, name)
    if not entries:
        raise IngestError("no_text", "No usable text was found in this file.")
    return {"entries": entries, "removed": removed, "truncated": len(entries) >= MAX_ENTRIES}


# ---- Web pages ----

_SKIP = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe", "template", "aside", "button"}
_HEADINGS = {"h1", "h2", "h3"}
_BLOCKS = {"p", "li", "div", "section", "article", "tr", "td", "th", "dd", "dt", "h4", "h5", "h6", "blockquote"}
_VOID = {"br", "img", "meta", "link", "input", "hr", "source", "wbr", "area", "base", "col", "embed", "track"}


class _PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.sections = "", []
        self._skip, self._in_title, self._in_heading = 0, False, False
        self._heading, self._buffer, self._heading_text = None, [], []

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if tag == "br" and not self._skip:
                self._buffer.append("\n")
            return
        hidden = any(k == "hidden" or (k == "aria-hidden" and v == "true") or
                     (k == "style" and v and re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", v)) for k, v in attrs)
        if self._skip or tag in _SKIP or hidden:
            self._skip += 1  # everything inside a skipped element is skipped, including hidden text
            return
        if tag == "title":
            self._in_title = True
        elif tag in _HEADINGS:
            self._flush()
            self._in_heading, self._heading_text = True, []
        elif tag in _BLOCKS:
            self._buffer.append("\n")

    def handle_endtag(self, tag):
        if tag in _VOID:
            return
        if self._skip:
            self._skip -= 1
            return
        if tag == "title":
            self._in_title = False
        elif tag in _HEADINGS and self._in_heading:
            self._in_heading = False
            self._heading = " ".join("".join(self._heading_text).split())[:160] or None

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        elif self._in_heading:
            self._heading_text.append(data)
        else:
            self._buffer.append(data)

    def _flush(self):
        text = " ".join("".join(self._buffer).split())
        if text:
            self.sections.append((self._heading, text))
        self._buffer = []

    def result(self) -> Tuple[str, List[Tuple[Optional[str], str]]]:
        self._flush()
        return " ".join(self.title.split())[:200], self.sections


def page_entries(html: str, url: str) -> Dict[str, Any]:
    parser = _PageText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        raise IngestError("unreadable", "This page could not be read.")
    title, sections = parser.result()
    entries, removed = to_entries(sections, title or url, {"kind": "web", "url": url})
    if not entries:
        raise IngestError("no_text", "No readable text was found on this page.")
    return {"title": title or url, "entries": entries, "removed": removed}
