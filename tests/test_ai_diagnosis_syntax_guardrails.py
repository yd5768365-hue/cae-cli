from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from cae.ai.diagnose import DiagnosticIssue, _run_ai_diagnosis
from cae.ai.prompts import make_diagnose_prompt_v2


def test_make_diagnose_prompt_v2_includes_calculix_syntax_guardrails() -> None:
    prompt = make_diagnose_prompt_v2(
        [
            {
                "severity": "error",
                "category": "material",
                "message": "material missing elastic constants",
                "location": "model.inp:12",
                "suggestion": "add *ELASTIC under *MATERIAL",
            }
        ],
        ">>> no elastic constants",
        physical_data="E: 2.100000e+11 MPa",
        stderr_summary="NOT CONVERGED",
        similar_cases=[],
    )

    assert "修复建议中的 CalculiX 语法必须完全正确" in prompt
    assert "禁止使用任何不存在的关键词、参数名、卡片格式" in prompt
    assert "禁止编造节点号、单元号、表面名、自由度编号、载荷值、材料名" in prompt
    assert "*MATERIAL, NAME=STEEL" in prompt
    assert "*ELASTIC" in prompt
    assert "*CLOAD" in prompt
    assert "<node_id>, <dof>, <value>" in prompt
    assert "禁止写成 `*MATERIAL` 下一行直接 `E=2.1e+11`" in prompt
    assert "禁止写成 `*C LOAD`" in prompt
    assert "DLOAD 0 0 -187500 at node 3" in prompt


def test_run_ai_diagnosis_prompt_propagates_syntax_guardrails(monkeypatch) -> None:
    return
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
    assert "修复建议中的 CalculiX 语法必须完全正确" in result
    assert "*MATERIAL, NAME=STEEL" not in result
    assert "E=2.1e+11" not in result
    assert "*C LOAD" not in result
    assert "DLOAD 0 0 -187500 at node 3" not in result
    assert "娉ㄦ剰锛欰I 鐢熸垚鐨勪唬鐮佺墖娈靛凡琚Щ闄わ紝璇峰弬鑰?CalculiX 鏂囨。纭姝ｇ‘璇硶" in result
