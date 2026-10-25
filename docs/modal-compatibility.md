# Modal compatibility and bounded cost estimate

Status: compatibility analysis only; no Modal authentication, deployment, GPU allocation, or paid endpoint was attempted.

## Compatibility

The starter's optional hosted-model path uses a Modal vLLM server with Python 3.12, `vllm==0.6.6`, a `Qwen/Qwen2.5-7B-Instruct` default, and an A10G label. Its own documentation estimates roughly 2–5 minutes for a small-model cold start and tears the ephemeral app down after the run. Current Modal GPU documentation lists `A10` as the supported name; `A10G` is treated as an old starter alias and must be verified before any deployment.

Qwen 2.5 7B is plausibly within a 24 GB A10-class GPU for a low-concurrency smoke test: fp16 weights alone are roughly 14 GB, leaving limited room for runtime and KV cache. That is a static fit inference, not a measured boot or throughput result. Modal’s current guidance also notes that model initialization, not the base container, can dominate cold-start time.

## Estimate

Checked Modal rates on 2026-10-25:

| GPU | USD/sec | USD/hour | 2 min | 5 min | 10 min |
|---|---:|---:|---:|---:|---:|
| A10 | $0.000306 | $1.1016 | $0.0367 | $0.0918 | $0.1836 |
| A100 40 GB | $0.000583 | $2.0988 | $0.0700 | $0.1749 | $0.3498 |
| H100 SXM5 | $0.001097 | $3.9492 | $0.1316 | $0.3291 | $0.6582 |

These figures exclude CPU and memory charges and are estimates, not measured consumption. A 5-minute A10 startup plus 10 minutes of a small smoke run would be approximately `$0.2754` for GPU seconds alone. The `$5` Modal milestone cap therefore leaves room for a bounded, explicitly approved probe, but no such probe is authorized by this milestone.

Modal documents a default short idle window and a configurable `scaledown_window`; the starter's server sets five minutes. Idle reservation can add cost, so a future one-shot experiment should use the shortest safe lifecycle and verify teardown. The runner in this repository does not import Modal and cannot deploy it accidentally.

Source receipts:

* [Modal pricing](https://modal.com/pricing) — current per-second GPU rates.
* [Modal GPU guide](https://modal.com/docs/guide/gpu) — supported GPU names and model-fit guidance.
* [Modal cold-start guide](https://modal.com/docs/guide/cold-start) — container/model initialization and idle-window behavior.
* Upstream `util/poseidon_compute/modal_serve.py` at the [pinned starter revision](https://github.com/poseidon-research/collusion_hackathon/blob/e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8/util/poseidon_compute/modal_serve.py) — actual starter image, vLLM version, GPU label, and teardown settings.
