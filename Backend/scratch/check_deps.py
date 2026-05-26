import importlib.util
import sys

requirements = [
    "flask", "flask_cors", "dotenv", "httpx", "jwt", "bcrypt", "requests", 
    "psycopg2", "redis", "rq", "pydantic", "ratelimit", "qdrant_client", 
    "sentence_transformers", "google.auth", "google.generativeai", "groq", 
    "pandas", "pypdf", "docx", "pptx", "bs4", "Pillow", "openpyxl", 
    "xlsxwriter", "docxtpl", "jinja2"
]

missing = []
for req in requirements:
    # Some packages have different import names
    import_name = req
    if req == "dotenv": import_name = "dotenv"
    if req == "jwt": import_name = "jwt"
    if req == "psycopg2": import_name = "psycopg2"
    if req == "sentence_transformers": import_name = "sentence_transformers"
    if req == "google.auth": import_name = "google.auth"
    if req == "google.generativeai": import_name = "google.generativeai"
    if req == "docx": import_name = "docx"
    if req == "pptx": import_name = "pptx"
    if req == "bs4": import_name = "bs4"
    if req == "Pillow": import_name = "PIL"
    
    spec = importlib.util.find_spec(import_name)
    if spec is None:
        missing.append(req)

if missing:
    print(f"MISSING: {', '.join(missing)}")
else:
    print("ALL_INSTALLED")
