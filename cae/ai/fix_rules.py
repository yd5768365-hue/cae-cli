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

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
    verification_status: str = "skipped"
    verification_notes: str = ""
    error: Optional[str] = None


SAFE_AUTOFIX_RULES = {
    "material_missing_elastic",
    "input_missing_step",
    "convergence_static_increment",
}


def _normalized_issue_text(issue) -> str:
    message = getattr(issue, "message", "") or ""
    suggestion = getattr(issue, "suggestion", "") or ""
    return f"{message}\n{suggestion}".lower()


def _classify_issue_for_autofix(issue) -> Optional[str]:
    text = _normalized_issue_text(issue)
    category = getattr(issue, "category", "") or ""

    if category == "material" and "elastic" in text:
        return "material_missing_elastic"

    if category == "input_syntax" and ("*step" in text or ("step" in text and "not found" in text)):
        return "input_missing_step"

    if category == "convergence" and (
        "increment" in text or "static" in text or "initial step" in text
    ):
        return "convergence_static_increment"

    return None


def get_safe_autofixable_issues(issues: list) -> list:
    return [issue for issue in issues if _classify_issue_for_autofix(issue) in SAFE_AUTOFIX_RULES]


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

        # ===== 载荷传递问题 =====
        elif "rhs only consists of 0.0" in message or "载荷向量为零" in message:
            fix = _fix_load_transfer(lines, issue, results_dir)
            if fix:
                fixes_applied.append(fix)

        # ===== 边界条件问题 =====
        elif "zero pivot" in message or "singular matrix" in message or "欠约束" in message:
            fix = _fix_boundary_issues(lines, issue)
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


def _fix_load_transfer(lines: list[str], issue, results_dir: Optional[Path] = None) -> Optional[str]:
    """
    修复：载荷传递问题（RHS only consists of 0.0）

    定位逻辑：
    1. 检查是否存在 *COUPLING 配合 *DISTRIBUTING
    2. 如果存在，将 *CLOAD 改为 *DLOAD

    注意：这是复杂修改，需要仔细处理。
    当前实现仅检测问题，不尝试自动修复。
    """
    # 检查是否有 DISTRIBUTING 耦合
    has_distributing = False
    has_coupling = False
    coupling_line_idx = -1

    for i, line in enumerate(lines):
        line_upper = line.strip().upper()
        if line_upper.startswith("*COUPLING"):
            has_coupling = True
            coupling_line_idx = i
        if line_upper.startswith("*DISTRIBUTING"):
            has_distributing = True

    # 如果有 DISTRIBUTING 耦合但没有 CLOAD，可能需要提示
    if has_distributing and has_coupling:
        return (
            "检测到 *COUPLING 配合 *DISTRIBUTING 使用，"
            "载荷应使用 *DLOAD 而非 *CLOAD。"
            "建议手动修改：将 *CLOAD 替换为相应的 *DLOAD 定义。"
        )

    return None


def _fix_boundary_issues(lines: list[str], issue) -> Optional[str]:
    """
    修复：边界条件问题（欠约束/过约束）

    当前实现仅检测问题，给出建议。
    实际修复需要用户确认边界条件是否正确。
    """
    message = issue.message.lower() if hasattr(issue, 'message') and issue.message else ""

    if "zero pivot" in message:
        return (
            "零主元错误：检查边界条件是否完整。"
            "确保结构被完全约束（所有位移分量），"
            "壳/梁结构需要面外约束。"
        )
    elif "singular matrix" in message:
        return (
            "矩阵奇异错误：检查是否存在冲突的边界条件，"
            "或某些自由度未被约束。"
        )

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


# ------------------------------------------------------------------ #
# Phase 1 safe whitelist implementation
# ------------------------------------------------------------------ #

SAFE_AUTOFIX_RULES = {
    "material_missing_elastic",
    "input_missing_step",
    "convergence_static_increment",
}


def _normalized_issue_text(issue) -> str:
    message = getattr(issue, "message", "") or ""
    suggestion = getattr(issue, "suggestion", "") or ""
    return f"{message}\n{suggestion}".lower()


def _classify_issue_for_autofix(issue) -> Optional[str]:
    text = _normalized_issue_text(issue)
    category = getattr(issue, "category", "") or ""

    if category == "material" and "elastic" in text:
        return "material_missing_elastic"

    if category == "input_syntax" and ("*step" in text or ("step" in text and "not found" in text)):
        return "input_missing_step"

    if category == "convergence" and (
        "increment" in text or "static" in text or "initial step" in text
    ):
        return "convergence_static_increment"

    return None


def get_safe_autofixable_issues(issues: list) -> list:
    """Return only issues that fall inside the explicit safe auto-fix whitelist."""
    return [issue for issue in issues if _classify_issue_for_autofix(issue) in SAFE_AUTOFIX_RULES]


def fix_inp(
    inp_file: Path,
    issues: list,
    results_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> FixResult:
    """
    Apply only safe whitelist auto-fixes.

    High-risk issue classes such as loads, boundary values, contact parameters,
    and real material values stay manual in Phase 1.
    """
    if not issues:
        return FixResult(
            success=True,
            changes_summary="No issues to fix.",
            verification_status="skipped",
            verification_notes="No whitelist fixes were applied.",
        )

    safe_issues = get_safe_autofixable_issues(issues)
    if not safe_issues:
        return FixResult(
            success=False,
            error="No safe whitelist auto-fix is available for the selected issues.",
        )

    if output_dir is None:
        output_dir = inp_file.parent

    backup_name = inp_file.stem + "_original" + inp_file.suffix
    backup_path = output_dir / backup_name
    shutil.copy2(inp_file, backup_path)

    fixed_name = inp_file.stem + "_fixed" + inp_file.suffix
    fixed_path = output_dir / fixed_name

    original_text = inp_file.read_text(encoding="utf-8")
    lines = original_text.splitlines()
    fixes_applied: list[str] = []
    applied_rule_names: list[str] = []

    for issue in safe_issues:
        rule_name = _classify_issue_for_autofix(issue)
        fix: Optional[str] = None

        if rule_name == "material_missing_elastic":
            fix = _safe_fix_missing_elastic(lines, issue, results_dir)
        elif rule_name == "input_missing_step":
            fix = _safe_fix_missing_step(lines)
        elif rule_name == "convergence_static_increment":
            fix = _safe_fix_convergence_issues(lines)

        if fix:
            fixes_applied.append(fix)
            if rule_name is not None:
                applied_rule_names.append(rule_name)

    if not fixes_applied:
        return FixResult(
            success=False,
            backup_path=backup_path,
            error="Whitelist matched, but no deterministic fix could be applied.",
        )

    fixed_path.write_text("\n".join(lines), encoding="utf-8")
    verification_status, verification_notes = _verify_safe_autofix_results(
        original_text=original_text,
        fixed_lines=lines,
        applied_rule_names=applied_rule_names,
    )
    return FixResult(
        success=True,
        fixed_path=fixed_path,
        backup_path=backup_path,
        changes_summary="; ".join(fixes_applied),
        verification_status=verification_status,
        verification_notes=verification_notes,
    )


def _safe_fix_missing_elastic(lines: list[str], issue, results_dir: Optional[Path] = None) -> Optional[str]:
    material_name = _safe_extract_material_name(issue, results_dir)
    if not material_name:
        return None

    mat_line_idx = -1
    for i, line in enumerate(lines):
        line_upper = line.strip().upper()
        if not line_upper.startswith("*MATERIAL"):
            continue
        if f"NAME={material_name}".upper() in line_upper or f"NAME = {material_name}".upper() in line_upper:
            mat_line_idx = i
            break

    if mat_line_idx == -1:
        return None

    insert_idx = mat_line_idx + 1
    while insert_idx < len(lines):
        current = lines[insert_idx].strip().upper()
        if current.startswith("*ELASTIC"):
            return None
        if current.startswith("*"):
            break
        insert_idx += 1

    lines.insert(insert_idx, "*ELASTIC")
    lines.insert(insert_idx + 1, "210000, 0.3")
    return f"Added *ELASTIC placeholder for material {material_name}"


def _safe_fix_missing_step(lines: list[str]) -> Optional[str]:
    has_step = any(line.strip().upper().startswith("*STEP") for line in lines)
    if has_step:
        return None

    if lines and lines[-1].strip():
        lines.append("")
    lines.extend(
        [
            "*STEP",
            "*STATIC",
            "0.1, 1.0",
            "*END STEP",
        ]
    )
    return "Added a minimal *STEP/*STATIC block"


def _safe_fix_convergence_issues(lines: list[str]) -> Optional[str]:
    static_idx = -1
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("*STATIC"):
            static_idx = i
            break

    if static_idx == -1:
        return None

    static_line = lines[static_idx].strip()
    if "," in static_line:
        parts = [part.strip() for part in static_line.split(",")]
        if len(parts) >= 2:
            try:
                current_val = float(parts[1])
                new_val = current_val * 0.1
                parts[1] = str(new_val)
                lines[static_idx] = ", ".join(parts)
                return f"Reduced inline *STATIC initial increment: {current_val} -> {new_val}"
            except ValueError:
                return None

    if static_idx + 1 >= len(lines):
        return None

    next_line = lines[static_idx + 1].strip()
    if not next_line or next_line.startswith("*"):
        return None

    parts = [part.strip() for part in next_line.split(",")]
    if not parts:
        return None

    try:
        current_val = float(parts[0])
    except ValueError:
        return None

    new_val = current_val * 0.1
    parts[0] = str(new_val)
    lines[static_idx + 1] = ", ".join(parts)
    return f"Reduced *STATIC initial increment: {current_val} -> {new_val}"


def _safe_extract_material_name(issue, results_dir: Optional[Path] = None) -> Optional[str]:
    if results_dir:
        for stderr_file in results_dir.glob("*.stderr"):
            try:
                text = stderr_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = re.search(r"to\s+material\s+(\w+)", text, re.IGNORECASE)
            if match:
                return match.group(1)

    suggestion = getattr(issue, "suggestion", "") or ""
    if suggestion:
        match = re.search(r"(?:material|材料)\s*(\w+)", suggestion, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r"NAME\s*=\s*(\w+)", suggestion, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def _verify_safe_autofix_results(
    *,
    original_text: str,
    fixed_lines: list[str],
    applied_rule_names: list[str],
) -> tuple[str, str]:
    if not applied_rule_names:
        return "skipped", "No whitelist fixes were applied."

    verification_notes: list[str] = []
    passed_checks = 0

    for rule_name in applied_rule_names:
        if rule_name == "material_missing_elastic":
            passed = any(line.strip().upper().startswith("*ELASTIC") for line in fixed_lines)
            verification_notes.append(
                "material_missing_elastic: *ELASTIC block present"
                if passed
                else "material_missing_elastic: *ELASTIC block still missing"
            )
        elif rule_name == "input_missing_step":
            has_step = any(line.strip().upper().startswith("*STEP") for line in fixed_lines)
            has_end_step = any(line.strip().upper().startswith("*END STEP") for line in fixed_lines)
            passed = has_step and has_end_step
            verification_notes.append(
                "input_missing_step: *STEP/*END STEP block present"
                if passed
                else "input_missing_step: *STEP block is still incomplete"
            )
        elif rule_name == "convergence_static_increment":
            old_increment = _extract_static_initial_increment(original_text.splitlines())
            new_increment = _extract_static_initial_increment(fixed_lines)
            passed = (
                old_increment is not None
                and new_increment is not None
                and new_increment < old_increment
            )
            if passed:
                verification_notes.append(
                    f"convergence_static_increment: initial increment reduced from {old_increment:g} to {new_increment:g}"
                )
            else:
                verification_notes.append(
                    "convergence_static_increment: initial increment was not reduced"
                )
        else:
            passed = False
            verification_notes.append(f"{rule_name}: no verifier implemented")

        if passed:
            passed_checks += 1

    if passed_checks == len(applied_rule_names):
        return "passed", "; ".join(verification_notes)
    return "failed", "; ".join(verification_notes)


def _extract_static_initial_increment(lines: list[str]) -> Optional[float]:
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.upper().startswith("*STATIC"):
            continue

        if "," in stripped:
            parts = [part.strip() for part in stripped.split(",")]
            if len(parts) >= 2:
                try:
                    return float(parts[1])
                except ValueError:
                    pass

        if index + 1 >= len(lines):
            return None

        next_line = lines[index + 1].strip()
        if not next_line or next_line.startswith("*"):
            return None

        first_value = next_line.split(",")[0].strip()
        try:
            return float(first_value)
        except ValueError:
            return None

    return None
