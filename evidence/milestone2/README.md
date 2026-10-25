# Milestone 2 evidence bundle

This directory contains the validated, sanitised outputs of the completed
Milestone 2 matched study. It is derived from the raw output root
`C:\BCM2` after validation and analysis. No API key, `.env` file, request
headers, or credentials are included.

## Contents

* `study_manifest.json` — manifest with machine-local `C:\BCM2` prefixes
  replaced by relative paths;
* `validation.json` — final validator receipt: 40 episodes, 10 per condition,
  160 auditor assessments, no issues;
* `budget_summary.json` — measured token usage, conservative reservation bound,
  and standard-rate estimate;
* `results.json` — data-derived metrics, confusion matrices, bootstrap
  intervals, paired summaries, and false-case index;
* CSV files — assessments, conditions, episode diagnostics, and paired view
  comparisons;
* `figures/` — five generated PNG figures and their manifest;
* `raw_artifacts_20261025.zip` — compressed raw `episodes/`, `analysis/`,
  `budget.json`, and `study_manifest.json` from `C:\BCM2`.

The portable raw archive is 5,381,985 bytes and has SHA-256:

`25cf15f33703c58b1fa0766e19dae4b76b7326887ead2a7aa38ec2797fe23f56`

The complete file checksum list is in `checksums.sha256`. The archive contains
the failed attempts and retry evidence as well as the valid selected episodes;
failed records were not deleted or silently excluded.

## Revalidate without API calls

From the repository root:

```powershell
Expand-Archive evidence\milestone2\raw_artifacts_20261025.zip -DestinationPath C:\BCM2-reproduction
uv sync --locked
uv run python scripts/validate_milestone2.py C:\BCM2-reproduction --expected-per-condition 10
uv run python scripts/analyze_milestone2.py C:\BCM2-reproduction
```

The expected validation status is `pass`. Analysis regenerates the CSV/JSON
summaries and the five figures from the archived episodes; it does not call the
OpenAI API.

## Provenance

* Repository main before Milestone 2: `18a8a44b1f228e593df6f60cea306032506be83d`.
* Frozen protocol commit: `4c25925698f81daae506f546e2abcd51458c8ac2`.
* Artifact-validation repair commit: `fea3586462c0a9c98da9a2c883ee9828b033080e`.
* Starter: Poseidon Research Colosseum
  `e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8`.
* Agent and auditor model: `gpt-6-luna`.

Raw artifacts remain reproducible from the frozen configuration even if the
archive is moved; absolute paths in the committed manifest and completion
markers are sanitised to relative names. The archive was extracted to a fresh
`C:\BCM2-reproduction-portable` root and revalidated successfully without API
calls.
