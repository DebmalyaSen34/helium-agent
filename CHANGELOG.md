# Changelog

All notable changes to Helium Agent are listed here.

## [0.2.0] - Unreleased

Helium 0.2 is a rebuild of the agent loop and the terminal UI. It makes coding Helium's default job and adds native tool calling, DeepSeek support, themes and notes. It is also much lighter than before. Playwright and the RAG service are gone, startup no longer calls the model, and every chat request is smaller.

### Performance

Measured on an Apple Silicon Mac with no LLM calls. The "Before" column is the first review of this branch, before these fixes.

| What | Before | After |
| --- | --- | --- |
| Launch to first prompt | ~258 ms, then a paid API request | ~128 ms, no request |
| Importing Helium | 235 ms | 122 ms |
| Memory after import | 55.8 MB | 48.2 MB |
| One redraw of a streamed 60k-character reply | 230 ms | ~1 ms |
| Fixed tokens sent with each chat request | ~3,990 (35 tools) | ~2,610 (20 tools) |
| `@` completion per keystroke, 20,000-file repo | 24 ms | 6 ms |
| `@` suggestions shown, 20,000-file repo | 20,000 | 50 |
| `@` file list rescan | every 2 s | at most every 30 s |
| Installed Python packages | 240 MB, plus 1.6 GB of Playwright browsers | 71 MB |

- **Streaming:** replies no longer re-render from the start on every redraw. Finished Markdown blocks are rendered once and cached, and only the block still being written is redrawn. Before, a long reply took longer to redraw than the gap between redraws, so one CPU core stayed busy and the screen fell behind.
- **Startup:** Helium no longer sends a test chat request before showing the prompt. Complete saved settings are trusted, and a rejected key shows up on the first real request with a hint to run `helium --setup`.
- **Smaller requests:** each mode sends only the tools it uses. The main agent gets 26 tools instead of all 35, and subagents get 16. Alias and rarely used tools (`create_file`, `append_file`, `replace_text`, `patch_file`, `copy_file`, `touch_file`, `stat_file`, `checksum_file`, `diff_text`) are still available to skills that list them. Subagent instructions are only added to the main agent's system prompt.
- **`@` completion:** suggestions are capped at the best 50 matches, with name matches first and then shorter paths. The file list is cached for 30 seconds, but adding or removing something in the top folder still refreshes it straight away. At most 20,000 files are indexed. Suggestions stop once you start typing your question.
- **Lazy web search:** BeautifulSoup and the search code load on the first web search, not at startup.

### Added

- **Native tool calling:** uses the OpenAI-compatible `tools` API. Safe tool calls run in parallel, and Helium falls back to a text `<action>` protocol for models or servers that don't support tools. Tool schemas come from function signatures, and arguments are validated.
- **One agent runner** for the main agent, skills and subagents.
- **Coding by default:** there is no separate coding command. Every request goes to one agent that explores, plans, edits and verifies, like Claude Code, and can still chat, search the web and remember things. The system prompt carries coding guidelines and a project snapshot (git status and file tree) taken once per session, so it stays identical between turns and local servers can reuse their prompt cache. Follow-ups build on the same conversation. File edits ask for approval unless you switch to "accept edits" with shift+tab. `[agent] max_turns` (default 40) replaces `chat_max_turns` and `code_max_turns`. New coding tools:
  - `edit_file`: atomic edits, several at once.
  - `glob_files`.
  - `search_text`: regex search that honours `.gitignore`.
  - Numbered `read_file` output.
  - `git_status`, `git_diff` and `git_log`.
  - `run_tests`, which detects the project's test runner.
- **Non-interactive mode:** `helium -p "<task>"` runs one task and exits. Tools that need approval are denied unless `--accept-edits` or `--yes` allows them. `--json` prints the result, stop reason, token usage and tool counts; `--transcript` saves every message. The exit code is 0 when Helium finishes, 2 at the turn limit, and 1 on an error.
- **Coding benchmark:** `python -m evals.bench.run` runs 20 coding tasks (bug fixes, features, refactors, debugging, performance) in throwaway git repos and grades each with hidden tests. It reports pass rates by category and difficulty, saves each attempt's transcript and diff, and compares against an earlier run with `--compare`. `--check` validates the tasks without a model.
- **Project instructions:** Helium reads a `HELIUM.md` into every prompt, and `/init` writes or updates it.
- **Per-workspace memory and prompt history:** stored in the user data directory, one database per project. The last session is summarised into the next one.
- **Session commands:**
  - `/clear`, `/model [name] [--save]` and `/usage`.
  - `/undo`, which reverts the last file change Helium made.
  - `/notes`, a full-screen notes editor per folder (`/notes <text>` appends a timestamped note).
  - `/theme`.
- **Themes:** 11 built-in themes: `helium`, `dracula`, `nord`, `gruvbox-dark`, `tokyo-night`, `catppuccin-mocha`, `one-dark`, `monokai`, `solarized-dark`, `solarized-light` and `github-light`. User themes can be TOML files. There's a live theme picker, and switching applies immediately to replies, tool lines, code, syntax highlighting and diffs.
- **Code and diff rendering:**
  - Diffs look like a code review: line numbers, syntax colours on every line, tinted added and removed lines, and highlighted changed words.
  - Markdown code blocks are syntax-highlighted.
  - Git diffs the agent reads are shown to you too.
- **DeepSeek support:**
  - `reasoning_content` is sent back on tool calls in thinking mode.
  - The setup wizard has `deepseek`, `openrouter` and `ollama` presets.
  - `DEEPSEEK_API_KEY` is supported.
  - `[llm.extra_params]` passes provider fields such as `reasoning_effort`.
  - Base URLs and Ollama's `/api/chat` are normalised to `/chat/completions`.
- **New terminal UI:**
  - Compact header with an animated helium-4 nucleus logo.
  - Framed prompt with rotating tips.
  - Status bar showing permission mode, model and session tokens.
  - Shift+Tab cycles between "ask before risky tools" and "accept edits".
- **`helium --setup`:** reruns the setup wizard (provider, API key, URL, model).
- **Pages that need JavaScript:** `browse_url` and web search say when a page needs JavaScript to render, instead of returning almost no text without explanation.
- **Opt-in live tests** against the real DeepSeek API: `HELIUM_LIVE_DEEPSEEK=1`.

### Changed

- **`@path/to/file`:** now asks Helium to read that file with `read_file`. Before, it went through the RAG service.
- **Web search:** finds results with DuckDuckGo (or a local SearXNG) and reads pages as plain HTML with requests and BeautifulSoup. No browser is involved.
- **Bash safety:** `execute_bash` checks commands with shell-aware parsing, per-command rules and project-root and sensitive-path checks. It also has a timeout, a working directory, the exit code and an output cap.
- **Ctrl+C:** cancels the running turn. At the prompt it takes two presses to exit.
- **Startup animation:** the fusion intro is opt-in through `assistant.startup_animation`.
- **Docker:** `docker compose` runs a single `helium` container. The image no longer installs Playwright or the RAG requirements.

### Removed

- **Playwright:** the browser fallback for fetching pages, the `use_playwright`, `fallback_only` and `headless` settings, the `USE_PLAYWRIGHT` and `PLAYWRIGHT_HEADLESS` variables, and the setup-wizard question about it.
- **RAG service** (`rag_service/`): the FastAPI service, `requirements-rag.txt`, the `[rag_service]` settings, the `HELIUM_RAG_*` variables and the boot check. Reading PDF, Word and Excel files went with it.
- **Dependencies:** `fastapi`, `uvicorn`, `numpy` and `spacy` are no longer required.
- **Voice mode, unused embedding dependencies and dead code.**

### Fixed

- **spaCy:** the model is never downloaded in the middle of a conversation. If spaCy or its model is missing, memory uses simple keyword matching, and a missing model is reported once with the install command.
- **Streaming:**
  - Streamed replies are no longer duplicated when they're taller than the terminal.
  - Answers that mention `<action>` or `<think>` are no longer cut off.
- **Shell commands:** they no longer inherit the terminal as input, so `cat` and `grep -r` can't block and swallow keystrokes. `tail -f` asks for confirmation.
- **`@` mentions:** plain `@words` (decorators, handles) no longer block a message, and `@file` search skips virtualenvs and trailing punctuation.
- **Web search sources:** they're listed under answers again.
- **Subagent tools:** they never run in parallel, so confirmations can't overlap.
- **Text mode:** a JSON answer isn't mistaken for a broken tool call.
- **Shift+Tab:** no longer interferes with the completion menu.
- **Cleanup:** old session summaries are pruned and undo snapshots are cleaned up at exit.
- **`DEEPSEEK_API_KEY`:** now takes precedence over a key saved for a different provider. An explicit `LLM_API_KEY` still wins.

### Upgrading from 0.1

- **Old settings:** `use_playwright` in a saved `config.toml` or `~/.helium.env` is ignored, and it's dropped the next time settings are saved. The same goes for a `[rag_service]` section in `config/settings.toml`.
- **Reclaiming disk space:** the packages are no longer required, but they stay in an existing environment until you uninstall them:

  ```bash
  pip uninstall -y playwright fastapi uvicorn pydantic pydantic-core uvloop numpy spacy
  rm -rf ~/Library/Caches/ms-playwright
  ```

- **spaCy keyword matching:** to keep it in memory, install spaCy yourself and run `python -m spacy download en_core_web_sm`.
- **Bad saved API key:** Helium no longer checks the key at startup. If it's wrong, the first request fails with a hint, and `helium --setup` fixes it.
