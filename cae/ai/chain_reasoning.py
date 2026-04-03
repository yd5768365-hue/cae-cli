# chain_reasoning.py
"""
多步 Chain 推理系统

借鉴 llm-diagnostic-reasoning 的 Chain 推理模式，
实现 4 步诊断推理：
1. 症状识别（Symptom）
2. 原因分析（Cause）
3. 验证推理（Verify）
4. 诊断结论（Diagnosis）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm_client import LLMClient
from .prompts import (
    CHAIN_SYSTEM,
    make_chain_symptom_prompt,
    make_chain_cause_prompt,
    make_chain_verify_prompt,
    make_chain_diagnosis_prompt,
)
from .diagnose import _get_stderr_snippets

log = logging.getLogger(__name__)


@dataclass
class ChainStep:
    """Chain 推理步骤。"""
    step_name: str  # 步骤名称
    step_number: int  # 步骤编号 (1-4)
    content: str  # 推理内容
    confidence: str = "中"  # 置信度：高/中/低
    key_findings: list[str] = field(default_factory=list)  # 关键发现


@dataclass
class ChainReasoningResult:
    """Chain 推理结果。"""
    success: bool
    steps: list[ChainStep] = field(default_factory=list)  # 推理步骤
    final_diagnosis: Optional[str] = None  # 最终诊断
    root_causes: list[str] = field(default_factory=list)  # 根因
    fix_suggestions: list[dict] = field(default_factory=list)  # 修复建议
    reasoning_chain: Optional[str] = None  # 推理链摘要
    error: Optional[str] = None


class ChainReasoner:
    """
    多步 Chain 推理器。

    采用类似 llm-diagnostic-reasoning 的 Chain 推理模式，
    分 4 步进行诊断推理，每步都建立在上一步的基础上。

    使用方法：
    ```python
    reasoner = ChainReasoner(client=llm_client)
    result = reasoner.reason(
        issues=level1_issues,
        physical_data=physical_data,
        similar_cases=similar_cases,
        results_dir=results_dir,
        stream=True,
    )
    ```
    """

    def __init__(self, client: LLMClient):
        """
        初始化 Chain 推理器。

        Args:
            client: LLM 客户端
        """
        self.client = client

    def reason(
        self,
        issues: list,
        physical_data: str,
        similar_cases: list[dict],
        results_dir: Path,
        *,
        stream: bool = True,
    ) -> ChainReasoningResult:
        """
        执行多步 Chain 推理。

        Args:
            issues: 规则检测的问题列表
            physical_data: 关键物理数据字符串
            similar_cases: 相似案例列表
            results_dir: 结果目录
            stream: 是否流式输出

        Returns:
            ChainReasoningResult: 推理结果
        """
        result = ChainReasoningResult(success=True)

        # 将 issues 转换为 dict 格式
        issue_dicts = []
        for i in issues:
            if hasattr(i, '__dict__'):
                issue_dicts.append({
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "location": getattr(i, 'location', None),
                    "suggestion": getattr(i, 'suggestion', None),
                })
            else:
                issue_dicts.append(i)

        stderr_snippets = _get_stderr_snippets(results_dir, issues)

        try:
            # ========== Step 1: 症状识别 ==========
            symptom_prompt = make_chain_symptom_prompt(
                issue_dicts, physical_data, stderr_snippets
            )

            if stream:
                from .stream_handler import StreamHandler
                handler = StreamHandler()
                symptom_content = handler.stream_tokens(
                    self.client.complete_streaming(CHAIN_SYSTEM + "\n\n" + symptom_prompt)
                )
            else:
                symptom_content = self.client.complete(CHAIN_SYSTEM + "\n\n" + symptom_prompt)

            symptom_step = ChainStep(
                step_name="症状识别",
                step_number=1,
                content=symptom_content,
            )
            result.steps.append(symptom_step)

            # ========== Step 2: 原因分析 ==========
            cause_prompt = make_chain_cause_prompt(symptom_content, physical_data)

            if stream:
                handler2 = StreamHandler()
                cause_content = handler2.stream_tokens(
                    self.client.complete_streaming(cause_prompt)
                )
            else:
                cause_content = self.client.complete(cause_prompt)

            cause_step = ChainStep(
                step_name="原因分析",
                step_number=2,
                content=cause_content,
            )
            result.steps.append(cause_step)

            # ========== Step 3: 验证推理 ==========
            verify_prompt = make_chain_verify_prompt(
                symptom_content,
                cause_content,
                physical_data,
                stderr_snippets,
                similar_cases,
            )

            if stream:
                handler3 = StreamHandler()
                verify_content = handler3.stream_tokens(
                    self.client.complete_streaming(verify_prompt)
                )
            else:
                verify_content = self.client.complete(verify_prompt)

            verify_step = ChainStep(
                step_name="验证推理",
                step_number=3,
                content=verify_content,
            )
            result.steps.append(verify_step)

            # ========== Step 4: 最终诊断 ==========
            diagnosis_prompt = make_chain_diagnosis_prompt(
                symptom_content,
                cause_content,
                verify_content,
                physical_data,
            )

            if stream:
                handler4 = StreamHandler()
                diagnosis_content = handler4.stream_tokens(
                    self.client.complete_streaming(diagnosis_prompt)
                )
            else:
                diagnosis_content = self.client.complete(diagnosis_prompt)

            diagnosis_step = ChainStep(
                step_name="诊断结论",
                step_number=4,
                content=diagnosis_content,
            )
            result.steps.append(diagnosis_step)

            # 解析最终诊断结果
            result.final_diagnosis = diagnosis_content
            result.reasoning_chain = self._build_reasoning_chain(result.steps)

            # 尝试解析根因和修复建议
            result.root_causes, result.fix_suggestions = self._parse_diagnosis(diagnosis_content)

        except Exception as exc:
            result.success = False
            result.error = f"Chain 推理失败: {exc}"
            log.exception("Chain 推理出错")

        return result

    def _build_reasoning_chain(self, steps: list[ChainStep]) -> str:
        """构建推理链摘要。"""
        chain_lines = ["## 推理链\n"]
        for step in steps:
            chain_lines.append(f"**Step {step.step_number}: {step.step_name}**")
            # 提取关键结论（取前3行）
            lines = step.content.strip().split("\n")
            key_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")][:3]
            for ln in key_lines:
                chain_lines.append(f"  → {ln.strip()}")
            chain_lines.append("")
        return "\n".join(chain_lines)

    def _parse_diagnosis(self, diagnosis: str) -> tuple[list[str], list[dict]]:
        """解析诊断结果中的根因和修复建议。"""
        root_causes = []
        fix_suggestions = []

        lines = diagnosis.split("\n")
        current_cause = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 识别根因（**根因 X** 格式）
            if "**根因" in line and ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    current_cause = parts[1].strip().replace("**", "")
                    root_causes.append(current_cause)

            # 识别修复建议（表格格式 "| 优先级 | 操作 |"）
            if line.startswith("|") and "优先级" not in line and "---" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    try:
                        priority = parts[1]
                        action = parts[2]
                        expected = parts[3] if len(parts) > 3 else ""
                        difficulty = parts[4] if len(parts) > 4 else ""
                        fix_suggestions.append({
                            "priority": priority,
                            "action": action,
                            "expected_effect": expected,
                            "difficulty": difficulty,
                        })
                    except IndexError:
                        pass

        return root_causes, fix_suggestions


def format_chain_result(result: ChainReasoningResult) -> str:
    """
    格式化 Chain 推理结果为可读字符串。

    Args:
        result: ChainReasoningResult

    Returns:
        格式化后的字符串
    """
    if not result.success:
        return f"[red]Chain 推理失败: {result.error}[/red]"

    output = []
    output.append("\n" + "=" * 60)
    output.append("多步 Chain 推理诊断")
    output.append("=" * 60)

    for step in result.steps:
        output.append(f"\n## Step {step.step_number}: {step.step_name}")
        output.append("-" * 40)
        output.append(step.content.strip())

    if result.final_diagnosis:
        output.append("\n" + "=" * 60)
        output.append("最终诊断结果")
        output.append("=" * 60)
        output.append(result.final_diagnosis.strip())

    if result.reasoning_chain:
        output.append("\n" + "-" * 40)
        output.append(result.reasoning_chain)

    return "\n".join(output)
