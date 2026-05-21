from dotenv import load_dotenv
import requests
import os

load_dotenv()

def hit_api(payload: dict, is_stream: bool = True):
    try:
        response = requests.post(
            os.getenv("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions"),
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY', '')}"
            },
            json=payload,
            stream=is_stream,
        )
        return response
    except Exception as e:
        print(f"Error hitting API: {e}")
        return None