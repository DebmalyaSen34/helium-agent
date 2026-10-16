<img src="assets/Helium-agent-logo.png" width="1080" height="480" alt="Helium Agent Logo"/>

# Helium Agent

## Demo

**[Watch the demo video →](https://youtu.be/JUzYe-BmOa0)**

Helium is a lightweight local AI agent that does everything your everyday agent does but without the massive bill and with your own customization. You can run any LLM be it local or cloud inside Helium. But to have the total experience of freedom I would suggest to integrate a local LLM either using ollama, llama.cpp or any inference technology of your choice.

Helium is still developing and more features are added as you read this. I would really love for you to contribute to this and make a part of Helium your own.

> [!TIP]
> If you directly want to try go to [usage](#usage) section.

## What It Can Do

- **Answer everyday questions:** Just like any other agent it can repsond to any mundane queries you might have. It won't judge you.
- **Tool calling:** Helium uses native OpenAI-compatible tool calling (several tools per turn, in parallel when they are read-only), and falls back to a text protocol for models or servers that don't support tools.
- **Coding**: Coding is what Helium does by default. Describe a task and it explores the project, plans, edits files with precise multi-edits, runs your tests, and reports what changed. `/undo` reverts its last file change.
- **Project instructions:** Put a `HELIUM.md` in your project (or let `/init` write one) and Helium follows it in every conversation.
- **Deep Research:** For queries that include an `in-depth` knowledge and information retrieval Helium will take help of its research tool to provide with most accurate repsonse with proper citations.
- **Web Search:** It searches with DuckDuckGo and reads the pages it finds as plain HTML. No browser is needed, so pages that only render with JavaScript may return little text.
- **File questions:** Mention a file with `@path/to/file` and Helium reads it to answer.
- **Bash execution:** Helium can perform `safe` bash operations in its terminal.
- **Long-term memory:** Facts and preferences are stored in SQLite, one database per project, and Helium picks up where the last session in that project left off.
- **Streaming:** Answers stream into the terminal as they are generated, with a line for each tool Helium uses.

## Prerequisites

Helium is optimized for **macOS on Apple Silicon** but I have tested it across platforms so you shouldn't face any problems but if you do please raise `issue`.

You will need:

- Python 3.10+
- Any OpenAI-compatible chat completions endpoint: a local server (llama.cpp, Ollama, LM Studio, vLLM) or a hosted API (OpenRouter and others).

Default service URLs are configured in [`config/settings.py`](config/settings.py) and can be overridden in [`config/settings.toml`](config/settings.toml).

## Usage

Helium is packaged to `pypi` so you can just download it and use it directly.

Just install it using `pip`:

```Bash
pip install helium-agent
```

Now, go to the directory where you want Helium to work and just call it:

```bash
helium .
```

For more commands type `/help` in the chat.

### Commands

| Command | What it does |
| --- | --- |
| `/help` | Show the help guide. |
| `/deep-research <task>` | Multi-source research report with citations. |
| `/init` | Inspect the project and write a `HELIUM.md` with project instructions. |
| `/undo` | Revert the last file change Helium made (shell-command changes are not covered). |
| `/model [name] [--save]` | Show the model, or switch it for this session (`--save` keeps it). |
| `/usage` | Token and tool usage for this session. |
| `/clear` | Clear the conversation (memories and files are kept). |
| `/skills` | List, create, or remove skills. |
| `/notes [text]` | Open a full-screen notes editor for this folder (Ctrl+S or Esc saves, Ctrl+C discards), or append a quick timestamped note. |
| `/theme [name]` | Browse themes with a live preview (↑/↓, enter to pick), switch by name, or create your own. |
| `/exit` | End the session (`exit`, `quit`, and `stop` work too). |
| `@path/to/file <question>` | Ask about a file; Helium reads it to answer. |

### Themes

Helium ships with popular themes: `helium` (default), `dracula`, `nord`, `gruvbox-dark`, `tokyo-night`, `catppuccin-mocha`, `one-dark`, `monokai`, `solarized-dark`, and, for light terminals, `solarized-light` and `github-light`. A theme colours the prompt, replies, tool lines, code blocks, syntax highlighting, and diffs.

```text
/theme                      browse themes with ↑/↓ and a live preview; enter picks, esc keeps yours
/theme list                 list themes with colour swatches
/theme dracula              switch (and remember it for next time)
/theme preview nord         see a sample without switching
/theme create mine from nord   start your own theme
```

`/theme create` writes a TOML file with every colour filled in from the base theme. Edit it, then run `/theme mine` to load it (run it again after each edit). Lines you delete are inherited from `base`, and diff tints and the code-block background are mixed from your colours unless you set them:

```toml
base = "nord"
dark = true

[colors]
accent = "#ff79c6"
warning = "#f1fa8c"

[syntax]
style = "nord"                # any Pygments style
keyword = "bold #ff79c6"      # then refine individual tokens
comment = "italic #6272a4"
```

`HELIUM_THEME=<name>` overrides the saved choice for one run. Pick a theme that matches your terminal's background; Helium doesn't repaint the background itself.

When Helium asks to run a risky tool, answer `y`, `n`, or `a` to allow that tool (or that exact shell command) for the rest of the session. `helium . --nuclear` skips all confirmations.

### Non-interactive mode

`helium -p "<task>"` runs one task without the interactive UI, prints the answer, and exits, which is handy for scripts and CI:

```bash
helium . -p "explain what main.py does"                    # read-only: risky tools are denied
helium . -p "fix the failing parser test" --accept-edits   # allow file edits
helium . -p "upgrade the lint config and run it" --yes     # allow everything, shell included
helium . -p "add type hints to utils/" --yes --json        # JSON: result, stop reason, tokens, tools
```

Nothing is asked during a `-p` run, so tools that need approval are denied unless `--accept-edits` or `--yes` allows them. Progress and diffs go to stderr (`--verbose` adds a line per tool call) and only the answer goes to stdout. `--transcript FILE` saves every message, and `--model` and `--max-turns` override the config for that run. The exit code is 0 when Helium finishes, 2 when it hits the turn limit, and 1 on an error.

### Project instructions (HELIUM.md)

Helium reads `HELIUM.md` (or `.helium/HELIUM.md`) from the project root and adds it to every prompt, the same way you would brief a new teammate: build and test commands, layout, conventions, and gotchas. Run `/init` to have Helium draft one.

### Tool-calling mode

By default (`tool_mode = "auto"` in [`config/settings.toml`](config/settings.toml)) Helium sends tool schemas using the OpenAI `tools` API. If the endpoint rejects them, Helium switches to its text `<action>` protocol for that model automatically. Set `tool_mode = "text"` or `"native"` to force one.

## Docker

> [!NOTE]
> Use this if you just want to chat without worrying the technical complexities but make sure to have you `env` configured accordingly.

You can build and run the entire terminal application using:

```bash
docker compose up --build
```

You might need to wait for a bit. So, go have a coffee while it is building.

This will run the image:

```bash
docker compose run --rm --service-ports helium
```

The API container is configured to reach host services through `host.docker.internal`. Keep llama.cpp instance running on the host, then update [`docker-compose.yml`](docker-compose.yml) if your ports differ.

## Dev Installation

> [!NOTE]
> Use this only if you want to run it manually otherwise go to [Docker](#docker) section.

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd helium-agent
   ```

2. Create and activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

3. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Local Services

> [!NOTE]
> You can either use llama.cpp or any LLM provider API.

### Start llama.cpp

Run a compatible instruction-tuned GGUF model on port `3000`:

```bash
./llama-server -m /path/to/your/model.gguf -c 4096 --port 3000
```

Helium expects an OpenAI-compatible chat completions endpoint:

```text
http://127.0.0.1:3000/v1/chat/completions
```

For Ollama use `http://localhost:11434/v1/chat/completions` (not the native `/api/chat` endpoint).

### Use DeepSeek

Run `helium`, pick `deepseek` in the setup wizard, and paste your key from the [DeepSeek platform](https://platform.deepseek.com/api_keys). The wizard fills in `https://api.deepseek.com/chat/completions` and the `deepseek-flash` model. Switch to `deepseek-v4-pro` any time with `/model deepseek-v4-pro --save`.

Or configure it with environment variables (a base URL is fine):

```bash
export LLM_API_URL=https://api.deepseek.com
export LLM_MODEL=deepseek-flash
export DEEPSEEK_API_KEY=sk-...   # or LLM_API_KEY
```

DeepSeek runs in thinking mode by default. Helium keeps the model's reasoning hidden but sends it back with tool-call requests, as the DeepSeek API requires. To change how hard it thinks, set it in [`config/settings.toml`](config/settings.toml):

```toml
[llm.extra_params]
reasoning_effort = "high"   # none | low | high | max
```

### Use LLM API

Run `helium` and follow the setup wizard. The API key, URL, and model are saved to `config.toml` in your user Helium config directory, readable only by your user (`chmod 600`). Run `helium --setup` to change them later.

You can still use environment variables for CI, Docker, or temporary overrides:

```text
LLM_API_KEY=your-llm-api-key
LLM_API_URL=your-llm-url
LLM_MODEL=your-model
```

If you previously used `~/.helium.env`, Helium can import it into the config file during setup. The legacy file is left untouched, so remove it yourself after confirming the import worked.

## Run The Assistant

1. Confirm the LLM service is running.
2. Confirm your web services are running if you want better results.
3. Start Helium:

   ```bash
   python main.py
   ```

4. Wait for:

Animation to load and welcome message to be shown.

5. Type your query and enjoy Helium.

Example requests:

```text
What is the latest news on AI?
Remember that I prefer concise responses.
Create a file named hello.txt that says hi.
Open Safari.
Compare India and China GDP in 2025.
Why is the Indian Rupee falling recently?
Give me a report on the latest AI regulation changes in the EU.
```

File question examples:

```text
@README.md what does this project do?
@main.py explain how a turn is handled
```

## Testing

Run the test suite from the repository root:

```bash
uv run pytest tests -q --ignore=tests/test_eval_graders.py --ignore=tests/test_eval_runner.py --ignore=tests/test_eval_schema.py
```

The tests never call a real LLM endpoint and keep memory and history in a temporary directory.

The coding benchmark runs Helium on 20 tasks in throwaway repos and grades them with hidden tests. It calls your configured model, so it is not part of the test suite:

```bash
uv run python -m evals.bench.run            # see evals/bench/README.md for options
uv run python -m evals.bench.run --check    # validate the tasks themselves, no model needed
```

Opt-in live checks against the real DeepSeek API (a few small `deepseek-flash` requests, key read from `DEEPSEEK_API_KEY` or `.env`):

```bash
HELIUM_LIVE_DEEPSEEK=1 uv run pytest tests/live -q
```


