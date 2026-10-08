import os
import sys
import json
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY", "")
embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

if not api_key:
    print("ERROR: OPENAI_API_KEY is not set.")
    sys.exit(1)

client = OpenAI(api_key=api_key)

kb_path = os.path.join("backend", "app", "data", "knowledge_base", "xobia_kb_master.json")
if not os.path.exists(kb_path):
    print(f"ERROR: {kb_path} does not exist.")
    sys.exit(1)

with open(kb_path, "r", encoding="utf-8") as f:
    kb_data = json.load(f)

articles = kb_data.get("articles", [])
glossary = kb_data.get("glossary", [])

print(f"Loaded {len(articles)} articles and {len(glossary)} glossary terms.")

documents_to_embed = []

# Prepare Articles (Active and Partially Active only; Excluded articles 25-28 are skipped completely)
for art in articles:
    if art.get("status") == "EXCLUDED":
        continue
    # Prepare rich text representation for semantic embedding
    parts = [
        f"Title: {art.get('title', '')}",
        f"Domain: {art.get('domain', '')}",
        f"Topic: {art.get('intent_name', '').replace('_', ' ')}",
        f"Summary: {art.get('short_answer', '')}",
        f"Detail: {art.get('detail', '')}"
    ]
    utterances = art.get("utterances", [])
    if utterances:
        parts.append("Sample user questions: " + " | ".join(utterances))
    
    text_content = "\n".join(parts)
    documents_to_embed.append({
        "doc_id": f"art_{art['article_number']}",
        "type": "article",
        "article_number": art["article_number"],
        "title": art.get("title", ""),
        "intent_name": art.get("intent_name", ""),
        "domain": art.get("domain", ""),
        "status": art.get("status", "ACTIVE"),
        "scope": art.get("scope", "FULL"),
        "disclaimer_flag": art.get("disclaimer_flag", "NO"),
        "short_answer": art.get("short_answer", ""),
        "detail": art.get("detail", ""),
        "follow_up_prompts": art.get("follow_up_prompts", []),
        "text_for_embedding": text_content
    })

# Prepare Glossary terms
for g in glossary:
    term_text = f"Term: {g.get('term', '')}\nDefinition: {g.get('definition', '')}\nDomain: UAE Real Estate & Mortgage Glossary"
    documents_to_embed.append({
        "doc_id": f"gloss_{g.get('intent_name', '')}",
        "type": "glossary",
        "article_number": None,
        "title": g.get("term", ""),
        "intent_name": g.get("intent_name", ""),
        "domain": "Glossary",
        "status": "ACTIVE",
        "scope": "FULL",
        "disclaimer_flag": "NO",
        "short_answer": g.get("definition", ""),
        "detail": g.get("definition", ""),
        "follow_up_prompts": [],
        "text_for_embedding": term_text
    })

print(f"Total documents to embed: {len(documents_to_embed)}")

# Batch embed via OpenAI text-embedding-3-small
batch_size = 20
embedded_records = []

for i in range(0, len(documents_to_embed), batch_size):
    batch = documents_to_embed[i:i + batch_size]
    texts = [b["text_for_embedding"] for b in batch]
    print(f"Embedding batch {i // batch_size + 1} of {(len(documents_to_embed) + batch_size - 1) // batch_size}...")
    
    response = client.embeddings.create(
        model=embedding_model,
        input=texts
    )
    
    for item, emb_obj in zip(batch, response.data):
        vec = np.array(emb_obj.embedding, dtype=np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        
        record = dict(item)
        del record["text_for_embedding"]
        record["embedding"] = vec.tolist()
        embedded_records.append(record)

out_store = {
    "metadata": {
        "model": embedding_model,
        "dimension": len(embedded_records[0]["embedding"]),
        "total_documents": len(embedded_records),
        "source": "Xobia_KB_v2_FINAL.md"
    },
    "documents": embedded_records
}

out_path_1 = os.path.join("backend", "app", "data", "knowledge_base", "vector_store.json")
out_path_2 = os.path.join("data", "knowledge_base", "vector_store.json")

os.makedirs(os.path.dirname(out_path_1), exist_ok=True)
os.makedirs(os.path.dirname(out_path_2), exist_ok=True)

with open(out_path_1, "w", encoding="utf-8") as f:
    json.dump(out_store, f, ensure_ascii=False)

with open(out_path_2, "w", encoding="utf-8") as f:
    json.dump(out_store, f, ensure_ascii=False)

print(f"SUCCESS: Vector store generated and persisted to {out_path_1} ({len(embedded_records)} vectors).")
