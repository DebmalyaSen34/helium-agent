from dotenv import load_dotenv
import requests
import os

load_dotenv()

def hit_api(payload: dict, is_stream: bool = True):
    try:
        url = os.getenv("LLM_API_URL", "https://openrouter.ai/api/v1/chat/completions")
        if url:
            url = url.strip()
        key = os.getenv("LLM_API_KEY", "")
        if key:
            key = key.strip()
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}"
            },
            json=payload,
            stream=is_stream,
            timeout=(10, 30) if is_stream else None, # 10s read timeout and 30s connect timeout
        )
        return response
    except requests.ConnectTimeout:
        print("Connection timed out while trying to connect to the API.")
        return None
    except requests.ReadTimeout:
        print("Read timed out while waiting for a response from the API.")
        return None
    except Exception as e:
        print(f"Error hitting API: {e}")
        return None