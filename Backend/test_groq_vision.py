from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

try:
    print("Testing llama-3.2-90b-vision-preview...")
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Hello",
            }
        ],
        model="llama-3.2-90b-vision-preview",
    )
    print("Success:", chat_completion.choices[0].message.content)
except Exception as e:
    print("Failed 90b:", e)

try:
    print("Testing llama-3.2-11b-vision-preview...")
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": "Hello",
            }
        ],
        model="llama-3.2-11b-vision-preview",
    )
    print("Success 11b:", chat_completion.choices[0].message.content)
except Exception as e:
    print("Failed 11b:", e)
