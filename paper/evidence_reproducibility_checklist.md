# Evidence and reproducibility checklist

Status date: 2026-10-25  
Archive: `evidence/milestone2/raw_artifacts_20261025.zip`  
Archive SHA-256: `25cf15f33703c58b1fa0766e19dae4b76b7326887ead2a7aa38ec2797fe23f56`

| Requirement | Status | Evidence |
|---|---|---|
| Pinned Poseidon starter retained | PASS | `e6fb1308dae9cf97ae42aec1c5f7889d9e2291e8` |
| Frozen protocol retained | PASS | `docs/milestone2-protocol.md` |
| Raw outcomes unchanged | PASS | Preserved archive and checksums |
| Four conditions represented | PASS | `configs/milestone2_conditions.yaml`, archive manifest |
| 40 completed episodes | PASS | Independent verification receipt |
| 10 episodes per condition | PASS | Independent verification receipt |
| 160 auditor assessments | PASS | Independent verification receipt |
| Four evidence views | PASS | `src/beyond_confessions/evidence.py` and archive |
| No privileged metadata in auditor evidence | PASS | Independent evidence-key audit |
| Results recalculated without API calls | PASS | `scripts/verify_milestone3.py`, `api_requests_made: 0` |
| Confusion matrices and derived metrics reconciled | PASS | `evidence/milestone3/verification_report.json` |
| Bootstrap intervals reconciled | PASS | 1,000 episode-level resamples in receipt |
| Paired comparisons reconciled | PASS | 40 episode-level matched rows per view comparison |
| Threshold sensitivity reconciled | PASS | 0.50, 0.60, and 0.75 in receipt |
| Representative cases trace to exact evidence IDs | PASS | `evidence/milestone3/case_studies.json` |
| Failed attempts retained | PASS | Raw archive manifest and `docs/milestone2-findings.md` |
| Cost ledger preserved | PASS | 1,416 records; `$0.25685258` estimate; Modal `$0.00` |
| Final figures checksumed | PASS | `evidence/milestone3/checksums.sha256` |
| Final PDF checksumed | PASS | `evidence/milestone3/checksums.sha256` |
| Secrets excluded | PASS | Ignored `.env`; repository/history scans |
| Independent reproduction from fresh extraction | PASS | M2 validator and analysis passed on portable extraction |
| Official template transfer | REVIEW | Google Docs copy URL requires user-authenticated review |
| Author and affiliation | REVIEW | Placeholders intentionally remain in source and PDF |

## No-API verification commands

```powershell
uv sync --locked
uv run python scripts/verify_milestone3.py
uv run python scripts/extract_case_studies.py
uv run python scripts/generate_milestone3_figures.py
uv run python scripts/check_submission_package.py
uv run pytest -q
uv run ruff check src scripts tests
```

For archive-only validation, extract the committed archive to a fresh
directory and run `scripts/validate_milestone2.py` with
`--expected-per-condition 10`. No command in this checklist requires an API
key.
