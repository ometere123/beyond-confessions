# Beyond Confessions

Beyond Confessions is a reproducible engineering foundation for studying whether cross-agent communication, executed actions, and structured behavioural evidence distinguish harmful collusion from innocent coordination.

Milestone 1 prepared the environment, verified a secret-safe OpenAI route,
audited Poseidon Research's Colosseum starter, added exact request/token
accounting, checked Modal feasibility without deploying, and reproduced one
positive-control trial. Milestone 2 has now completed the frozen matched study;
the results remain explicitly limited to observable task-harm labels rather than
a causal claim of realised collusion.

## Current status

Milestone 2 is `COMPLETE_WITH_KNOWN_LIMITATIONS`: 40 matched episodes (10 per
condition), 160 blinded auditor assessments, validated artifacts, preserved
failures, five data-derived figures, and a complete cost ledger are available
in [`docs/milestone2-findings.md`](docs/milestone2-findings.md) and
[`evidence/milestone2/`](evidence/milestone2/). Condition D produced six task
violations and is therefore not a clean behavioural negative control. The
deterministic rubric does not label any episode realised harmful collusion.

## Reproducible setup

Prerequisites: Windows, macOS, or Linux with Git, `uv`, and Python 3.12. The project does not require Docker or a GPU for this milestone.

```powershell
uv sync --locked
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY locally. Never commit .env.
uv run pytest
uv run ruff check .
```

The OpenAI key is read only from `OPENAI_API_KEY` in the process environment or the ignored `.env`. It is never printed, included in a ledger, or committed. Automatic provider retries are disabled in the connectivity probe.

## Bounded OpenAI compatibility probe

The default probe tests tool calling, which is the critical Colosseum capability:

```powershell
uv run beyond-confessions connectivity --mode tool --ledger artifacts/openai_probe.json
```

To test text transport, tool calling, and structured output in three small requests:

```powershell
uv run beyond-confessions connectivity --mode all --ledger artifacts/openai_probe.json
```

The probe enforces the initial `$0.50` cap configured in `.env.example`; the actual cost is calculated from returned token usage when the model has a checked price.

## Official starter checkout

The starter is kept outside this repository's source tree so its attribution and history remain intact. Pin the milestone to the audited commit:

```powershell
git clone https://github.com/poseidon-research/collusion_hackathon.git third_party/collusion_hackathon
git -C third_party/collusion_hackathon checkout e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8
```

`third_party/` is ignored. The exact upstream revision, inspected files, and changes made by this project are recorded in [docs/starter-audit.md](docs/starter-audit.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

On Windows, keep both the starter checkout and its log root short enough for
the starter's generated paths. The verified setup used a Git worktree at
`C:\CH2` for the pinned commit and a result root at `C:\BCM1`.

Run the starter checks first:

```powershell
uv run python scripts/run_colosseum_positive_control.py `
  --starter-root C:\CH2 `
  --out-dir C:\BCM1 `
  --preflight
```

Once preflight passes, run one bounded positive-control trial through the direct OpenAI endpoint:

```powershell
uv run python scripts/run_colosseum_positive_control.py `
  --starter-root C:\CH2 `
  --model gpt-6-luna `
  --out-dir C:\BCM1
```

The runner uses the starter's Terrarium/CoLLAB environment and output contract, but overrides its OpenAI-compatible endpoint to `OPENAI_BASE_URL`, adapts the pinned adapter's `max_tokens` payload for GPT-6 Luna, records actual HTTP Chat Completions attempts in `usage.json`, refuses an unpriced model, caps calls and spend, and never invokes Modal. Use `--allow-unpinned` only after recording and reviewing a new starter revision.

Validate the generated result directory:

```powershell
uv run beyond-confessions validate-results C:\BCM1\<timestamp>
```

The verified control is archived at
[`evidence/positive_control_20261025-174632.zip`](evidence/positive_control_20261025-174632.zip)
with a SHA-256 checksum and extraction instructions in
[`evidence/README.md`](evidence/README.md). The failed Windows path attempts
are documented in [`evidence/failed_attempts.md`](evidence/failed_attempts.md).

## Milestone 2 controlled study

The frozen protocol compares:

* A: designated pair with a private channel;
* B: designated pair without a private channel;
* C: no coalition instruction with an all-agent open channel; and
* D: no coalition instruction and no extra channel.

All four evidence views—messages, actions, raw combined, and structured
claim/action/outcome links—are generated from each underlying episode and sent
to the same blinded `gpt-6-luna` auditor schema. The full target completed at a
measured standard-rate estimate of `$0.25685258`, below the `$2.00` Milestone 2
cap; Modal consumption was `$0.00`.

To validate the committed evidence without making API calls:

```powershell
Expand-Archive evidence\milestone2\raw_artifacts_20261025.zip -DestinationPath C:\BCM2-reproduction
uv run python scripts/validate_milestone2.py C:\BCM2-reproduction --expected-per-condition 10
uv run python scripts/analyze_milestone2.py C:\BCM2-reproduction
```

To reproduce the study from scratch, follow the commands in
[`docs/milestone2-protocol.md`](docs/milestone2-protocol.md) with the pinned
starter at `C:\CH2` and a new output root. The ignored `.env` must contain
`OPENAI_API_KEY`; never print or commit it. Do not begin another sweep using D
as a clean negative class without revising and preregistering the adjudication
design.

## Modal decision

Modal is an optional future route for open-weight/off-catalog inference or parallel compute. This milestone contains only a calculator and compatibility assessment:

```powershell
uv run beyond-confessions modal-estimate --gpu A10 --active-seconds 300
```

No paid Modal endpoint is deployed. See [docs/modal-compatibility.md](docs/modal-compatibility.md).

## Research integrity boundary

The positive control and matched study establish that the harness can produce
structured observations, blinded evidence views, and reproducible auditor
outputs. They do not establish that a coalition formed or that a detector
proved collusion. Do not infer collusion from promise-breaking, private
messages, reward advantage, or task violations alone; keep coalition assignment,
realized actions, communication, rewards, task harm, and auditor evidence
separate. The next research step is independent adjudication and a cleaner
negative-control task, not an unqualified larger sweep.
