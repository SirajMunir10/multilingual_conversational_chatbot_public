import os
import re
import json

def parse_kb_markdown(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Split articles
    # Each article starts with **Article <num> [–—-] <Title>**
    article_pattern = re.compile(
        r'\*\*Article\s+(\d+)\s+[–—-]\s+(.*?)\*\*(.*?)(?=\*\*Article|\*\*Domain 11|\*\*Domain 12|\*\*Domain 13|\*\*Domain 13\*{0,4}A\*{0,4}|\*\*Compliance|$)',
        re.DOTALL
    )

    matches = article_pattern.findall(text)
    articles = []

    for num_str, title_raw, body in matches:
        num = int(num_str)
        title = title_raw.strip()

        # Parse table fields
        rows = re.findall(r'\|\s*\*\*([^*|]+?)\*\*\s*\|\s*([^|]+?)\s*\|', body)
        field_dict = {}
        for k, v in rows:
            clean_k = k.strip().lower()
            clean_v = v.strip()
            # Normalize keys
            if "intent" in clean_k:
                field_dict["intent_name"] = clean_v
            elif "domain" in clean_k:
                field_dict["domain"] = clean_v
            elif "utterance" in clean_k:
                field_dict["utterances_raw"] = clean_v
            elif "short answer" in clean_k:
                field_dict["short_answer"] = clean_v
            elif "detail" in clean_k or "conversation flow" in clean_k:
                field_dict["detail"] = clean_v
            elif "follow-up" in clean_k:
                field_dict["follow_up_raw"] = clean_v
            elif "disclaimer" in clean_k:
                field_dict["disclaimer_flag"] = "YES" if "YES" in clean_v.upper() else "NO"
            elif "escalation" in clean_k:
                field_dict["escalation_trigger"] = clean_v
            elif "owner" in clean_k:
                field_dict["content_owner"] = clean_v
            elif "reviewed" in clean_k:
                field_dict["last_reviewed"] = clean_v
            elif "expiry" in clean_k:
                field_dict["expiry_date"] = clean_v
            elif "metadata" in clean_k:
                field_dict["metadata_tags"] = clean_v

        # Determine activation status & scope per Phase 5 boundary
        if 1 <= num <= 8:
            status = "ACTIVE"
            scope = "FULL"
        elif 9 <= num <= 12:
            status = "PARTIALLY_ACTIVE"
            scope = "EDUCATIONAL_ONLY"
        elif 13 <= num <= 24:
            status = "ACTIVE"
            scope = "FULL"
        elif 25 <= num <= 28:
            status = "EXCLUDED"
            scope = "DO_NOT_IMPLEMENT"
        else:
            status = "ACTIVE"
            scope = "FULL"

        # Split utterances into clean list
        raw_utt = field_dict.get("utterances_raw", "")
        # Utterances are usually separated by newline, '?', or questions
        if raw_utt:
            # Split by lines or question marks or commas if on single line
            lines = [u.strip() for u in raw_utt.replace("\r", "").split("\n") if u.strip()]
            if len(lines) <= 2 and "?" in raw_utt:
                # Might be space or question mark separated
                parts = re.split(r'\?\s*', raw_utt)
                utterances = [p.strip() + "?" for p in parts if p.strip()]
            else:
                utterances = lines
        else:
            utterances = []

        # Split follow-up prompts
        raw_fu = field_dict.get("follow_up_raw", "")
        follow_ups = [re.sub(r'^[→\s\-\*]+', '', fu).strip() for fu in raw_fu.split("→") if fu.strip()]

        article_obj = {
            "article_number": num,
            "title": title,
            "intent_name": field_dict.get("intent_name", f"article_{num}_intent"),
            "domain": field_dict.get("domain", "General"),
            "status": status,
            "scope": scope,
            "short_answer": field_dict.get("short_answer", ""),
            "detail": field_dict.get("detail", ""),
            "utterances": utterances,
            "follow_up_prompts": follow_ups,
            "disclaimer_flag": field_dict.get("disclaimer_flag", "NO"),
            "escalation_trigger": field_dict.get("escalation_trigger", ""),
            "content_owner": field_dict.get("content_owner", "XOTO Knowledge Team"),
            "last_reviewed": field_dict.get("last_reviewed", "23/03/2026"),
            "expiry_date": field_dict.get("expiry_date", "Review every 6 months"),
            "metadata_tags": field_dict.get("metadata_tags", "")
        }
        articles.append(article_obj)

    # Parse Glossary (Domain 12)
    glossary_match = re.search(r'\*\*Domain 12\s+[–—-]\s+UAE Real Estate Glossary\*\*(.*?)(?=\*\*Domain 13|\*\*Compliance|$)', text, re.DOTALL)
    glossary_terms = []
    if glossary_match:
        glossary_body = glossary_match.group(1)
        term_rows = re.findall(r'\|\s*\*\*([^*|]+?)\*\*\s*\|\s*([^|]+?)\s*\|', glossary_body)
        for term, definition in term_rows:
            t = term.strip()
            d = definition.strip()
            if t.lower() in ["term", "field"]:
                continue
            slug = re.sub(r'[^a-z0-9]+', '_', t.lower()).strip('_')
            glossary_terms.append({
                "term": t,
                "intent_name": f"define_term_{slug}",
                "domain": "Glossary",
                "definition": d,
                "status": "ACTIVE",
                "scope": "FULL"
            })

    # Standard disclaimer
    standard_disclaimer = (
        "This information is for general guidance only and does not constitute legal or financial advice. "
        "Please consult a licensed property professional for your specific emirate. "
        "Fees, laws, and regulations are subject to change — verify with your emirate land authority: "
        "Dubai: DLD/RERA (dubailand.gov.ae) · Abu Dhabi: ADREC · Sharjah: SRERD · RAK: RAK RLRE · Ajman: AjmanRE · Fujairah/UAQ: local municipality."
    )

    # Master KB payload
    master_kb = {
        "metadata": {
            "title": "XOBIA Conversational Knowledge Base",
            "version": "v2.0_FINAL",
            "source_document": "Xobia_KB_v2_FINAL.md",
            "total_articles": len(articles),
            "total_glossary_terms": len(glossary_terms),
            "standard_legal_disclaimer": standard_disclaimer
        },
        "articles": sorted(articles, key=lambda x: x["article_number"]),
        "glossary": glossary_terms
    }

    return master_kb

if __name__ == "__main__":
    src_file = "Xobia_KB_v2_FINAL.md"
    kb_data = parse_kb_markdown(src_file)

    out_dir = os.path.join("backend", "app", "data", "knowledge_base")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "xobia_kb_master.json")

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(kb_data, f, indent=2, ensure_ascii=False)

    print(f"Successfully ingested {kb_data['metadata']['total_articles']} articles and {kb_data['metadata']['total_glossary_terms']} glossary terms.")
    print(f"Saved master KB to: {out_file}")
