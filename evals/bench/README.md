# Helium coding benchmark

Twenty small but realistic coding tasks: bug fixes, features, refactors, debugging from a vague report or a traceback, and one performance fix. Each runs Helium headless in a fresh git repo and grades the result with tests the agent never sees. It is the number to watch when you change prompts, tools, or context handling, or compare models.

## Running it

```bash
# all 20 tasks once, with the model from your Helium config
uv run python -m evals.bench.run

# another model, 3 attempts per task (models are noisy; one run per task is a smoke test)
uv run python -m evals.bench.run --model qwen3-coder:30b --runs 3

# a few tasks, two attempts at a time
uv run python -m evals.bench.run --tasks pagination,lru,stale --jobs 2

# compare against an earlier run
uv run python -m evals.bench.run --compare evals/bench/results/<earlier>/summary.json

# benchmark the installed release instead of this checkout
uv run python -m evals.bench.run --helium-cmd helium
```

Every attempt runs with all tools allowed (`helium -p --yes`) in a temporary copy of the task. Keep `--jobs 1` for a local model that serves one request at a time.

Results go to `evals/bench/results/<time>-<model>/` (git-ignored):

| File | What it holds |
| --- | --- |
| `summary.md` | Pass rate overall, by category and difficulty, plus one row per attempt with the failure reason |
| `summary.json` | The same numbers, for `--compare` and scripts |
| `results.jsonl` | One line per attempt, written as each finishes |
| `attempts/<task>__<run>/` | `transcript.json` (every message), `agent.log` (tool calls and diffs), `diff.patch`, `hidden_tests.log`, `report.json` |

When a task fails, read its `diff.patch` and `hidden_tests.log` first, then the transcript.

## The tasks

| Task | Category | Difficulty | What it checks |
| --- | --- | --- | --- |
| 01-pagination-off-by-one | bugfix | easy | Two off-by-one bugs from a user report |
| 02-mutable-default | bugfix | easy | Shared mutable defaults (both of them) |
| 03-duration-parser | feature | medium | Parsing to a precise spec with error cases |
| 04-cli-reverse-flag | feature | easy | Small argparse change keeping tie order |
| 05-lru-cache | feature | medium | Implementing a class from its docstring |
| 06-rename-function | refactor | medium | Rename across code, tests, and docs |
| 07-failing-tests | debug | medium | "Tests fail, fix it": three bugs, tests are protected |
| 08-config-not-applied | bugfix | medium | Tracing a symptom across modules |
| 09-slugify | bugfix | easy | Unicode and edge cases |
| 10-slow-duplicates | performance | medium | O(n²) to O(n) without changing output |
| 11-traceback-crash | debug | medium | Fixing from a pasted traceback, running a script |
| 12-signup-validation | feature | medium | Many rules with exact messages and order |
| 13-keyword-only-args | refactor | medium | Signature change plus every caller |
| 14-swallowed-errors | bugfix | medium | Exception chaining across two modules |
| 15-text-wrap | feature | medium | Algorithm with edge cases |
| 16-order-state-machine | feature | medium | Implementing a transition table |
| 17-stale-cache | bugfix | hard | Cache invalidation while keeping cache hits |
| 18-cli-subcommand | feature | hard | New subcommand, option, stderr, exit code |
| 19-json-round-trip | bugfix | hard | Datetimes, Decimals, and sets through JSON |
| 20-dotenv-parser | bugfix | hard | Quoting and comment rules from examples |

## Adding a task

```
tasks/<id>/
  task.yaml    # id, category, difficulty, prompt; optional protected, timeout_s, test_command
  repo/        # the starting project the agent sees (may include its own tests/)
  tests/       # hidden tests, copied in as .bench_hidden/ only after the agent finishes
  solution/    # files laid over repo/ to make a reference solution
```

Write the prompt the way a user would, not a list of the hidden assertions. `protected` lists files the agent must not change (the attempt fails if it does). Then run:

```bash
uv run python -m evals.bench.run --check
```

`--check` needs no model. It confirms the hidden tests fail on the starting repo, pass with the reference solution, that the solution passes the repo's own tests, and that it leaves protected files alone.

## Reading the numbers

- Twenty tasks is small: one task is 5 points. Use `--runs 3` or more before trusting a difference under about 10 points.
- `stop_reason` shows how an attempt ended: `final` (the agent finished), `max_turns`, `timeout`, or `error`. Many `max_turns` usually means looping; many `final` failures mean the agent stopped early or didn't verify its work.
- Tokens and tool calls per attempt are in the summary. A change that keeps the pass rate but cuts tokens is still a win, especially on local models.
