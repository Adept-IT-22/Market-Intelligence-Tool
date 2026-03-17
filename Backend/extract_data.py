import json
import sys

# Search for all Adept company-related documents
search_terms = ["Company 1-Pager", "Company Profile", "Adept Technologies"]

dump_path = r"d:\Projects\ProjectsWork\MIT\Backend\qdrant_dump.json"
output_path = r"d:\Projects\ProjectsWork\MIT\Backend\extracted_adept_info.txt"

target_ids = [
    "fef0c0d3-9406-46fc-9089-ad3ae1bef5aa",
    "8cfa7ba8-6e5c-42c0-b869-936204bce350",
]

try:
    with open(dump_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    results = []
    for item in data:
        item_id = item.get('id', '')
        payload = item.get('payload', {})
        source = payload.get('source', '')
        title = payload.get('title', '')
        text = payload.get('text', '')
        
        # Match by ID or by source/title containing key terms
        if item_id in target_ids or \
           any(term.lower() in (source + title).lower() for term in ["Company 1-Pager", "2501 - Adept Company Profile", "2025 - Adept Technologies Company Profile"]):
            results.append({
                'id': item_id,
                'source': source,
                'title': title,
                'text': text[:3000]  # cap text length for readability
            })
    
    with open(output_path, 'w', encoding='utf-8') as out:
        for r in results:
            out.write(f"=== ID: {r['id']} ===\n")
            out.write(f"Source: {r['source']}\n")
            out.write(f"Title: {r['title']}\n")
            out.write(f"Text:\n{r['text']}\n")
            out.write("=" * 60 + "\n\n")
    
    print(f"Done. Found {len(results)} matching items. Output written to: {output_path}")
            
except Exception as e:
    print(f"Error: {e}")
