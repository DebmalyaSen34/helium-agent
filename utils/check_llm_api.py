from __future__ import annotations
import requests
from config.runtime_config import load_llm_runtime_config

def hit_api(
    payload: dict,
    is_stream: bool = True,
    *,
    api_url: str | None = None,
    api_key: str | None = None,
):
    try:
        runtime_config = None
        if api_url is None or api_key is None:
            runtime_config = load_llm_runtime_config()
        url = (api_url or (runtime_config.api_url if runtime_config else None) or "https://openrouter.ai/api/v1/chat/completions").strip()
        key = (api_key or (runtime_config.api_key if runtime_config else None) or "").strip()
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

if __name__ == "__main__":
    payload = {
        "model": "mimo-v2.5-pro",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, how are you?"}
        ],
        "stream": False
    }
    response = hit_api(payload)
    print(response)
    if response:
        print(response.json())
        print("API is working!")
    else:
        print("API is not working.")
