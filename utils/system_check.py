import os
import requests
from dotenv import load_dotenv

load_dotenv()


def check_llm_api():

    api_key = os.getenv("LLM_API_KEY", None)
    if api_key:
        api_key = api_key.strip()

    if not api_key:
        print("LLM_API_KEY is not set in environment variables.")
        return False

    api_url = os.getenv("LLM_API_URL", None)
    if api_url:
        api_url = api_url.strip()

    if not api_url:
        print("LLM_API_URL is not set in environment variables."    )
        return False

    llm_model = os.getenv("LLM_MODEL", None)
    if llm_model:
        llm_model = llm_model.strip()

    if not llm_model:
        print("LLM_MODEL is not set in environment variables.")
        return False

    try:
        response = requests.post(api_url, headers={"Authorization": f"Bearer {api_key}"}, json={
            "model": llm_model,
            "messages": [{"role": "user", "content": "Hi!"}],
            "max_tokens": 1
        })
        return response.status_code == 200
    except Exception as e:
        print(f"Error while checking LLM API: {e}")
        return False

def check_tools():
    from tools.registry import AVAILABLE_TOOLS

    #NOTE For simplicity, we just check if the tools are registered correctly.
    return list(AVAILABLE_TOOLS.keys())

def check_internet_connectivity():
    try:
        response = requests.get("https://www.google.com", timeout=5)
        return response.status_code == 200
    except Exception as e:
        print(f"Error while checking internet connectivity: {e}")
        return False

def check_memory():
    #NOTE Placeholder for memory check, can be expanded to check actual memory usage or limits.
    return True

def check_rag():
    #NOTE Placeholder for RAG check, can be expanded to check actual RAG system status.
    return True