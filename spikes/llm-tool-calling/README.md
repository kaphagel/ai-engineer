# Spike: LLM tool calling with schema-validated output

Throw-away code for Phase 0 (spec §25). Results and decisions: [ADR-0002](../../doc/adr/0002-llm-tool-calling.md).

Synthetic data only.

## Run against the local Ollama server

```bash
cd spikes/llm-tool-calling
docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -e UV_CACHE_DIR=/tmp/uv -v "$PWD":/work -w /work \
  -e LLM_BASE_URL=http://192.168.10.41:11434/v1 -e LLM_MODEL=qwen3:30b-a3b -e SPIKE_RUNS=3 \
  ghcr.io/astral-sh/uv:python3.12-bookworm-slim uv run spike_llm.py
```

Inside the Dev Container, `uv run spike_llm.py` with the same environment variables is enough.

## Run against Claude (when the account has credit)

Uses Anthropic's OpenAI-compatible endpoint. The key is read from `.env` and never printed:

```bash
set -a; . ../../.env; set +a
docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -e UV_CACHE_DIR=/tmp/uv -v "$PWD":/work -w /work \
  -e LLM_BASE_URL=https://api.anthropic.com/v1/ -e LLM_MODEL=claude-sonnet-5-5 -e LLM_API_KEY="$ANTHROPIC_API_KEY" \
  ghcr.io/astral-sh/uv:python3.12-bookworm-slim uv run spike_llm.py
```

Results are written to `out/` (git-ignored).
