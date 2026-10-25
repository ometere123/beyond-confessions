# Beyond Confessions — Engineering Milestone 1 report

Date: 2026-10-25
Repository: `ometere123/beyond-confessions`
Scope: reproducible foundation only; no full sweep and no numerical research conclusion.

## Verified

* The target repository was initialized on `main` from an empty GitHub repository.
* The official Poseidon starter was inspected at commit `e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8`.
* Colosseum’s preflight, OpenAI-compatible provider adapter, positive-control config, routing, cost prompt, output artifacts, and Modal lifecycle were traced.
* A Python 3.12/`uv` project definition, ignored secret path, tests, artifact validator, and cost ledger were added.
* The direct OpenAI probe and Colosseum runner refuse missing/unpriced configuration and do not print credentials.
* Modal was assessed from current documentation and the starter source; no paid GPU action was attempted.
* The target environment passed its automated suite on Windows with Python 3.12.10, `uv` 0.11.8, `openai` 2.54.0, `pytest` 8.4.2, `ruff` 0.17.2, `PyYAML` 6.0.3, and `python-dotenv` 1.2.4.
* The pinned starter environment resolved 224 packages and installed 117 packages, including `terrarium-agents==0.1.1` and the local `poseidon-compute`; its preflight passed Python, imports, checkout, and environment loading, then stopped only because no inference key was configured.

## Pending live verification

| Check | Status | Evidence needed |
|---|---|---|
| OpenAI text transport | NOT_RUN until key is supplied | `artifacts/openai_probe.json` |
| OpenAI tool calling | NOT_RUN until key is supplied | probe ledger and response usage |
| OpenAI structured outputs | NOT_RUN until key is supplied | `--mode structured` ledger |
| Colosseum preflight | PARTIAL: pinned checkout/deps and local checks pass; inference-key check fails | preflight output |
| Positive-control run | NOT_RUN until preflight and key pass | timestamped Colosseum root + `usage.json` |
| Modal GPU boot/inference | NOT_RUN by design | requires explicit approval after cost/compatibility review |

## Model decision

`gpt-6-luna` is the least expensive current candidate found in the checked OpenAI catalog at `$0.10/M` input and `$0.50/M` output, and its documentation lists function calling and structured outputs. Chat Completions function calling requires `reasoning_effort=none`, so the first probe must verify the exact integration. `gpt-4o-mini` remains the explicit lower-risk compatibility fallback for the starter’s historical path, but its official page is marked deprecated.

## Actual consumption

At the time this report was authored, the process environment did not contain `OPENAI_API_KEY`; no OpenAI request, Modal request, or full experimental run was performed. This section must be updated from `usage.json` and provider billing after a live run. Do not fill it with estimates and label them actual.

## Blockers and uncertainties

* A live key is required to verify the selected model and the direct endpoint.
* The starter’s normal call estimate is an upper bound. The new OpenAI boundary ledger is required to establish actual successful/failed request counts and token usage.
* The current Modal GPU name differs from the starter’s `A10G` label; deployment must not proceed until the selected Modal SDK accepts the chosen name and the vLLM image is compatible.
* A single positive-control seed cannot establish a general effect or distinguish coordination from harmful collusion.

## Recommended next experiment

Run exactly one bounded positive-control trial after the probe, validate all artifacts, inspect the usage ledger, and preserve failures. Then run the four matched conditions for Track 2.2 with a small pre-registered seed set before adding a Track 2.3 auditor comparison.
