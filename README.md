# digest-engine

A small, config-driven news digest engine. It fetches RSS sources, summarizes fresh
items with an LLM, and delivers a digest to Telegram. Designed to run on a schedule via
GitHub Actions, but the core is decoupled from CI so it runs equally well locally or in
Docker.

The whole product is driven by a single YAML config. To run a digest for someone else,
copy a config, change a few values, add their secrets — no code changes.

## How it works

```
sources → normalize → select (time window + dedup) → summarize (LLM) → render → deliver
```

Each stage lives in its own module and is independently testable. The three pluggable
extension points use a registry pattern, so adding a variant is "write a class, register
it, reference it from config":

| Extension point | Interface | Selected by | Built-in |
|---|---|---|---|
| Sources | `digest_engine/sources/base.py` | `sources[].type` | `rss` |
| LLM providers | `digest_engine/llm/base.py` | `llm.provider` | `openrouter` |
| Delivery channels | `digest_engine/delivery/base.py` | `delivery.type` | `telegram` |

## Freshness & deduplication

Freshness is handled primarily by a **time window** (`filters.lookback_hours`): only
items published within that window are considered. With a daily cron and a 24h window,
that alone prevents repeats. On top of that, every run does in-run dedup by canonical
URL/title.

For feeds that don't set publish dates or that re-surface old items, there's an optional
persistent layer — set `state.type: json` and the engine remembers delivered item hashes
in `state/seen.json`. The included workflow commits that file back so it carries across
runs. The `StateStore` interface (`digest_engine/state.py`) makes it easy to add SQLite,
Redis, etc. later.

## Configuration

See `configs/torchlab-ai.yml` (live config) and `configs/example.yml` (annotated
template). Secrets are never stored in YAML — config references environment variable
*names* and values are resolved at runtime. YAML strings also support `${ENV_VAR}`
interpolation.

## Running locally

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in your keys
set -a && . ./.env && set +a  # export them into the shell

# Preview without delivering or persisting state:
python scripts/run_digest.py --config configs/torchlab-ai.yml --dry-run

# Real run:
python scripts/run_digest.py --config configs/torchlab-ai.yml
```

## Running in Docker

```bash
docker build -t digest-engine .
docker run --rm --env-file .env digest-engine --config configs/torchlab-ai.yml --dry-run
```

## Running in GitHub Actions

The workflow `.github/workflows/digest.yml` runs daily at 06:00 MSK and supports manual
runs (`workflow_dispatch`) with `config_name` and `dry_run` inputs.

Add these repository secrets (Settings → Secrets and variables → Actions):

- `OPENROUTER_API_KEY` — required
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — required
- `OPENROUTER_REFERER`, `OPENROUTER_TITLE` — optional (OpenRouter attribution)

`TELEGRAM_CHAT_ID` is your chat/channel id. For a channel, add the bot as an admin and
use the `-100...` id; for a personal chat, message the bot and read the id from
`https://api.telegram.org/bot<TOKEN>/getUpdates`.

## Adding a digest for someone else

1. Copy `configs/example.yml` to `configs/<name>.yml` and edit sources/topics/audience.
2. Add their secrets to the repo (or a fork).
3. Run manually with `config_name: <name>`, or add another cron schedule.

## Adding a new LLM provider (example)

```python
# digest_engine/llm/openai.py
from digest_engine.llm.base import LLMProvider, register_provider

@register_provider("openai")
class OpenAIProvider(LLMProvider):
    def chat(self, system: str, user: str) -> str:
        ...
```

Import it in `digest_engine/llm/__init__.py`, then set `llm.provider: openai` and
`llm.api_key_env: OPENAI_API_KEY` in the config.

## Project layout

```
configs/                 YAML configs (one per digest)
digest_engine/
  config.py              pydantic schema + loader
  models.py              domain models passed between stages
  sources/               source registry + RSS adapter
  normalizer.py          HTML cleaning, URL canonicalization
  dedup.py               time window + dedup + caps
  state.py               StateStore interface + json/none backends
  llm/                   provider registry + OpenRouter adapter
  summarizer.py          batched LLM summarization
  render.py              Telegram HTML + markdown rendering
  delivery/              channel registry + Telegram adapter
  pipeline.py            wires the stages together
  cli.py                 command-line entry point
scripts/run_digest.py    runnable wrapper
tests/                   unit + pipeline tests
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```
