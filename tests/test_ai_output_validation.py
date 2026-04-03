from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from cae.ai.diagnose import (
    AI_OUTPUT_SYNTAX_WARNING,
    DiagnosticIssue,
    _run_ai_diagnosis,
    strip_code_blocks,
    validate_ai_output,
)


def test_strip_code_blocks_removes_fenced_blocks() -> None:
    text = "前置说明\n```text\n*C LOAD\n1, 3, -1000\n```\n后置说明"

    result = strip_code_blocks(text)

    assert "```" not in result
    assert "前置说明" in result
    assert "后置说明" in result


def test_validate_ai_output_removes_invalid_syntax_and_appends_warning() -> None:
    text = (
        "建议先检查材料定义。\n"
        "```text\n"
        "*MATERIAL\n"
        "E=2.1e+11\n"
        "ELASTIC, TYPE=ISOTROPIC\n"
        "```\n"
        "或者使用 *C LOAD。\n"
        "DLOAD 0 0 -187500 at node 3\n"
    )

    result = validate_ai_output(text)

    assert "E=2.1e+11" not in result
    assert "*C LOAD" not in result
    assert "DLOAD 0 0 -187500 at node 3" not in result
    assert "建议先检查材料定义。" in result
    assert AI_OUTPUT_SYNTAX_WARNING in result


def test_run_ai_diagnosis_sanitizes_invalid_generated_snippets(monkeypatch) -> None:
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
        lambda results_dir, issues, ctx=None: ">>> no elastic constants",
    )

    client = MagicMock()
    client.complete.return_value = (
        "最可能根因：材料卡片不完整。\n"
        "修复建议：\n"
        "```text\n"
        "*MATERIAL\n"
        "E=2.1e+11\n"
        "```\n"
        "也可以写成 *C LOAD。\n"
    )

    result = _run_ai_diagnosis(
        client,
        level1_issues=[
            DiagnosticIssue(
                severity="error",
                category="material",
                message="材料缺少弹性常数",
                suggestion="在 *MATERIAL 中添加 *ELASTIC",
            )
        ],
        level2_issues=[],
        similar_cases=[],
        results_dir=Path.cwd(),
        inp_file=None,
        stream=False,
        ctx=None,
    )

    assert result is not None
    assert "最可能根因：材料卡片不完整。" in result
    assert "E=2.1e+11" not in result
    assert "*C LOAD" not in result
    assert AI_OUTPUT_SYNTAX_WARNING in result
