from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

try:
    models = client.models.list()
    for m in models.data:
        print(m.id)
except Exception as e:
    print(e)
