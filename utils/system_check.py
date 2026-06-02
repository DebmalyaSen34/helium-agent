import requests
from config.runtime_config import LlmRuntimeConfig, load_llm_runtime_config
from utils.check_llm_api import hit_api


def check_llm_api(config: LlmRuntimeConfig | None = None):
    runtime_config = config or load_llm_runtime_config()

    api_key = runtime_config.api_key.strip() if runtime_config.api_key else None
    if not api_key:
        print("LLM_API_KEY is not set in runtime configuration.")
        return False

    api_url = runtime_config.api_url.strip() if runtime_config.api_url else None
    if not api_url:
        print("LLM_API_URL is not set in runtime configuration.")
        return False

    llm_model = runtime_config.model.strip() if runtime_config.model else None
    if not llm_model:
        print("LLM_MODEL is not set in runtime configuration.")
        return False

    try:
        response = hit_api(
            {
                "model": llm_model,
                "messages": [{"role": "user", "content": "Hi!"}],
                "max_tokens": 1,
                "stream": False,
            },
            is_stream=False,
            api_url=api_url,
            api_key=api_key,
        )
        if response is None:
            return False
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
