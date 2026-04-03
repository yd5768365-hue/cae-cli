from __future__ import annotations

import json
import re
import shutil
from uuid import uuid4
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest

from cae.ai.diagnose import DiagnoseResult, diagnose_results


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "diagnosis_cases"


@dataclass(frozen=True)
class RegressionCase:
    case_dir: Path
    case_id: str
    expected_issue_keys: list[str]
    expected_severities: list[str]


def _iter_case_dirs() -> list[Path]:
    return sorted(
        path
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_dir() and (path / "expected.json").exists()
    )


def _load_case(case_dir: Path) -> RegressionCase:
    data = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    return RegressionCase(
        case_dir=case_dir,
        case_id=data["case_id"],
        expected_issue_keys=list(data["expected_issue_keys"]),
        expected_severities=list(data.get("expected_severities", [])),
    )


def _write_minimal_frd(
    target: Path,
    *,
    displacements: dict[int, list[float]] | None = None,
    stresses: dict[int, list[float]] | None = None,
    model_bounds: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> None:
    node_count = 8
    element_count = 1
    lines = [
        "    1UFRD test\n",
        "    1UUSER\n",
        "    1UDATE 03.april.2026\n",
        "    1UTIME 18:00:00\n",
        "    1UPGM CalculiX\n",
        "    1UVERSION Version 2.22\n",
        f"    1C{node_count:>10}{'':>10}    1\n",
    ]

    nodes = [
        (1, 0.0, 0.0, 0.0),
        (2, model_bounds[0], 0.0, 0.0),
        (3, model_bounds[0], model_bounds[1], 0.0),
        (4, 0.0, model_bounds[1], 0.0),
        (5, 0.0, 0.0, model_bounds[2]),
        (6, model_bounds[0], 0.0, model_bounds[2]),
        (7, model_bounds[0], model_bounds[1], model_bounds[2]),
        (8, 0.0, model_bounds[1], model_bounds[2]),
    ]
    for node_id, x, y, z in nodes:
        lines.append(f" -1{'':>5}{node_id}{x:>15.5f}{y:>15.5f}{z:>15.5f}\n")
    lines.append(" -3\n")

    lines.append(f"    3C{element_count:>10}{'':>10}    1\n")
    lines.append(f" -1{1:>5}{1:>5}    1    1\n")
    lines.append(f" -2{1:>5}{2:>5}{3:>5}{4:>5}{5:>5}{6:>5}{7:>5}{8:>5}\n")
    lines.append(" -3\n")

    if displacements:
        lines.append("  100C       DISP       1  0.00000E+00      1\n")
        lines.append(" -4  DISP        4    1\n")
        for comp in ["D1", "D2", "D3", "ALL"]:
            lines.append(f" -5  {comp}      1    2    0    0\n")
        for node_id in sorted(displacements):
            vals = displacements[node_id]
            d1 = vals[0] if len(vals) > 0 else 0.0
            d2 = vals[1] if len(vals) > 1 else 0.0
            d3 = vals[2] if len(vals) > 2 else 0.0
            lines.append(f" -1{node_id:>5}{d1:>15.5e}{d2:>15.5e}{d3:>15.5e}\n")
        lines.append(" -3\n")

    if stresses:
        lines.append("  100C     STRESS       1  1.00000E+00      1\n")
        lines.append(" -4  STRESS      6    1\n")
        for comp in ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"]:
            lines.append(f" -5  {comp}     1    4    1    1\n")
        for node_id in sorted(stresses):
            vals = stresses[node_id]
            sxx = vals[0] if len(vals) > 0 else 0.0
            syy = vals[1] if len(vals) > 1 else 0.0
            szz = vals[2] if len(vals) > 2 else 0.0
            svm = vals[3] if len(vals) > 3 else 0.0
            syz = vals[4] if len(vals) > 4 else 0.0
            szx = vals[5] if len(vals) > 5 else 0.0
            lines.append(f" -1{node_id:>5}{sxx:>15.5e}{syy:>15.5e}{szz:>15.5e}{svm:>15.5e}{syz:>15.5e}{szx:>15.5e}\n")
        lines.append(" -3\n")

    lines.append("9999\n")
    target.write_text("".join(lines), encoding="latin-1")


def _materialize_case(case: RegressionCase, workspace_root: Path) -> tuple[Path, Path]:
    results_dir = workspace_root / case.case_id.replace("/", "_")
    if results_dir.exists():
        shutil.rmtree(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    inp_source = case.case_dir / "input.inp"
    stderr_source = case.case_dir / "stderr.txt"

    inp_target = results_dir / "input.inp"
    stderr_target = results_dir / "case.stderr"
    shutil.copy2(inp_source, inp_target)
    shutil.copy2(stderr_source, stderr_target)

    stderr_text = stderr_source.read_text(encoding="utf-8")
    (results_dir / "case.sta").write_text(stderr_text, encoding="utf-8")
    (results_dir / "case.dat").write_text(stderr_text, encoding="utf-8")

    expected_keys = set(case.expected_issue_keys)
    if "rigid_body_mode" in expected_keys:
        _write_minimal_frd(
            results_dir / "case.frd",
            displacements={i: [3.0e-2, 0.0, 0.0] for i in range(1, 9)},
            stresses={1: [0.0, 0.0, 0.0, 1.0e5, 0.0, 0.0]},
        )
    elif "unit_consistency" in expected_keys:
        _write_minimal_frd(
            results_dir / "case.frd",
            displacements={i: [1.0e-6, 0.0, 0.0] for i in range(1, 9)},
            stresses={1: [0.0, 0.0, 0.0, 1.0e-1, 0.0, 0.0]},
        )

    return results_dir, inp_target


@pytest.fixture(autouse=True)
def disable_reference_case_matching(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "cae.ai.diagnose._check_reference_cases",
        lambda results_dir, inp_file=None, ctx=None: {"issues": [], "similar_cases": []},
    )


@pytest.fixture(params=[_load_case(case_dir) for case_dir in _iter_case_dirs()], ids=lambda case: case.case_id)
def sample_case(request: pytest.FixtureRequest) -> RegressionCase:
    return request.param


@pytest.fixture
def regression_workspace(request: pytest.FixtureRequest) -> Path:
    root = Path(__file__).parent / ".tmp_regression_cases"
    root.mkdir(exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name)
    case_root = root / safe_name / uuid4().hex
    case_root.mkdir(parents=True, exist_ok=True)
    return case_root


def run_case(sample_case: RegressionCase, workspace_root: Path) -> DiagnoseResult:
    results_dir, inp_file = _materialize_case(sample_case, workspace_root)
    return diagnose_results(results_dir, client=None, inp_file=inp_file, stream=False)


def test_regression_case_matches_expected_issue_keys(sample_case: RegressionCase, regression_workspace: Path) -> None:
    result = run_case(sample_case, regression_workspace)
    assert result.success, result.error

    found_categories = {issue.category for issue in result.issues}
    for expected_key in sample_case.expected_issue_keys:
        assert expected_key in found_categories, (
            f"{sample_case.case_id} expected category {expected_key!r}, "
            f"found {sorted(found_categories)!r}"
        )


def test_regression_case_matches_expected_severities(sample_case: RegressionCase, regression_workspace: Path) -> None:
    result = run_case(sample_case, regression_workspace)
    assert result.success, result.error

    severities_by_category: dict[str, set[str]] = defaultdict(set)
    for issue in result.issues:
        severities_by_category[issue.category].add(issue.severity)

    for expected_key, expected_severity in zip(sample_case.expected_issue_keys, sample_case.expected_severities):
        assert expected_severity in severities_by_category[expected_key], (
            f"{sample_case.case_id} expected severity {expected_severity!r} "
            f"for category {expected_key!r}, found {sorted(severities_by_category[expected_key])!r}"
        )
