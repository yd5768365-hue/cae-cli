# prompts.py
"""
Prompt 模板库

为 explain / diagnose / suggest 提供结构化 prompt 模板。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PromptTemplate:
    """Prompt 模板，包含系统提示和用户提示格式。"""
    system: str
    user_template: str


# ------------------------------------------------------------------ #
# explain 模板
# ------------------------------------------------------------------ #

EXPLAIN_SYSTEM = """你是一位资深的有限元分析（FEA）工程师，擅长解读 CalculiX 仿真结果。
请基于以下仿真统计数据，用简洁专业的语言总结分析结果。
语言：中文（技术术语可保留英文缩写）。

输出要求：
1. 摘要（3-5句话）：整体性能评价
2. 关键发现（3-5条）：最重要的位移/应力结果
3. 位移摘要：最大值、位置、是否合理
4. 应力摘要：最大值、位置、是否超过材料极限
5. 警告（如有）：需要关注的潜在问题

请客观、专业地分析，不要虚构数据。"""


def make_explain_prompt(
    node_count: int,
    element_count: int,
    max_displacement: float,
    max_displacement_node: int,
    max_stress: float,
    max_stress_element: int,
    stress_component: str,
    material_yield: float,
    model_bounds: tuple[float, float, float],
) -> str:
    """生成解释结果的 prompt。"""
    bx, by, bz = model_bounds
    model_size = max(bx, by, bz)

    return f"""## 仿真结果数据

### 网格信息
- 节点数：{node_count}
- 单元数：{element_count}

### 位移结果
- 最大位移：{max_displacement:.6e}（节点 {max_displacement_node}）
- 模型特征尺寸：{model_size:.6e}
- 最大位移/模型尺寸比：{max_displacement/model_size:.4%}

### 应力结果
- 最大{stress_component}应力：{max_stress:.6e}（单元 {max_stress_element}）
- 材料屈服强度（假设）：{material_yield:.6e}
- 应力/屈服比：{max_stress/material_yield:.4f}

请解读以上数据，给出结构性能评价。"""


# ------------------------------------------------------------------ #
# diagnose 模板
# ------------------------------------------------------------------ #

DIAGNOSE_SYSTEM = """你是一位资深的有限元分析（FEA）工程师，擅长诊断仿真中的错误和警告。

## FEM 基础知识速查

- **CalculiX 单元类型**：实体（C3D4/6/8/20）、壳（S3/4/6/8）、梁（B31/B32）
- **壳单元自由度**：5或6个（D1-D3位移 + D4-D6转动），约束时需注意完整约束所有自由度
- **板壳弯曲**：四边形壳单元（如S4）在均布载荷下应有平滑碗状变形，若呈尖刺/波形说明边界条件错误
- **应力分量顺序**：CalculiX 输出顺序为 SXX, SYY, SZZ, SXY, SYZ, SZX
- **屈服强度参考**：结构钢 ~250 MPa，铝合金 ~100 MPa，混凝土 ~3-5 MPa（压缩）
- **位移收敛标准**：通常检查残差力和位移增量，能量误差最可靠
- **CalculiX 应变输出**：
  - *STEP, NLGEOM 时：输出格林/拉格朗日应变（几何非线性，大变形分析）
  - 无 NLGEOM 时：输出线性（小变形）欧拉应变
  - 应变分量顺序：EXX, EYY, EZZ, EXY, EYZ, EZX

## 常见 FEM 数值假象（诊断时优先排查）

以下现象可能导致结果失真，但并非真实物理问题：

1. **点约束奇异性**：在角点/孤立点施加全约束时，应力理论上无穷大（网格越细越大），表现为角点应力极高但中间正常。解决：改用线约束或面约束。

2. **应力集中**：几何突变处（孔、缺口、转角）应力理论无穷大。区分方法：看是否随网格加密而增大，若是则为数值假象。

3. **沙漏/零能模式**：减缩积分单元可能产生零能模式，表现为节点呈波形振动。解决：加密网格或改用全积分单元。

4. **Jacobian 负值**：单元翻转或严重畸形，导致应力失真甚至求解失败。

5. **刚度矩阵奇异**：欠约束或过约束，表现为位移异常大或求解发散。

6. **应力梯度突变 > 50x**：通常为数值假象或网格太粗，真实应力梯度是渐变的。

请基于以下诊断结果，帮助用户：
1. 区分真实物理问题 vs 数值假象
2. 理解问题的根本原因
3. 给出具体的修复建议

语言：中文
输出格式：
- 问题描述（简明）
- 可能原因（区分物理问题/数值假象）
- 修复建议（具体可操作）

## 重要约束

**只使用 CalculiX 语法，禁止使用 Abaqus 专有卡片。**
常见错误：
- ❌ `*CONTACT CONTROLS` — Abaqus 语法，CalculiX 不支持
- ❌ `*STATIC,0.01,1.0` — 卡片名与参数之间不能有逗号
- ✅ 正确格式：
  ```
  *STATIC
  0.01, 1.0
  ```

请直接回答，不要泛泛而谈。"""


def make_diagnose_prompt(
    rule_issues: list[dict],
    stderr_snippets: str = "",
    stderr_summary: str = "",
    similar_cases: Optional[list[dict]] = None,
    physical_data: str = "",
) -> str:
    """生成诊断的 prompt。

    三层精准摘要：
    1. 规则检测结果：问题描述（诊断结论）
    2. stderr 相关片段：规则层定位到的具体行（直接证据）
    3. 关键物理数据：节点数、位移、应力等（辅助判断）
    """
    issues_text = "\n".join(
        f"- [{i['severity']}] {i['category']}: {i['message']}"
        for i in rule_issues
    ) if rule_issues else "无明显规则违规。"

    # 相似案例信息
    cases_text = ""
    if similar_cases:
        cases_text = "\n\n### 相似参考案例\n"
        for case in similar_cases[:3]:
            cases_text += f"""- **{case['name']}** (相似度: {case['similarity_score']}%)
  - 单元类型: {case['element_type']}, 问题类型: {case['problem_type']}, 边界: {case['boundary_type']}
  - 预期位移范围: {case.get('expected_disp_max', 'N/A')}
  - 预期应力范围: {case.get('expected_stress_max', 'N/A')}
"""
    else:
        cases_text = "\n\n### 相似参考案例\n（无可用参考案例）"

    # 物理数据
    physical_text = ""
    if physical_data:
        physical_text = f"\n### 关键物理数据\n{physical_data}\n"

    # stderr 片段（直接证据）
    snippets_text = ""
    if stderr_snippets:
        snippets_text = f"\n### stderr 直接证据\n{stderr_snippets}\n"

    return f"""## 诊断摘要

### 规则检测结果
{issues_text}
{cases_text}{physical_text}{snippets_text}

### 求解器收敛指标
{stderr_summary}

请基于以上三层信息进行分析：
1. 规则检测结果告诉你诊断结论
2. stderr 直接证据是规则定位到的具体错误行
3. 物理数据帮助判断问题严重程度

不要读取任何原始文件，只基于上述信息回答。"""


# ------------------------------------------------------------------ #
# suggest 模板
# ------------------------------------------------------------------ #

SUGGEST_SYSTEM = """你是一位资深 FEA 优化工程师，擅长给出结构优化建议。

请基于以下诊断信息，按优先级给出 3-5 条优化建议。
每条建议包含：
- 类别（material / mesh / boundary / geometry）
- 优先级（1=最高，5=最低）
- 标题
- 描述
- 预期改进效果
- 实现难度（easy / medium / hard）

语言：中文
输出格式：JSON 数组

示例：
[
  {{"category": "mesh", "priority": 1, "title": "加密应力集中区域网格",
    "description": "...", "expected_improvement": "应力精度提升 20%",
    "implementation_difficulty": "medium"}}
]"""


def make_suggest_prompt(
    rule_issues: list[dict],
    ai_diagnosis: str,
    max_stress: float,
    max_displacement: float,
    material_yield: float,
) -> str:
    """生成优化建议的 prompt。"""
    issues_text = "\n".join(
        f"- [{i['severity']}] {i['category']}: {i['message']}"
        for i in rule_issues
    ) if rule_issues else "无明显规则违规。"

    stress_ratio = max_stress / material_yield if material_yield > 0 else 0

    return f"""## 当前状态摘要

### 关键指标
- 最大位移：{max_displacement:.6e}
- 最大应力：{max_stress:.6e}
- 应力/屈服比：{stress_ratio:.2f}

### 发现的问题
{issues_text}

### AI 诊断结果
{ai_diagnosis or "（无 AI 诊断）"}

请给出优化建议，专注于提升结构性能和可靠性。"""


# ------------------------------------------------------------------ #
# CAD 生成模板
# ------------------------------------------------------------------ #

CAD_SYSTEM = """你是一位 CadQuery 专家，擅长生成参数化几何代码。

请生成 CadQuery Python 代码，创建以下几何部件：
- 梁（Beam）：指定长度、宽度、高度、圆角半径
- 圆柱（Cylinder）：指定半径、高度、角度
- 板（Plate）：指定长度、宽度、厚度

要求：
1. 使用 CadQuery 2.x API
2. 导出函数 create_<type>(params) -> Workplane
3. 支持 export_step() 和 export_inp() 导出
4. 代码可直接运行

输出格式：纯 Python 代码块，不要解释。"""
