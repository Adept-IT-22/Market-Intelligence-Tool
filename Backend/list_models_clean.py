import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

try:
    print("Listing models...")
    models = client.models.list()
    with open("groq_models_list.txt", "w", encoding="utf-8") as f:
        for m in models.data:
            f.write(f"{m.id}\n")
            print(f"- {m.id}")
except Exception as e:
    print(f"Error: {e}")
