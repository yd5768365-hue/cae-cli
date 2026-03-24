# explain.py
"""
AI 结果解读

解析 .frd 文件，提取节点/单元/位移/应力统计，
组装结构化 prompt，调用 LLM 进行解读。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from cae.viewer.frd_parser import FrdData, parse_frd
from .llm_client import LLMClient
from .prompts import EXPLAIN_SYSTEM, make_explain_prompt
from .stream_handler import StreamHandler


@dataclass
class ExplainResult:
    """AI 解读结果。"""
    success: bool
    summary: str
    key_findings: list[str] = field(default_factory=list)
    displacement_summary: Optional[str] = None
    stress_summary: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None


def explain_results(
    results_dir: Path,
    client: LLMClient,
    *,
    stream: bool = True,
) -> ExplainResult:
    """
    解析结果目录，提取 .frd 数据并调用 AI 解读。

    Args:
        results_dir: 包含 .frd 文件的目录
        client: LLM 客户端
        stream: 是否流式输出

    Returns:
        ExplainResult 包含 AI 解读文本
    """
    try:
        frd_file = _find_frd(results_dir)
        if not frd_file:
            return ExplainResult(
                success=False,
                summary="",
                error=f"目录中未找到 .frd 文件: {results_dir}",
            )

        frd_data = parse_frd(frd_file)
        if not frd_data.has_geometry:
            return ExplainResult(
                success=False,
                summary="",
                error="FRD 文件缺少几何数据",
            )

        # 提取统计信息
        stats = _extract_stats(frd_data)
        prompt_text = make_explain_prompt(**stats)

        # 调用 LLM
        if stream:
            handler = StreamHandler()
            tokens = client.complete_streaming(prompt_text)
            full_text = handler.stream_tokens(tokens)
        else:
            full_text = client.complete(prompt_text)

        # 解析 AI 返回
        summary, key_findings, disp_summary, stress_summary, warnings = _parse_ai_response(full_text)

        return ExplainResult(
            success=True,
            summary=summary,
            key_findings=key_findings,
            displacement_summary=disp_summary,
            stress_summary=stress_summary,
            warnings=warnings,
        )

    except FileNotFoundError as exc:
        return ExplainResult(success=False, summary="", error=str(exc))
    except Exception as exc:
        return ExplainResult(success=False, summary="", error=f"解读失败: {exc}")


def _find_frd(results_dir: Path) -> Optional[Path]:
    """在目录中查找 .frd 文件。"""
    frd_files = sorted(results_dir.glob("*.frd"))
    if frd_files:
        return frd_files[0]
    return None


def _extract_stats(frd_data: FrdData) -> dict:
    """从 FrdData 提取统计信息。"""
    # 节点/单元数
    node_count = frd_data.node_count
    element_count = frd_data.element_count

    # 位移
    disp_result = frd_data.get_result("DISP")
    max_disp = 0.0
    max_disp_node = 0
    if disp_result and disp_result.values:
        all_disps = []
        for node_id in disp_result.node_ids:
            vals = disp_result.values.get(node_id)
            if vals is not None and len(vals) >= 3:
                magnitude = sum(float(vals[j]) ** 2 for j in range(3)) ** 0.5
                all_disps.append((node_id, magnitude))
        if all_disps:
            max_disp_node, max_disp = max(all_disps, key=lambda x: x[1])

    # 应力
    stress_result = frd_data.get_result("STRESS")
    max_stress = 0.0
    max_stress_elem = 0
    stress_component = "von Mises"
    if stress_result and stress_result.values:
        # 假设第4个分量是 von Mises（根据 CalculiX 输出格式）
        for elem_id, vals in stress_result.values.items():
            # 计算 von Mises 等效应力
            if vals is not None and len(vals) >= 4:
                vm = abs(float(vals[3]))
                if vm > max_stress:
                    max_stress = vm
                    max_stress_elem = elem_id

    # 模型边界（用于计算尺寸）
    model_bounds = (1.0, 1.0, 1.0)  # 默认
    if frd_data.nodes and frd_data.nodes.coords:
        xs = [c[0] for c in frd_data.nodes.coords]
        ys = [c[1] for c in frd_data.nodes.coords]
        zs = [c[2] for c in frd_data.nodes.coords]
        if xs and ys and zs:
            model_bounds = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    # 材料屈服强度（默认 250 MPa for steel）
    material_yield = 250e6

    return {
        "node_count": node_count,
        "element_count": element_count,
        "max_displacement": max_disp,
        "max_displacement_node": max_disp_node,
        "max_stress": max_stress,
        "max_stress_element": max_stress_elem,
        "stress_component": stress_component,
        "material_yield": material_yield,
        "model_bounds": model_bounds,
    }


def _parse_ai_response(text: str) -> tuple:
    """简单解析 AI 返回文本。"""
    # 提取摘要、关键发现等
    lines = text.strip().splitlines()
    summary_parts = []
    findings = []
    disp_parts = []
    stress_parts = []
    warnings = []
    current_section = "summary"

    for line in lines:
        upper = line.upper().strip()
        if "关键发现" in upper or "主要发现" in upper:
            current_section = "findings"
            continue
        elif "位移" in upper and "摘要" in upper:
            current_section = "disp"
            continue
        elif "应力" in upper and "摘要" in upper:
            current_section = "stress"
            continue
        elif "警告" in upper:
            current_section = "warnings"
            continue

        if current_section == "summary":
            summary_parts.append(line)
        elif current_section == "findings":
            if line.strip().startswith(("-", "*", "•")):
                findings.append(line.strip().lstrip("-*• ").strip())
            elif line.strip() and len(line.strip()) > 5:
                findings.append(line.strip())
        elif current_section == "disp":
            disp_parts.append(line)
        elif current_section == "stress":
            stress_parts.append(line)
        elif current_section == "warnings":
            if line.strip().startswith(("-", "*", "•")):
                warnings.append(line.strip().lstrip("-*• ").strip())

    return (
        " ".join(summary_parts),
        findings[:5],
        " ".join(disp_parts) if disp_parts else None,
        " ".join(stress_parts) if stress_parts else None,
        warnings,
    )
