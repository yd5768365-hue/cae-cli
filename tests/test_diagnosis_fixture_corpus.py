from __future__ import annotations

import json
from pathlib import Path


def test_diagnosis_fixture_cases_have_expected_files() -> None:
    root = Path(__file__).parent / "fixtures" / "diagnosis_cases"
    assert root.exists(), "diagnosis fixture root does not exist"

    case_dirs = [
        path
        for path in root.rglob("*")
        if path.is_dir() and (path / "expected.json").exists()
    ]
    assert case_dirs, "no diagnosis fixture cases found"

    for case_dir in case_dirs:
        assert (case_dir / "input.inp").exists(), f"missing input.inp in {case_dir}"
        assert (case_dir / "stderr.txt").exists(), f"missing stderr.txt in {case_dir}"
        data = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
        assert "expected_issue_keys" in data, f"missing expected_issue_keys in {case_dir}"
        assert isinstance(data["expected_issue_keys"], list), f"expected_issue_keys must be a list in {case_dir}"
        assert data["expected_issue_keys"], f"expected_issue_keys must not be empty in {case_dir}"


def test_diagnosis_fixture_seed_case_count() -> None:
    root = Path(__file__).parent / "fixtures" / "diagnosis_cases"
    case_dirs = [
        path
        for path in root.rglob("*")
        if path.is_dir() and (path / "expected.json").exists()
    ]
    assert len(case_dirs) >= 10, "expected at least 10 diagnosis seed cases"
