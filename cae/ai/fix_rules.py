# fix_rules.py
"""
基于规则层的自动修复功能

设计原则：
1. 定位由规则层硬编码（确定性的）
2. AI 只生成插入内容（如弹性模量数值）
3. 原文件永远不变，复制后再修改
4. 修复前询问用户，不强制执行

修复流程：
  诊断问题 → 规则层定位 + AI 生成内容 → 精准修改 INP → 用户确认
"""
from __future__ import annotations

import shutil
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cae.inp import InpModifier, Block


# ------------------------------------------------------------------ #
# 数据结构
# ------------------------------------------------------------------ #

@dataclass
class FixResult:
    """修复结果。"""
    success: bool
    fixed_path: Optional[Path] = None
    backup_path: Optional[Path] = None
    changes_summary: str = ""
    error: Optional[str] = None


# ------------------------------------------------------------------ #
# 规则层硬编码的定位逻辑
# ------------------------------------------------------------------ #

def fix_inp(
    inp_file: Path,
    issues: list,  # DiagnosticIssue list
    results_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> FixResult:
    """
    基于规则层的自动修复。

    定位由规则层硬编码，AI 只生成内容。
    """
    if not issues:
        return FixResult(success=True, changes_summary="没有问题需要修复")

    if output_dir is None:
        output_dir = inp_file.parent

    # 备份原文件
    backup_name = inp_file.stem + "_original" + inp_file.suffix
    backup_path = output_dir / backup_name
    shutil.copy2(inp_file, backup_path)

    # 生成修复后的文件名
    fixed_name = inp_file.stem + "_fixed" + inp_file.suffix
    fixed_path = output_dir / fixed_name

    # 读取原文件
    text = inp_file.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 收集修复操作
    fixes_applied = []

    for issue in issues:
        message = issue.message.lower() if hasattr(issue, 'message') and issue.message else ""
        suggestion = issue.suggestion.lower() if hasattr(issue, 'suggestion') and issue.suggestion else ""

        # ===== 材料缺少弹性常数 =====
        if "elastic" in message or "弹性" in message:
            fix = _fix_missing_elastic(lines, issue, results_dir)
            if fix:
                fixes_applied.append(fix)

        # ===== 收敛困难 =====
        elif "converge" in message or "收敛" in message or "increment" in suggestion:
            fix = _fix_convergence_issues(lines, issue)
            if fix:
                fixes_applied.append(fix)

    if not fixes_applied:
        return FixResult(
            success=False,
            backup_path=backup_path,
            error="没有可自动修复的问题",
        )

    # 写入修复后的文件
    new_text = "\n".join(lines)
    fixed_path.write_text(new_text, encoding="utf-8")

    return FixResult(
        success=True,
        fixed_path=fixed_path,
        backup_path=backup_path,
        changes_summary="; ".join(fixes_applied),
    )


def _fix_missing_elastic(lines: list[str], issue, results_dir: Optional[Path] = None) -> Optional[str]:
    """
    修复：材料缺少弹性常数

    定位逻辑（硬编码）：
    1. 从 stderr 片段找到材料名（如 MINESI1）
    2. 在 INP 中找到 *MATERIAL, NAME=材料名 的位置
    3. 在该块的数据行结束后插入 *ELASTIC
    """
    # 从 issue.message 或 suggestion 中提取材料名
    # 格式如："材料缺少弹性常数（Elastic modulus）"
    # 或者 suggestion: "在 *MATERIAL 中添加 *ELASTIC..."

    material_name = _extract_material_name_from_issue(issue, results_dir)
    if not material_name:
        return None

    # 找到 *MATERIAL, NAME=xxx 的位置
    mat_line_idx = -1
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("*MATERIAL"):
            if f"NAME={material_name}" in line.upper() or f"NAME = {material_name}" in line.upper():
                mat_line_idx = i
                break

    if mat_line_idx == -1:
        return None

    # 找到该 MATERIAL 块的数据行结束位置（下一个 * 开头的行）
    insert_idx = mat_line_idx + 1
    while insert_idx < len(lines):
        if lines[insert_idx].strip().upper().startswith("*"):
            break
        # 跳过已经是 ELASTIC 等属性行的行
        if lines[insert_idx].strip().upper().startswith("*ELASTIC"):
            return None  # 已经存在，跳过
        insert_idx += 1

    # 插入 *ELASTIC 卡片（使用默认值，用户可后续修改）
    lines.insert(insert_idx, "*ELASTIC")
    lines.insert(insert_idx + 1, "210000, 0.3")  # 默认钢材料

    return f"为材料 {material_name} 添加 *ELASTIC (E=210000, nu=0.3)"


def _fix_convergence_issues(lines: list[str], issue) -> Optional[str]:
    """
    修复：收敛困难

    定位逻辑：
    1. 找到 *STATIC 的位置
    2. 修改初始步长参数
    """
    # 找到 *STATIC 的位置
    static_idx = -1
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("*STATIC"):
            static_idx = i
            break

    if static_idx == -1:
        return None

    # *STATIC 的第一个参数通常是初始步长
    # 格式：*STATIC, 0.1, 1.0  或  *STATIC, 0.01
    static_line = lines[static_idx]

    # 检查是否已经有参数
    if "," in static_line:
        # 修改现有参数
        parts = static_line.rstrip().split(",")
        if len(parts) >= 2:
            # 第一个参数是初始步长，改为更小的值
            try:
                current_val = float(parts[1].strip())
                new_val = current_val * 0.1  # 减小10倍
                parts[1] = str(new_val)
                lines[static_idx] = ",".join(parts)
                return f"修改 *STATIC 初始步长: {current_val} -> {new_val}"
            except ValueError:
                pass

    return None


def _extract_material_name_from_issue(issue, results_dir: Optional[Path] = None) -> Optional[str]:
    """从 issue 或 stderr 中提取材料名。"""
    # 方法1：从 stderr 直接读取
    if results_dir:
        stderr_files = list(results_dir.glob("*.stderr"))
        if stderr_files:
            try:
                text = stderr_files[0].read_text(encoding="utf-8", errors="replace")
                # 匹配 "no elastic constants were assigned to material XXX"
                match = re.search(r"to\s+material\s+(\w+)", text, re.IGNORECASE)
                if match:
                    return match.group(1)
            except OSError:
                pass

    # 方法2：从 suggestion 中提取
    if hasattr(issue, 'suggestion') and issue.suggestion:
        # 匹配 "材料 XXX" 或 "material XXX"
        match = re.search(r"(?:material|材料)\s*(\w+)", issue.suggestion, re.IGNORECASE)
        if match:
            return match.group(1)

        # 匹配 NAME=xxx
        match = re.search(r"NAME\s*=\s*(\w+)", issue.suggestion, re.IGNORECASE)
        if match:
            return match.group(1)

    return None

    return None
