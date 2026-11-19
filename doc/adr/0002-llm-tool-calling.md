# ADR-0002: LLM tool calling through a provider-neutral interface

- **Status:** Accepted (spike result, synthetic data)
- **Date:** 2026-11-19
- **Related:** spec §6.6, §6.7, §1.2 (F-3), D-16, D-17, X-02
- **Evidence:** [spikes/llm-tool-calling](../../spikes/llm-tool-calling/)

## Context

The platform needs a model that reliably calls typed tools and returns schema-valid output, reached through one provider-neutral interface (D-16). The Anthropic API key has no credit yet, so this spike used local inference on the existing Ollama server.

Test: a synthetic customer specification for a hopper. The model must return the hopper input set by calling one tool whose parameters are a Pydantic schema (value, exact source quote, missing flag per field, plus open questions). The document mixes units (one length in metres) and deliberately does **not** state the plate thickness.

## Setup

- Server: `ecsserver` (192.168.10.41), Ollama 0.11.2, CPU inference. Its two Quadro K6000 GPUs (Kepler) are not supported by current Ollama.
- Model: `qwen3:30b-a3b` (mixture-of-experts, about 3B active parameters; Apache-2.0). Generation speed about 12 tokens/s on CPU.
- Interface: OpenAI-compatible chat completions with `tools`, via the `openai` Python client; temperature 0.

## Results (3 runs)

| Check | Result |
|:---|:---|
| Tool called | 3/3 |
| Output valid against the Pydantic schema | 3/3 |
| All values correct, including 6.0 m → 6000 mm | 3/3 |
| Missing plate thickness flagged, **not invented** | 3/3 |
| Missing value raised as an open question | 3/3 |
| Source quotes found verbatim in the document | 3/3 |
| Time per run | 272–288 s (about 3,400–3,800 tokens, mostly model "thinking") |

## Decision

- The platform calls models only through the OpenAI-compatible interface, configured by `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY`. Switching to Claude (Anthropic's OpenAI-compatible endpoint) or a company-approved EU provider is a configuration change.
- Every model output is validated against a Pydantic schema, and source quotes are checked against the document in code. The model's own claims are never trusted without these checks.
- `qwen3:30b-a3b` on `ecsserver` is the **development model** for synthetic data while no cloud credit is available.
- Development use of the local model is limited to tests that tolerate about 5 minutes per call. It is not suitable for interactive use or multi-step agent work at this speed.

## Consequences and open points

- **X-02 is answered for local development only.** The prototype's extraction targets (F-3) must be measured with the strongest approved model on real documents. Rerun this spike against Claude when the Anthropic account has credit, and compare.
- Speed: most of the time is the model's reasoning. Disabling thinking for simple extractions, or a GPU server, would reduce it greatly. This should be measured before choosing a production setup.
- The test document is short and clean. Real documents (scanned PDFs, tables, conflicting statements) are the actual test, in Phase 1.
- The Ollama server has no authentication and is reachable from the local network. Acceptable for synthetic development data only.
