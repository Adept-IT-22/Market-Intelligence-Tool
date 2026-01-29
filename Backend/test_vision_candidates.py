from groq import Groq
import os
import base64
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Create a tiny 1x1 black pixel image to test (Base64)
# This is a valid PNG
tiny_image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

models_to_test = [
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "groq/compound",
    "openai/gpt-oss-20b"
]

for model in models_to_test:
    print(f"Testing {model} with image...")
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is this?"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{tiny_image}",
                            },
                        },
                    ],
                }
            ],
            model=model,
        )
        print(f"SUCCESS: {model} accepted image.")
        print(f"Response: {chat_completion.choices[0].message.content}")
        # If one works, we are good.
        break 
    except Exception as e:
        print(f"FAILED: {model} - {e}")
