from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from cae.ai.diagnose import DiagnosticIssue, _run_ai_diagnosis


def test_ai_diagnosis_prompt_includes_all_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        "cae.ai.diagnose._get_physical_data",
        lambda results_dir, inp_file=None, ctx=None: "最大位移: 1.23e-03",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_summary",
        lambda results_dir, ctx=None: "收敛状态: NOT CONVERGED",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_snippets",
        lambda results_dir, issues, ctx=None: ">>> zero pivot",
    )

    client = MagicMock()
    client.complete.side_effect = lambda prompt: prompt

    result = _run_ai_diagnosis(
        client,
        level1_issues=[
            DiagnosticIssue(
                severity="error",
                category="boundary",
                message="检测到 zero pivot",
                suggestion="补充位移约束",
            )
        ],
        level2_issues=[],
        similar_cases=[
            {
                "name": "beam_test",
                "similarity_score": 92.0,
                "element_type": "C3D8",
                "problem_type": "static",
                "expected_disp_max": 0.001,
                "expected_stress_max": 120.0,
            }
        ],
        results_dir=Path.cwd(),
        inp_file=None,
        stream=False,
        ctx=None,
    )

    assert result is not None
    assert "最大位移: 1.23e-03" in result
    assert "收敛状态: NOT CONVERGED" in result
    assert "beam_test" in result
    assert ">>> zero pivot" in result
    assert "补充位移约束" in result
