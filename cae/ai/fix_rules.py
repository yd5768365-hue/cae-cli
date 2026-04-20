# fix_rules.py
"""
Deterministic, whitelist-based INP auto-fixes.

Safety policy:
- Only fix low-risk syntax/structure issues.
- Never infer real boundary/load/material values.
- Always keep a backup of the original input file.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FixResult:
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
    "input_missing_end_step",
    "convergence_static_increment",
}


def _normalized_issue_text(issue) -> str:
    message = getattr(issue, "message", "") or ""
    suggestion = getattr(issue, "suggestion", "") or ""
    return f"{message}\n{suggestion}".lower()


def _classify_issue_for_autofix(issue) -> Optional[str]:
    text = _normalized_issue_text(issue)
    category = (getattr(issue, "category", "") or "").lower()

    if category == "material" and "elastic" in text:
        return "material_missing_elastic"

    if category == "input_syntax":
        mentions_step_missing = (
            "*step" in text
            and ("missing" in text or "not found" in text or "未找到" in text)
            and "*end step" not in text
        )
        if mentions_step_missing:
            return "input_missing_step"

        mentions_end_step_missing = (
            "*end step" in text
            and (
                "missing" in text
                or "not found" in text
                or "not closed" in text
                or "未找到" in text
                or "未闭合" in text
            )
        )
        if mentions_end_step_missing:
            return "input_missing_end_step"

    if category == "convergence" and (
        "increment" in text or "static" in text or "initial step" in text
    ):
        return "convergence_static_increment"

    return None


def get_safe_autofix_rule(issue) -> Optional[str]:
    """Return the safe auto-fix rule name for an issue, if one is allowed."""
    return _classify_issue_for_autofix(issue)


def get_safe_autofixable_issues(issues: list) -> list:
    """Return only issues that match the explicit safe whitelist."""
    return [issue for issue in issues if get_safe_autofix_rule(issue) in SAFE_AUTOFIX_RULES]


def fix_inp(
    inp_file: Path,
    issues: list,
    results_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> FixResult:
    """Apply only deterministic safe auto-fixes from the whitelist."""
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
    output_dir.mkdir(parents=True, exist_ok=True)

    backup_path = output_dir / f"{inp_file.stem}_original{inp_file.suffix}"
    fixed_path = output_dir / f"{inp_file.stem}_fixed{inp_file.suffix}"
    shutil.copy2(inp_file, backup_path)

    original_text = inp_file.read_text(encoding="utf-8")
    lines = original_text.splitlines()

    fixes_applied: list[str] = []
    applied_rules: list[str] = []

    for issue in safe_issues:
        rule_name = _classify_issue_for_autofix(issue)
        fix: Optional[str] = None

        if rule_name == "material_missing_elastic":
            fix = _safe_fix_missing_elastic(lines, issue, results_dir)
        elif rule_name == "input_missing_step":
            fix = _safe_fix_missing_step(lines)
        elif rule_name == "input_missing_end_step":
            fix = _safe_fix_missing_end_step(lines)
        elif rule_name == "convergence_static_increment":
            fix = _safe_fix_convergence_issues(lines)

        if fix:
            fixes_applied.append(fix)
            if rule_name:
                applied_rules.append(rule_name)

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
        applied_rule_names=applied_rules,
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
        upper = line.strip().upper()
        if not upper.startswith("*MATERIAL"):
            continue
        if f"NAME={material_name}".upper() in upper or f"NAME = {material_name}".upper() in upper:
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
    if any(line.strip().upper().startswith("*STEP") for line in lines):
        return None

    if lines and lines[-1].strip():
        lines.append("")
    lines.extend([
        "*STEP",
        "*STATIC",
        "0.1, 1.0",
        "*END STEP",
    ])
    return "Added a minimal *STEP/*STATIC block"


def _safe_fix_missing_end_step(lines: list[str]) -> Optional[str]:
    step_count = sum(1 for line in lines if line.strip().upper().startswith("*STEP"))
    end_step_count = sum(1 for line in lines if line.strip().upper().startswith("*END STEP"))

    if step_count == 0 or end_step_count >= step_count:
        return None

    if lines and lines[-1].strip():
        lines.append("")
    lines.append("*END STEP")
    return f"Added missing *END STEP ({end_step_count} -> {end_step_count + 1})"


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
            except ValueError:
                return None
            new_val = current_val * 0.1
            parts[1] = str(new_val)
            lines[static_idx] = ", ".join(parts)
            return f"Reduced inline *STATIC initial increment: {current_val} -> {new_val}"

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
            for pattern in (
                r"\bto\s+material\s+([A-Za-z0-9_.-]+)",
                r"\bfor\s+material\s+([A-Za-z0-9_.-]+)",
                r"\bmaterial\s+([A-Za-z0-9_.-]+)\s+(?:has|is|was|with|:)",
                r"\bmaterial\s+name\s*[=:]\s*([A-Za-z0-9_.-]+)",
            ):
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    return match.group(1)

    suggestion = getattr(issue, "suggestion", "") or ""
    if suggestion:
        for pattern in (
            r"NAME\s*=\s*([A-Za-z0-9_.-]+)",
            r"(?:material|材料)\s+([A-Za-z0-9_.-]+)",
        ):
            match = re.search(pattern, suggestion, re.IGNORECASE)
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
        elif rule_name == "input_missing_end_step":
            step_count = sum(1 for line in fixed_lines if line.strip().upper().startswith("*STEP"))
            end_step_count = sum(1 for line in fixed_lines if line.strip().upper().startswith("*END STEP"))
            passed = step_count > 0 and end_step_count >= step_count
            verification_notes.append(
                "input_missing_end_step: *STEP/*END STEP pairs are balanced"
                if passed
                else "input_missing_end_step: *END STEP is still missing"
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
