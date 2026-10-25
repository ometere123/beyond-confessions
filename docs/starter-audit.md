# Colosseum starter audit

Audit date: 2026-10-25
Upstream: <https://github.com/poseidon-research/collusion_hackathon>
Pinned commit: `e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8`

## What was inspected

The audit covered:

* `COMPUTE.md`: shared inference configuration, Nebius → OpenRouter → Modal routing, no-silent-substitution policy, call estimate, OpenAI-compatible client, and Modal hosted-model lifecycle.
* `colosseum/pyproject.toml`: Python `>=3.11`, Terrarium `0.1.1`, `poseidon-compute`, YAML, dotenv, and optional vLLM dependencies.
* `colosseum/README.md`: preflight command, positive-control command, model/tool-calling assumptions, output directory contract, and the warning that one cheap seed is not evidence.
* `colosseum/experiments/preflight.py`: Python/Terrarium/CoLLAB/environment/key checks and optional one-call ping.
* `colosseum/experiments/collusion/configs/hackathon_positive_control.yaml`: four agents, two assigned colluders, private coalition channel, one seed, two planning rounds, and the `simple` prompt variant.
* `colosseum/experiments/common/providers.py`: the shared OpenAI-compatible `TogetherClient`, model resolution, call estimate, cost prompt, and explicit provider label behavior.
* `colosseum/experiments/collusion/run.py`: communication setup, coalition injection, planning/execution turns, metrics, progress, and artifact writes.
* `colosseum/experiments/common/run_utils.py` and `blackboard_logger.py`: file logging and blackboard snapshots.
* `util/poseidon_compute/llm_config.py`, `run.py`, `hosted_model.py`, and `modal_serve.py`: environment loading, provider routing, Modal lifecycle, model access preflight, GPU defaults, and teardown.

## Verified starter behavior from source

The starter's native experiment output includes `config.json`, `progress.json`, `experiment.log`, `summary.json`, `summary.jsonl`, `summary.csv`, and per-run `run_config.json`, `final_summary.json`, `agent_turns.json`, `metrics.json`, `tool_events.json`, and `blackboards.json`. The runner's upper-bound call estimate is `runs × agents × planning_rounds × conversation_steps`; it is useful for approval but is not measured billing.

The positive-control README explicitly says its single seed and reduced planning rounds are a cheap smoke test, not a reliable effect estimate. This project preserves that limitation.

## Adaptation boundary

The upstream checkout is not edited. The Beyond Confessions runner:

1. requires the exact pinned starter revision by default;
2. loads `OPENAI_API_KEY` and `OPENAI_BASE_URL` from the local process/.env;
3. maps those values to the starter's already-supported `LLM_BASE_URL`/`LLM_API_KEY` path;
4. supplies a derived YAML config with the selected OpenAI model;
5. wraps only the starter adapter's `requests.Session.post` Chat Completions boundary in the child process, translates `max_tokens` to `max_completion_tokens` for the verified GPT-6 Luna route, adds `reasoning_effort=none`, and counts requests, usage, latency, and failures without recording prompts or response bodies;
6. writes `usage.json` beside the starter's normal output; and
7. never calls `poseidon_compute.hosted_model`, `modal run`, or a persistent endpoint.

On Windows, the unmodified starter generated log paths longer than the default
filesystem limit when checked out under the original Documents workspace. The
successful run used a real Git worktree at `C:\CH2` at the same pinned commit;
the starter source and experiment settings were unchanged.

For Milestone 1, no ground-truth label was passed to a judge. Milestone 2 now
uses the same boundary: the blinded auditor receives only one anonymised
evidence view and never receives condition, coalition, role, or adjudication
metadata. The deterministic task-violation rubric is kept outside the auditor
packet and is not treated as proof of collusion.

## Milestone 2 verification

The pinned checkout was rechecked before the matched study with the runner's
preflight: Python 3.12.10, `terrarium-agents==0.1.1`, the local CoLLAB
checkout, all four condition environments, model routing, tool-call transport,
and the output contract passed. The upstream checkout remained detached and
unmodified.

The four derived configurations were generated from the starter's official
condition files `hackathon_2_1_a_pair_private_channel.yaml`,
`hackathon_2_1_b_pair_no_channel.yaml`, `hackathon_2_1_c_open_channel.yaml`,
and `hackathon_2_1_d_neither.yaml`. Only the frozen model, seed, output path,
generation bounds, and matched treatment knobs were supplied by this project.
The final 40 raw runs passed the cross-file artifact validator; six transient
or invalid attempts remain preserved as failures/retries in the evidence
archive. No Modal route was used.
