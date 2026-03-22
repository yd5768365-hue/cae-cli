"""
Inp 模块 — Abaqus/CalculiX .inp 文件解析与修改

基于 cae-master 的 Block 解析思路，支持：
  - 解析 .inp 文件为 Block 列表（保留原始行位置）
  - 按关键词/名称精确定位修改
  - 保留原始格式（注释、空行、结构）重新生成
  - AI 辅助修改建议

关键词定义来源：kw_list.json（从 cae-master kw_list.xml 转换）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

__all__ = [
    "Block",
    "InpParser",
    "InpModifier",
    "InpFile",
    "load_kw_list",
    "load_kw_tree",
    "list_keywords",
    "get_keyword_info",
    "validate_block",
    "suggest_inp_modifications",
    "replace_values",
    # 模型构建器
    "ModelBuilder",
    "CantileverBeam",
    "FlatPlate",
    # 载荷步关键词
    "Amplitude",
    "Cload",
    "Dload",
    "Boundary",
    "Coupling",
    # 方程约束
    "Equation",
    "EquationTerm",
    "EquationFactory",
]

# ------------------------------------------------------------------ #
# 数据结构
# ------------------------------------------------------------------ #

# 懒加载 kw_list
_kw_list: Optional[dict] = None


def load_kw_list() -> dict:
    """加载关键词定义列表（kw_list.json）。"""
    global _kw_list
    if _kw_list is None:
        kw_path = Path(__file__).parent / "kw_list.json"
        with open(kw_path, encoding="utf-8") as f:
            _kw_list = json.load(f)
    return _kw_list


@dataclass
class Block:
    """
    关键词块，保留原始 INP 文本。

    Attributes:
        keyword_name: 关键词名称，如 "*BOUNDARY", "*STEP"
        comments: 注释行列表（含 "**" 前缀）
        lead_line: 关键词定义行（含参数）
        data_lines: 数据行列表
        line_range: 原始文件中的行范围 (start, end)，用于格式保留
    """

    keyword_name: str
    comments: list[str] = field(default_factory=list)
    lead_line: str = ""
    data_lines: list[str] = field(default_factory=list)
    line_range: tuple[int, int] = field(default_factory=lambda: (0, 0), repr=False)

    # 解析后的参数 {参数名: 值}
    _params: dict[str, str] = field(default_factory=dict, repr=False)

    def get_inp_code(self) -> list[str]:
        """重新生成 INP 代码行。"""
        lines = []
        lines.extend(self.comments)
        lines.append(self.lead_line)
        lines.extend(self.data_lines)
        return lines

    def get_param(self, name: str) -> Optional[str]:
        """获取关键词参数值（不区分大小写）。"""
        return self._params.get(name.upper())

    def set_param(self, name: str, value: str) -> None:
        """设置关键词参数值。"""
        name_upper = name.upper()
        # 匹配 NAME=value 或 NAME= value 或 NAME value
        pattern = rf"({re.escape(name)})[\s=].*?(?=,|\s*?$|\*)"
        if re.search(pattern, self.lead_line, re.IGNORECASE):
            self.lead_line = re.sub(
                pattern,
                f"{name}={value}",
                self.lead_line,
                flags=re.IGNORECASE,
            )
        else:
            sep = "," if not self.lead_line.rstrip().endswith(",") else ""
            self.lead_line = f"{self.lead_line}{sep} {name}={value}"
        self._params[name_upper] = value

    def update_data_line(self, index: int, new_line: str) -> None:
        """更新指定索引的数据行。"""
        if 0 <= index < len(self.data_lines):
            self.data_lines[index] = new_line

    def get_data_summary(self) -> str:
        """获取数据行摘要（用于 AI 分析）。"""
        if not self.data_lines:
            return "(无数据)"
        n = len(self.data_lines)
        sample = self.data_lines[:3]
        preview = ", ".join(l.strip()[:30] for l in sample)
        return f"{n}行: {preview}" + (" ..." if n > 3 else "")


# ------------------------------------------------------------------ #
# 解析器
# ------------------------------------------------------------------ #

# 关键词行匹配：*KEYWORD 或 *KEYWORD,param1=value,param2=value
_KEYWORD_RE = re.compile(r"^\*[\w\s-]+")


class InpParser:
    """
    .inp 文件解析器。

    解析流程：
      1. read_lines()       — 递归读取文件（含 *INCLUDE）
      2. split_on_blocks()  — 分割为 Block 列表（记录行范围）
      3. parse_params()      — 解析每块的关键词参数

    Usage:
        parser = InpParser()
        blocks = parser.parse("model.inp")
        for block in blocks:
            print(block.keyword_name, block.get_param("NAME"))
    """

    def __init__(self):
        self.keyword_blocks: list[Block] = []
        self._source_lines: list[str] = []

    def parse(self, inp_file: Path) -> list[Block]:
        """解析 .inp 文件，返回 Block 列表。"""
        if not inp_file.exists():
            raise FileNotFoundError(f"文件不存在: {inp_file}")

        with open(inp_file, encoding="utf-8", errors="ignore") as f:
            self._source_lines = f.readlines()

        inp_doc = [line.rstrip() for line in self._source_lines]
        self.split_on_blocks(inp_doc)
        for block in self.keyword_blocks:
            self._parse_params(block)
        return self.keyword_blocks

    def parse_string(self, inp_text: str) -> list[Block]:
        """解析 INP 文本字符串。"""
        self._source_lines = inp_text.splitlines(keepends=True)
        inp_doc = [line.rstrip() for line in self._source_lines]
        self.split_on_blocks(inp_doc)
        for block in self.keyword_blocks:
            self._parse_params(block)
        return self.keyword_blocks

    def _read_lines(self, inp_file: Path) -> list[str]:
        """递归读取 INP 文件及 *INCLUDE 文件。"""
        lines = []
        with open(inp_file, encoding="utf-8", errors="ignore") as f:
            for raw_line in f:
                line = raw_line.rstrip()
                lines.append(line)
                if re.match(r"^\s*\*INCLUDE", line, re.IGNORECASE):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        inc_path = Path(inp_file.parent) / parts[1].strip()
                        if inc_path.exists():
                            lines.extend(self._read_lines(inc_path))
        return lines

    def split_on_blocks(self, inp_doc: list[str]) -> None:
        """将 INP 文档分割为关键词块列表（记录行范围）。"""
        self.keyword_blocks = []
        i = 0
        n = len(inp_doc)

        while i < n:
            match = _KEYWORD_RE.match(inp_doc[i])
            if match is not None:
                keyword_name = match.group(0).strip()
                block_start = i  # 0-based

                # 前置注释
                comments = []
                counter = 0
                while i - counter - 1 >= 0 and inp_doc[i - counter - 1].startswith("**"):
                    counter += 1
                    comments.insert(0, inp_doc[i - counter])

                # Lead line（支持多行逗号续接）
                lead_line = inp_doc[i].rstrip()
                j = i + 1
                while lead_line.endswith(","):
                    if j >= n:
                        break
                    lead_line = lead_line + " " + inp_doc[j].rstrip()
                    j += 1

                i = j
                start = i

                # 数据行直到下一关键词
                while i < n:
                    if _KEYWORD_RE.match(inp_doc[i]):
                        i -= 1
                        break
                    i += 1

                end = i if i < n else n - 1
                if end < start:
                    end = start

                data_lines = inp_doc[start : end + 1]
                block_end = start + len(data_lines) - 1

                block = Block(
                    keyword_name=keyword_name.upper(),
                    comments=comments,
                    lead_line=lead_line,
                    data_lines=data_lines,
                    line_range=(block_start, block_end + len(comments)),
                )
                self.keyword_blocks.append(block)

            i += 1

    def _parse_params(self, block: Block) -> None:
        """从 lead_line 解析关键词参数，存入 block._params。"""
        line = block.lead_line.strip().lstrip("*")
        if line.endswith(","):
            line = line[:-1]

        parts = line.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            eq_match = re.match(r"^([\w-]+)\s*=\s*(.*)$", part, re.IGNORECASE)
            if eq_match:
                key = eq_match.group(1).upper()
                val = eq_match.group(2).strip()
                block._params[key] = val


# ------------------------------------------------------------------ #
# 修改器
# ------------------------------------------------------------------ #

_NAME_KEYWORDS = {
    "*MATERIAL", "*STEP", "*BOUNDARY", "*LOAD", "*CLOAD", "*DLOAD",
    "*ELSET", "*NSET", "*SURFACE", "*AMPLITUDE", "*PART", "*ASSEMBLY",
    "*INSTANCE", "*SOLID SECTION", "*BEAM SECTION", "*SHELL SECTION",
    "*NODE", "*ELEMENT",
}


class InpModifier:
    """
    .inp 文件修改器。

    支持按关键词类型 + 参数条件精确定位修改，
    保留原始格式不变。

    Usage:
        mod = InpModifier("model.inp")
        mod.update_blocks(
            keyword="*MATERIAL",
            params={"NAME": "STEEL", "E": "210000"},
            name="OLD_MAT",
        )
        mod.write("model_modified.inp")
    """

    def __init__(self, inp_file: Optional[Path] = None):
        self.blocks: list[Block] = []
        self._source_text: list[str] = []
        if inp_file is not None:
            self.load(inp_file)

    def load(self, inp_file: Path) -> None:
        """加载 .inp 文件（保留原始文本用于格式生成）。"""
        parser = InpParser()
        self.blocks = parser.parse(inp_file)
        with open(inp_file, encoding="utf-8", errors="ignore") as f:
            self._source_text = f.read().splitlines()

    def find_blocks(
        self,
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        name_param: str = "NAME",
    ) -> list[Block]:
        """查找匹配的 Block。"""
        results = []
        for block in self.blocks:
            if keyword is not None and block.keyword_name.upper() != keyword.upper():
                continue
            if name is not None:
                block_name = block.get_param(name_param)
                if block_name is None or block_name.upper() != name.upper():
                    continue
            results.append(block)
        return results

    def find_block(
        self,
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        name_param: str = "NAME",
    ) -> Optional[Block]:
        """查找单个匹配的 Block。"""
        results = self.find_blocks(keyword=keyword, name=name, name_param=name_param)
        return results[0] if results else None

    def update_blocks(
        self,
        keyword: str,
        params: Optional[dict[str, str]] = None,
        name: Optional[str] = None,
        name_param: str = "NAME",
        data_transformer: Optional[callable] = None,
    ) -> int:
        """更新所有匹配的 Block。"""
        blocks = self.find_blocks(keyword=keyword, name=name, name_param=name_param)
        for block in blocks:
            if params:
                for k, v in params.items():
                    block.set_param(k, v)
            if data_transformer is not None:
                block.data_lines = data_transformer(block.data_lines)
        return len(blocks)

    def insert_block(
        self,
        block: Block,
        after_keyword: Optional[str] = None,
        after_name: Optional[str] = None,
        at_end: bool = False,
    ) -> None:
        """插入新的 Block。"""
        if at_end:
            self.blocks.append(block)
            return

        insert_idx = len(self.blocks)
        for i, b in enumerate(self.blocks):
            if after_keyword is not None and b.keyword_name.upper() != after_keyword.upper():
                continue
            if after_name is not None:
                bname = b.get_param("NAME")
                if bname is None or bname.upper() != after_name.upper():
                    continue
            insert_idx = i + 1

        self.blocks.insert(insert_idx, block)

    def delete_blocks(
        self,
        keyword: Optional[str] = None,
        name: Optional[str] = None,
        name_param: str = "NAME",
    ) -> int:
        """删除所有匹配的 Block。"""
        to_delete = self.find_blocks(keyword=keyword, name=name, name_param=name_param)
        for b in to_delete:
            self.blocks.remove(b)
        return len(to_delete)

    def generate(self) -> list[str]:
        """简单生成（不保留原始格式）。"""
        lines = []
        for block in self.blocks:
            lines.extend(block.get_inp_code())
        return lines

    def generate_preserving(self) -> list[str]:
        """
        保留原始格式生成。

        策略：
        1. 收集所有被修改过的 block，用新内容替换
        2. 未修改的 block 保留原始行
        3. 块之间的空白行从原文保留
        """
        # 找出修改/新增/删除的 block
        modified_blocks: set[int] = set()
        for i, b in enumerate(self.blocks):
            if getattr(b, "_modified", False):
                modified_blocks.add(i)

        # 用 Block 内容覆盖对应行范围
        result: list[Optional[str]] = [None] * len(self._source_text)

        for i, b in enumerate(self.blocks):
            start, end = b.line_range
            # 确保范围有效
            start = max(0, start)
            end = min(len(self._source_text) - 1, end)
            if start > end:
                start = end

            block_lines = b.get_inp_code()
            for j, line in enumerate(block_lines):
                if start + j < len(result):
                    result[start + j] = line

        # 移除 None 的位置（即被删除的 block 区域），
        # 保留非 None 的原始行
        output: list[str] = []
        i = 0
        n = len(result)
        while i < n:
            if result[i] is not None:
                output.append(result[i])
            else:
                # 保留原始行（非空且非已删除块的行）
                orig = self._source_text[i].rstrip()
                if orig.strip():
                    output.append(orig)
            i += 1

        # 清理连续的空行（最多保留2个）
        return _clean_empty_lines(output)

    def write(self, output_path: Path, preserve_format: bool = True) -> None:
        """将修改后的 INP 写入文件。"""
        lines = self.generate_preserving() if preserve_format else self.generate()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")


def _clean_empty_lines(lines: list[str]) -> list[str]:
    """清理连续空行，最多保留2个。"""
    result: list[str] = []
    empty_streak = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            empty_streak += 1
            if empty_streak <= 2:
                result.append(line)
        else:
            empty_streak = 0
            result.append(line)
    return result


# ------------------------------------------------------------------ #
# Phase 3: kw_list 参数校验
# ------------------------------------------------------------------ #

@dataclass
class ValidationIssue:
    """校验问题。"""
    severity: str  # "error" | "warning" | "info"
    keyword: str
    parameter: Optional[str]
    message: str


def validate_block(block: Block) -> list[ValidationIssue]:
    """
    校验单个 Block 是否符合 kw_list.json 定义。

    Returns:
        问题列表（空=通过）
    """
    kw_list = load_kw_list()
    issues: list[ValidationIssue] = []
    kw_def = kw_list.get(block.keyword_name)

    if kw_def is None:
        issues.append(ValidationIssue(
            severity="warning",
            keyword=block.keyword_name,
            parameter=None,
            message=f"未知关键词 '{block.keyword_name}'",
        ))
        return issues

    for arg in kw_def.get("arguments", []):
        if arg.get("required") and not block.get_param(arg["name"]):
            issues.append(ValidationIssue(
                severity="error",
                keyword=block.keyword_name,
                parameter=arg["name"],
                message=f"必填参数 '{arg['name']}' 缺失",
            ))

    return issues


def validate_inp(mod: InpModifier) -> list[ValidationIssue]:
    """
    校验整个 INP 文件。

    Returns:
        所有问题列表
    """
    all_issues: list[ValidationIssue] = []
    for block in mod.blocks:
        all_issues.extend(validate_block(block))
    return all_issues


# ------------------------------------------------------------------ #
# Phase 3: AI 辅助修改建议
# ------------------------------------------------------------------ #

@dataclass
class ModificationSuggestion:
    """修改建议。"""
    category: str  # "material" | "mesh" | "boundary" | "geometry" | "step"
    severity: str  # "high" | "medium" | "low"
    target_keyword: str
    target_name: Optional[str]
    action: str  # "modify" | "insert" | "delete"
    params: Optional[dict[str, str]] = None
    data_transform: Optional[str] = None  # 描述数据修改
    reason: str = ""


@dataclass
class SuggestResult:
    success: bool
    suggestions: list[ModificationSuggestion]
    summary: str = ""
    error: Optional[str] = None


def suggest_inp_modifications(
    inp_file: Path,
    diagnose_issues: Optional[list] = None,
    client=None,
    *,
    stream: bool = True,
) -> SuggestResult:
    """
    基于诊断问题和 AI 分析，生成 INP 修改建议。

    Args:
        inp_file: .inp 文件路径
        diagnose_issues: 可选的诊断问题列表（来自 DiagnoseResult）
        client: LLMClient 实例（可选，不提供则只用规则建议）
        stream: 是否流式输出

    Returns:
        SuggestResult — 修改建议列表
    """
    try:
        mod = InpModifier(inp_file)
    except Exception as exc:
        return SuggestResult(success=False, suggestions=[], error=str(exc))

    suggestions: list[ModificationSuggestion] = []

    # ---- 规则建议（无需 AI）----
    suggestions.extend(_rule_based_suggestions(mod))

    # ---- kw_list 校验建议 ----
    issues = validate_inp(mod)
    for issue in issues:
        if issue.severity == "error":
            suggestions.append(ModificationSuggestion(
                category="validation",
                severity="high",
                target_keyword=issue.keyword,
                target_name=mod.find_block(keyword=issue.keyword).get_param("NAME")
                    if mod.find_block(keyword=issue.keyword) else None,
                action="modify",
                params={issue.parameter: "<值>"},
                reason=f"kw_list 校验失败: {issue.message}",
            ))

    # ---- AI 建议（如果有 client）----
    if client is not None and hasattr(client, "complete_streaming"):
        ai_suggestions = _ai_suggestions(mod, suggestions, client, stream=stream)
        suggestions.extend(ai_suggestions)

    return SuggestResult(
        success=True,
        suggestions=suggestions,
        summary=f"共生成 {len(suggestions)} 条修改建议",
    )


def _rule_based_suggestions(mod: InpModifier) -> list[ModificationSuggestion]:
    """基于规则的修改建议。"""
    suggestions: list[ModificationSuggestion] = []

    # 检查材料是否缺少密度（影响动力学分析）
    for block in mod.blocks:
        if block.keyword_name == "*MATERIAL":
            mat_name = block.get_param("NAME")
            has_density = any(
                b.keyword_name == "*DENSITY"
                and b.get_param("MATERIAL") == mat_name
                for b in mod.blocks
            )
            has_elastic = any(
                b.keyword_name == "*ELASTIC"
                and b.get_param("MATERIAL") == mat_name
                for b in mod.blocks
            )
            if has_elastic and not has_density:
                suggestions.append(ModificationSuggestion(
                    category="material",
                    severity="medium",
                    target_keyword="*DENSITY",
                    target_name=None,
                    action="insert",
                    params={"MATERIAL": mat_name, "DENSITY": "<密度>"},
                    reason=f"材料 '{mat_name}' 缺少密度定义",
                ))

        # 检查 STEP 是否缺少 *STATIC 或 *DYNAMIC
        if block.keyword_name == "*STEP":
            step_name = block.get_param("NAME") or "STEP-1"
            has_procedure = any(
                b.keyword_name in ("*STATIC", "*DYNAMIC", "*BUCKLE", "*FREQUENCY")
                for b in mod.blocks
            )
            if not has_procedure:
                suggestions.append(ModificationSuggestion(
                    category="step",
                    severity="high",
                    target_keyword="*STATIC",
                    target_name=None,
                    action="insert",
                    params={"STEEL": "STEEL"},
                    reason=f"STEP '{step_name}' 缺少分析procedure（*STATIC/*DYNAMIC）",
                ))

        # 检查边界条件是否完整
        if block.keyword_name == "*BOUNDARY":
            bc_name = block.get_param("NAME")
            nset = block.get_param("NSET")
            if not nset:
                suggestions.append(ModificationSuggestion(
                    category="boundary",
                    severity="medium",
                    target_keyword="*BOUNDARY",
                    target_name=bc_name,
                    action="modify",
                    params={"NSET": "<节点集名称>"},
                    reason="边界条件未指定节点集(NSET)",
                ))

    return suggestions


def _ai_suggestions(
    mod: InpModifier,
    rule_suggestions: list[ModificationSuggestion],
    client,
    stream: bool,
) -> list[ModificationSuggestion]:
    """利用 AI 生成修改建议。"""
    suggestions: list[ModificationSuggestion] = []

    # 组装 INP 摘要（用于 prompt）
    inp_summary = _build_inp_summary(mod)

    # 组装已有规则建议（避免重复）
    rule_text = "\n".join(
        f"- [{s.severity}] {s.action} {s.target_keyword}"
        + (f" NAME={s.target_name}" if s.target_name else "")
        + f": {s.reason}"
        for s in rule_suggestions
    ) or "无"

    prompt = f"""你是 CAE 有限元分析专家。基于以下 INP 文件内容和已有的规则建议，
为用户生成针对该模型的优化修改建议。

## INP 文件摘要
{inp_summary}

## 已有的规则建议
{rule_text}

## 输出要求
请分析以上内容，生成 3-5 条具体的 INP 修改建议。每条建议格式如下：

[修改N]
category: <material|mesh|boundary|geometry|step>
keyword: <关键词>
name: <NAME值或无>
action: <modify|insert|delete>
params: <KEY1=VALUE1,KEY2=VALUE2 或无>
reason: <修改原因，一句话>

请确保建议：
1. 具体且可执行（关键词+参数名+值）
2. 基于当前模型的实际内容
3. 不重复已有的规则建议

只输出建议，不要解释。"""

    try:
        if stream and hasattr(client, "complete_streaming"):
            response = ""
            for chunk in client.complete_streaming(prompt):
                response += chunk
        elif hasattr(client, "complete"):
            response = client.complete(prompt)
        else:
            return suggestions

        # 解析 AI 响应，提取建议
        suggestions = _parse_ai_suggestions(response)
    except Exception:
        pass  # AI 失败时只返回规则建议

    return suggestions


def _build_inp_summary(mod: InpModifier) -> str:
    """构建 INP 文件摘要（用于 AI prompt）。"""
    lines = []
    kw_count: dict[str, int] = {}
    for b in mod.blocks:
        kw_count[b.keyword_name] = kw_count.get(b.keyword_name, 0) + 1

    lines.append("关键词统计:")
    for kw, cnt in sorted(kw_count.items()):
        lines.append(f"  {kw}: {cnt}个")

    # 重点材料摘要
    lines.append("\n材料定义:")
    for b in mod.blocks:
        if b.keyword_name == "*MATERIAL":
            name = b.get_param("NAME") or "(unnamed)"
            lines.append(f"  - {name}")
            for prop_kw in ("*ELASTIC", "*DENSITY", "*PLASTIC", "*EXPANSION"):
                prop = mod.find_block(keyword=prop_kw, name=name)
                if prop:
                    lines.append(f"    包含: {prop_kw}")

    # 载荷和边界条件
    lines.append("\n载荷/边界条件:")
    for b in mod.blocks:
        if b.keyword_name in ("*BOUNDARY", "*CLOAD", "*DLOAD", "*LOAD"):
            name = b.get_param("NAME") or "(unnamed)"
            nset = b.get_param("NSET") or b.get_param("ELSET") or "(未指定)"
            lines.append(f"  {b.keyword_name} {name} (集={nset})")

    # STEP 信息
    lines.append("\n分析步骤:")
    for b in mod.blocks:
        if b.keyword_name in ("*STATIC", "*DYNAMIC", "*BUCKLE", "*FREQUENCY"):
            name = b.get_param("NAME") or "(unnamed)"
            lines.append(f"  {b.keyword_name} {name}")

    return "\n".join(lines)


def _parse_ai_suggestions(response: str) -> list[ModificationSuggestion]:
    """从 AI 响应中解析出 ModificationSuggestion 列表。"""
    suggestions: list[ModificationSuggestion] = []

    # 简单的正则解析 [修改N] ... category: ... 等格式
    import re as _re

    pattern = r"\[修改(\d+)\]\s*category:\s*(\w+)\s*keyword:\s*(\*\w+)\s*name:\s*(\S+|无)\s*action:\s*(\w+)\s*params:\s*(.*?)\s*reason:\s*(.*?)(?=\[修改|$)"
    matches = _re.findall(pattern, response, _re.DOTALL)

    for match in matches:
        _, category, keyword, name, action, params_str, reason = match
        name_val = None if name == "无" else name
        params = {}
        if params_str.strip() and params_str.strip() != "无":
            for p in params_str.split(","):
                p = p.strip()
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k.strip()] = v.strip()

        suggestions.append(ModificationSuggestion(
            category=category,
            severity="medium",
            target_keyword=keyword,
            target_name=name_val,
            action=action,
            params=params if params else None,
            reason=reason.strip(),
        ))

    return suggestions


# ------------------------------------------------------------------ #
# 辅助函数
# ------------------------------------------------------------------ #

def replace_values(
    lines: list[str],
    column_key: str,
    new_value: float,
    columns: Optional[dict[str, int]] = None,
) -> list[str]:
    """
    替换数据行中的值。

    Args:
        lines: 数据行列表
        column_key: 列名（如 "E" 代表弹性模量）
        new_value: 新值
        columns: {列名: 索引} 映射，默认使用常见 INP 格式

    Returns:
        替换后的行列表
    """
    col_idx = _get_column_index(column_key, columns)
    result = []
    for line in lines:
        if not line.strip() or line.strip().startswith("**"):
            result.append(line)
            continue
        numbers = re.findall(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", line)
        if len(numbers) > col_idx:
            parts = re.split(r"([-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)", line)
            count = 0
            new_parts = []
            for part in parts:
                if re.match(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", part):
                    if count == col_idx:
                        new_parts.append(str(new_value))
                    else:
                        new_parts.append(part)
                    count += 1
                else:
                    new_parts.append(part)
            result.append("".join(new_parts))
        else:
            result.append(line)
    return result


def _get_column_index(column_key: str, columns: Optional[dict[str, int]]) -> int:
    """获取列索引。"""
    if columns and column_key in columns:
        return columns[column_key]
    COMMON_COLUMNS = {
        "E": 0,
        "NU": 1,
        "RHO": 2,
    }
    return COMMON_COLUMNS.get(column_key.upper(), 0)


# ------------------------------------------------------------------ #
# kw_tree — 关键词层级导航
# ------------------------------------------------------------------ #

_kw_tree: Optional[dict] = None


def load_kw_tree() -> dict:
    """加载关键词层级定义（kw_tree.json）。"""
    global _kw_tree
    if _kw_tree is None:
        kw_path = Path(__file__).parent / "kw_tree.json"
        with open(kw_path, encoding="utf-8") as f:
            _kw_tree = json.load(f)
    return _kw_tree


def list_keywords(category: Optional[str] = None) -> list[str]:
    """
    列出关键词。

    Args:
        category: 可选，分类名称（如 "Mesh", "Properties", "Step"）

    Returns:
        关键词列表
    """
    tree = load_kw_tree()
    if category is None:
        # 返回所有关键词
        all_kw: list[str] = []
        _collect_keywords(tree.get("Collections", {}), all_kw)
        return all_kw

    colls = tree.get("Collections", {})
    if category not in colls:
        return []
    return _flatten_collection(colls[category])


def _collect_keywords(node: dict, out: list[str]) -> None:
    """递归收集所有关键词。"""
    if "keywords" in node:
        out.extend(node["keywords"])
    if "nested" in node:
        for v in node["nested"].values():
            if isinstance(v, dict):
                _collect_keywords(v, out)
            elif isinstance(v, list):
                out.extend(v)


def _flatten_collection(node: dict) -> list[str]:
    """将 collection 节点展平为关键词列表。"""
    result: list[str] = []
    if "keywords" in node:
        result.extend(node["keywords"])
    if "nested" in node:
        for v in node["nested"].values():
            if isinstance(v, dict):
                result.extend(_flatten_collection(v))
            elif isinstance(v, list):
                result.extend(v)
    if "Section" in node and isinstance(node["Section"], dict):
        result.extend(_flatten_collection(node["Section"]))
    if "Analysis type" in node and isinstance(node["Analysis type"], dict):
        result.extend(_flatten_collection(node["Analysis type"]))
    if "Field Output" in node and isinstance(node["Field Output"], dict):
        result.extend(_flatten_collection(node["Field Output"]))
    if "Load & BC" in node and isinstance(node["Load & BC"], dict):
        result.extend(_flatten_collection(node["Load & BC"]))
    if "Change" in node and isinstance(node["Change"], dict):
        result.extend(_flatten_collection(node["Change"]))
    return result


def get_keyword_info(keyword: str) -> dict:
    """
    获取关键词详细信息。

    Returns:
        {"keyword": "...", "args": [...], "category": "...", "parent": [...]}
    """
    kw_list = load_kw_list()
    tree = load_kw_tree()
    kw_upper = keyword.upper()

    # 从 kw_list 获取参数定义
    kw_def = kw_list.get(keyword, kw_list.get(kw_upper, {}))
    args = []
    for arg in kw_def.get("arguments", []):
        args.append({
            "name": arg.get("name"),
            "form": arg.get("form"),
            "required": arg.get("required", False),
            "options": arg.get("options"),
            "use": arg.get("use"),
        })

    # 从 kw_tree 获取分类路径
    category_path: list[str] = []
    _find_keyword_path(tree.get("Collections", {}), kw_upper, [], category_path)

    return {
        "keyword": keyword,
        "args": args,
        "category": category_path[0] if category_path else None,
        "path": category_path,
        "known": kw_upper in kw_list,
    }


def _find_keyword_path(
    node: dict,
    target: str,
    path: list[str],
    result: list[str],
) -> bool:
    """递归查找关键词在 tree 中的路径。"""
    for name, content in node.items():
        current_path = path + [name]
        if isinstance(content, dict):
            if "keywords" in content and target in content["keywords"]:
                result[:] = current_path
                return True
            if "nested" in content:
                if _find_keyword_path(content["nested"], target, current_path, result):
                    return True
            # 递归检查 Section / Analysis type 等子节点
            for sub_key in ("Section", "Analysis type", "Field Output", "Load & BC", "Change"):
                if sub_key in content and isinstance(content[sub_key], dict):
                    if _find_keyword_path({sub_key: content[sub_key]}, target, current_path, result):
                        return True
    return False


# ------------------------------------------------------------------ #
# 载荷步关键词导入
# ------------------------------------------------------------------ #

from cae.inp.step_keywords import Amplitude, Cload, Dload, Boundary, Coupling
from cae.inp.model_builder import ModelBuilder, CantileverBeam, FlatPlate
from cae.inp.equation import Equation, EquationTerm, EquationFactory
