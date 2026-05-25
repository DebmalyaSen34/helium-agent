# Lazy setup

```bash
git clone <repo_url>
```

```bash
cd helium-agent
```

```bash
docker compose build
```

> wait for few minutes it might take some time

Get your llm endpoints, url and model.

### Free llm endpoints

1. Go to [OpenRouter](https://openrouter.ai/)
2. Log in or Register
3. Click on your profile at the **top right**
4. Click on `preferences`
5. On the left panel click on `API keys`
6. Create an API key and copy the `key and url`
7. Find a free model in openrouter. Eg. `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
8. Paste in a file `.env` in the `helium-agent` directory these fields:
        

        LLM_API_KEY=key
        LLM_API_URL=url
        LLM_MODEL=nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free


## Running it

```bash
docker run -it --env-file .env jarvis-runtime:latest
```

Enjoy!
