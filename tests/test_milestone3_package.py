"""No-API regression checks for the final Milestone 3 package."""

from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def test_independent_verification_receipt_is_clean() -> None:
    receipt = json.loads(
        (ROOT / "evidence/milestone3/verification_report.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == "pass"
    assert receipt["api_requests_made"] == 0
    assert receipt["dataset"]["completed_episode_count"] == 40
    assert receipt["dataset"]["assessment_count"] == 160
    assert receipt["comparisons_to_committed_results"]["mismatch_count"] == 0


def test_case_study_selection_is_complete_and_anonymised() -> None:
    cases = json.loads(
        (ROOT / "evidence/milestone3/case_studies.json").read_text(encoding="utf-8")
    )
    assert len(cases) == 4
    assert len({case["case_id"] for case in cases}) == 4
    assert all(case["case_id"].startswith("case-") for case in cases)
    assert all(case["selected_message_refs"] for case in cases)
    assert all(case["selected_action_refs"] for case in cases)


def test_manuscript_keeps_collusion_claim_boundary() -> None:
    manuscript = (ROOT / "paper/beyond_confessions_submission.md").read_text(encoding="utf-8")
    for phrase in (
        "collusion ground truth",
        "H1 was not supported",
        "H2 was not supported",
        "one-false-positive improvement",
        "Limitations and Dual-Use / Ethical Considerations",
    ):
        assert phrase in manuscript


def test_submission_pdf_has_selectable_text() -> None:
    pdf = ROOT / "output/pdf/beyond_confessions_submission.pdf"
    reader = PdfReader(str(pdf))
    assert len(reader.pages) == 7
    assert all((page.extract_text() or "").strip() for page in reader.pages)
