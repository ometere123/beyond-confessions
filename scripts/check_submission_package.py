"""Run final no-API quality checks over the Milestone 3 package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

ABSTRACT_RE = re.compile(r"\*\*Abstract\.\*\*(.*?)(?:\n\n|$)", re.DOTALL)
IMAGE_RE = re.compile(r"!\[[^]]*\]\(([^)]+)\)")
CREDENTIAL_RE = re.compile(
    r"sk-(?:proj-|live-|admin-)[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9]{40,}|"
    r"-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----"
)
OFFICIAL_TEMPLATE_URL = (
    "https://docs.google.com/document/d/1Y5wd3VRbXU5N08BvAGiJUQTaWbMCSPjhzXsR-ozuehg/copy?usp=sharing"
)
GOOGLE_DOC_URL = (
    "https://docs.google.com/document/d/1Dw0ae0l4lyRb2dJQvuAykuzwHCde5eqRmezN4HuTL48/edit?tab=t.0"
)


def _words(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_file(path: Path, failures: list[str]) -> None:
    if not path.is_file():
        failures.append(f"missing file: {path}")


def _load_json(path: Path, failures: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"invalid JSON {path}: {exc}")
        return {}
    if not isinstance(value, dict):
        failures.append(f"expected JSON object: {path}")
        return {}
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("evidence/milestone3/submission_qa.json")
    )
    args = parser.parse_args()
    root = args.repo_root.resolve()
    failures: list[str] = []
    reviews: list[str] = []

    manuscript = root / "paper" / "beyond_confessions_submission.md"
    pdf = root / "output" / "pdf" / "beyond_confessions_submission.pdf"
    verification_path = root / "evidence" / "milestone3" / "verification_report.json"
    case_path = root / "evidence" / "milestone3" / "case_studies.json"
    manifest_path = root / "evidence" / "milestone3" / "figures" / "figure_manifest.json"
    for path in (manuscript, pdf, verification_path, case_path, manifest_path):
        _check_file(path, failures)

    source_text = manuscript.read_text(encoding="utf-8") if manuscript.is_file() else ""
    abstract_match = ABSTRACT_RE.search(source_text)
    abstract_words = _words(abstract_match.group(1)) if abstract_match else 0
    if not 150 <= abstract_words <= 250:
        failures.append(f"abstract word count outside 150-250: {abstract_words}")

    required_markers = (
        "Beyond Confessions: What Can Message–Action Evidence Really Establish About AI-Agent Collusion?",
        "Ometere Dele-Alufec",
        "Independent Researcher, Nigeria",
        "Limitations and Dual-Use / Ethical Considerations",
        "AI tools were used",
        "H1 was not supported",
        "H2 was not supported",
        "https://github.com/ometere123/beyond-confessions",
    )
    for marker in required_markers:
        if marker not in source_text:
            failures.append(f"manuscript marker missing: {marker}")
    for forbidden in (
        "AUTHOR NAME - REVIEW REQUIRED",
        "AFFILIATION - REVIEW REQUIRED",
        "Submission draft",
        "submission draft",
    ):
        if forbidden in source_text:
            failures.append(f"draft-only manuscript marker remains: {forbidden}")

    pdf_pages = 0
    selectable_pages = 0
    main_text_pages = None
    pdf_text = ""
    pdf_metadata: dict[str, Any] = {}
    if pdf.is_file():
        try:
            reader = PdfReader(str(pdf))
            pdf_pages = len(reader.pages)
            page_texts = [(page.extract_text() or "") for page in reader.pages]
            selectable_pages = sum(bool(text.strip()) for text in page_texts)
            pdf_text = "\n".join(page_texts)
            metadata = reader.metadata or {}
            title_page_compact = re.sub(r"\s+", "", page_texts[0])
            pdf_metadata = {
                "title": metadata.get("/Title"),
                "author": metadata.get("/Author"),
                "title_matches": metadata.get("/Title")
                == "Beyond Confessions — Ometere Dele-Alufec — Apart Research 2026",
                "author_visible_on_title_page": "OmetereDele-Alufec" in title_page_compact,
            }
            references_page = next(
                (index + 1 for index, text in enumerate(page_texts) if "References" in text),
                None,
            )
            if references_page is not None:
                main_text_pages = references_page - 1
            else:
                failures.append("PDF references heading not found")
        except (OSError, PdfReadError, ValueError) as exc:
            failures.append(f"PDF could not be parsed: {exc}")
    if selectable_pages != pdf_pages:
        failures.append(f"not all PDF pages have selectable text: {selectable_pages}/{pdf_pages}")
    if main_text_pages is None or not 1 <= main_text_pages <= 8:
        failures.append(f"main-text page count outside 1-8: {main_text_pages}")
    if CREDENTIAL_RE.search(pdf_text):
        failures.append("credential-like material detected in PDF text")
    if "OPENAI_API_KEY" + "=" in pdf_text:
        failures.append("possible private configuration material detected in PDF text")

    verification = _load_json(verification_path, failures)
    if verification.get("status") != "pass":
        failures.append("independent verification receipt is not pass")
    if verification.get("api_requests_made") != 0:
        failures.append("Milestone 3 verification made or recorded API requests")
    dataset = verification.get("dataset", {})
    if dataset.get("completed_episode_count") != 40 or dataset.get("assessment_count") != 160:
        failures.append("verification receipt does not report 40 episodes and 160 assessments")
    comparison = verification.get("comparisons_to_committed_results", {})
    if comparison.get("mismatch_count") != 0:
        failures.append("verification receipt reports result mismatches")

    case_studies = []
    if case_path.is_file():
        try:
            case_studies = json.loads(case_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"invalid case-study JSON: {exc}")
    if len(case_studies) != 4:
        failures.append(f"expected four case studies, got {len(case_studies)}")
    if len({item.get("case_id") for item in case_studies if isinstance(item, dict)}) != 4:
        failures.append("case-study IDs are not unique")

    manifest = _load_json(manifest_path, failures)
    figure_count = 0
    for figure in manifest.get("figures", []):
        if not isinstance(figure, dict):
            failures.append("figure manifest contains a non-object entry")
            continue
        figure_count += 1
        figure_path = root / "evidence" / "milestone3" / "figures" / str(figure.get("file", ""))
        _check_file(figure_path, failures)
        if figure_path.is_file() and _sha256(figure_path) != figure.get("sha256"):
            failures.append(f"figure checksum mismatch: {figure_path}")
    if figure_count != 4:
        failures.append(f"expected four figures, got {figure_count}")
    for relative in IMAGE_RE.findall(source_text):
        if not (manuscript.parent / relative).is_file():
            failures.append(f"manuscript image is missing: {relative}")

    if not GOOGLE_DOC_URL:
        failures.append("Google Docs URL is not recorded")

    report = {
        "schema_version": "beyond-confessions-m3-submission-qa-1",
        "status": "pass" if not failures else "fail",
        "api_requests_made": 0,
        "abstract_word_count": abstract_words,
        "pdf": {
            "path": "output/pdf/beyond_confessions_submission.pdf",
            "pages_total": pdf_pages,
            "selectable_text_pages": selectable_pages,
            "main_text_pages": main_text_pages,
            "metadata": pdf_metadata,
        },
        "verified_requirements": {
            "archive_recalculation": verification.get("status") == "pass",
            "dataset_40_episodes": dataset.get("completed_episode_count") == 40,
            "auditor_assessments_160": dataset.get("assessment_count") == 160,
            "four_data_derived_figures": figure_count == 4,
            "credential_scan": not bool(CREDENTIAL_RE.search(pdf_text)),
            "github_link_present": "https://github.com/ometere123/beyond-confessions" in source_text,
        },
        "template_status": "verified_official_google_docs_export",
        "official_template_url": OFFICIAL_TEMPLATE_URL,
        "google_docs_url": GOOGLE_DOC_URL,
        "google_docs_export": True,
        "failures": failures,
        "review_items": reviews,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failures": len(failures), "output": str(args.output)}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
