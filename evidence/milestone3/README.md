# Milestone 3 final research package

This directory contains no new inference output. It contains independent
verification receipts and data-derived figures built from the preserved
Milestone 2 archive.

## Contents

* `verification_report.json` - no-API reconstruction of 40 episodes, 160
  assessments, metrics, bootstrap intervals, paired comparisons, conditions,
  evidence-key checks, and committed-result comparisons;
* `case_studies.json` - four exact anonymised case selections with messages,
  actions, outcomes, and auditor values;
* `figures/` - four print-ready figures and `figure_manifest.json`;
* `submission_qa.json` - PDF, manuscript, figure, link, and security checks;
* `checksums.sha256` - SHA-256 hashes for final paper and evidence outputs.

## Reproduce without API calls

From the repository root:

```powershell
uv sync --locked
uv run python scripts/verify_milestone3.py
uv run python scripts/extract_case_studies.py
uv run python scripts/generate_milestone3_figures.py
uv run python scripts/check_submission_package.py
uv run python scripts/write_milestone3_checksums.py
```

The raw study archive remains the source of truth:

`evidence/milestone2/raw_artifacts_20261025.zip`

SHA-256:

`25cf15f33703c58b1fa0766e19dae4b76b7326887ead2a7aa38ec2797fe23f56`

Milestone 3 did not alter that archive, make OpenAI requests, deploy Modal, or
submit the study. The scientific interpretation and submission status are
documented in `docs/milestone3-scientific-verification.md` and
`paper/submission_checklist.md`.
