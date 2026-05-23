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
            {"role": "user", "content": "What is the capital of France?"}
        ],
        "stream": False,
        "stream_options": {
            "include_usage": True
        },
        "stop": [
            "<end_of_turn>",
            "<start_of_turn>",
            "User:",
            "Current User:",
            "</start_of_turn>",
            "</end_of_turn>",
        ]
    }
    
    response = hit_api(payload, is_stream=False)
    if response and response.status_code == 200:
        print("API call successful!")
        print(response.json())
    else:
        print(f"API call failed with status code: {response.status_code if response else 'No response'}")