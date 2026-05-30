# digest-engine

A small, config-driven news digest engine. It fetches RSS sources, summarizes fresh
items with an LLM, and delivers a digest to Telegram. It runs as a Dockerized job on a
schedule (host cron) alongside a self-hosted RSSHub instance, and runs equally well
locally for testing.

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
in `state/seen.json`. In Docker the `./state` directory is mounted as a volume, so that
file persists across runs on the host. The `StateStore` interface
(`digest_engine/state.py`) makes it easy to add SQLite, Redis, etc. later.

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

Note: the Telegram sources resolve through RSSHub. Without Docker you need a local
RSSHub on `http://localhost:1200` (the config's default), otherwise those sources are
skipped. The Docker workflow below starts RSSHub for you — that's the recommended path.

## Running in Docker (recommended)

The stack has two parts (see `docker-compose.yml`):

- **rsshub** — a self-hosted [RSSHub](https://docs.rsshub.app) instance on port `1200`
  that turns Telegram channels into RSS feeds. It replaces the public `rsshub.app`
  instance, which is rate-limited and returns `403`.
- **digest** — the one-shot job. It's behind the `job` profile, so it does **not**
  start with `docker compose up`; you run it on demand.

```bash
cp .env.example .env            # fill in OPENROUTER / TELEGRAM secrets

docker compose up -d rsshub     # start RSSHub (stays running)

# Preview without delivering:
docker compose run --rm digest --config configs/torchlab-ai.yml --dry-run

# Real run (delivers to Telegram, archives to ./digests):
docker compose run --rm digest --config configs/torchlab-ai.yml
```

The digest container reaches RSSHub over the internal network via
`RSSHUB_BASE_URL=http://rsshub:1200` (injected by compose). To eyeball a feed directly,
RSSHub is also exposed on the host: `http://localhost:1200/telegram/channel/ai_newz`.

## Deploying to a VPS

1. Install Docker Engine + the Compose plugin, then clone the repo (e.g. to
   `/opt/news_digets`).
2. Create `.env` from `.env.example` and fill in the secrets.
3. Start RSSHub: `docker compose up -d rsshub`.
4. Smoke-test once: `docker compose run --rm digest --config configs/torchlab-ai.yml --dry-run`.
5. Schedule the daily run with host cron (`crontab -e`) — 06:00 MSK = 03:00 UTC:

   ```cron
   0 3 * * *  /opt/news_digets/scripts/cron-digest.sh >> /var/log/news-digest.log 2>&1
   ```

   `scripts/cron-digest.sh` ensures RSSHub is up and runs one digest, then exits. Pass a
   config name as the first argument to run a different digest
   (e.g. `cron-digest.sh my-friend`).

`TELEGRAM_CHAT_ID` is your chat/channel id. For a channel, add the bot as an admin and
use the `-100...` id; for a personal chat, message the bot and read the id from
`https://api.telegram.org/bot<TOKEN>/getUpdates`.

## Adding a digest for someone else

1. Copy `configs/example.yml` to `configs/<name>.yml` and edit sources/topics/audience.
2. Make sure the secrets it references exist in `.env`.
3. Run it: `docker compose run --rm digest --config configs/<name>.yml`, and add a cron
   line for it (the script takes the config name as an argument).

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
