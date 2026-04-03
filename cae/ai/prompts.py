# prompts.py
"""
Prompt 模板库

为 explain / diagnose / suggest 提供结构化 prompt 模板。
"""
from __future__ import annotations

from dataclasses import dataclass


CALCULIX_SYNTAX_GUARD = """
## CalculiX 语法硬约束

- 修复建议中的 CalculiX 语法必须完全正确。
- 禁止使用任何不存在的关键词、参数名、卡片格式或“伪代码式”INP 写法。
- 禁止编造节点号、单元号、表面名、自由度编号、载荷值、材料名；如果证据里没有这些具体值，只能使用占位符或文字说明。
- 如果你不能确定某条 INP 语法的准确写法，就不要输出该代码片段，改为只描述修改方向。

### 允许使用的正确模板

材料弹性：
```text
*MATERIAL, NAME=STEEL
*ELASTIC
210000, 0.3
```

集中载荷：
```text
*CLOAD
<node_id>, <dof>, <value>
```

静力步：
```text
*STEP
*STATIC
0.01, 1.0
*END STEP
```

### 明确禁止

- 禁止写成 `*MATERIAL` 下一行直接 `E=2.1e+11`
- 禁止写成 `ELASTIC, TYPE=ISOTROPIC` 这种不存在的 CalculiX 片段
- 禁止写成 `*C LOAD`
- 禁止输出 `DLOAD 0 0 -187500 at node 3` 这类自然语言混合伪语法
- 除非证据里已经给出正确对象和载荷类型，否则不要自行生成具体 `*DLOAD` 数据行
"""


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

DIAGNOSE_SYSTEM = f"""你是一位资深的有限元分析（FEA）工程师，擅长诊断 CalculiX 仿真中的错误和警告。

## CalculiX 核心知识速查

### 单元类型与自由度
- **实体单元（C3D*）**：只有位移自由度 D1-D3
- **壳单元（S*、M3D*）**：5或6个自由度（D1-D3位移 + D4-D6转动），约束时需注意完整约束所有自由度
- **梁单元（B*）**：6个自由度，截面属性通过 *BEAM SECTION 定义
- **弹簧单元（SPRING*）**：可压缩或只拉不压，节点必须属于某个实体单元

### 常见错误模式（来自 CalculiX 源码 528 模式库）
1. **RHS only consists of 0.0**：载荷向量为零，通常是耦合约束配置错误
   - *COUPLING + *DISTRIBUTING 必须用 *DLOAD，不能用 *CLOAD
   - 或载荷方向与约束自由度冲突
2. **zero pivot / singular matrix**：边界条件不完整导致刚体运动
3. **not converged**：收敛困难，尝试减小初始步长
4. **negative jacobian**：单元畸形或翻转
5. **increase nmpc_/nboun_/nk_**：MPC/约束/节点数量超限，需简化模型
6. **slave/master surface**：接触主从面定义错误
7. **user element/umat**：用户子程序未找到或实现错误
8. **eigenvalue**：模态分析特征值求解失败

### 板壳弯曲结果验证
四边形壳单元（S4/S4R）在均布载荷下应有平滑碗状变形，若呈尖刺/波形说明边界条件错误。

### 单位一致性（最常见的错误）
- 材料 E 用 MPa，几何必须用 mm，载荷用 N
- 应力结果 MPa，位移结果 mm
- 检验：E=210000 MPa，1N/mm²=1MPa

### 单位推断规则（E 值自动推断）
根据弹性模量 E 的数值大小推断实际单位体系：
- **E ≈ 210000~220000**（如 210000、2.1e+5、2.09e+5）→ **MPa 体系**（标准钢）
- **E ≈ 2.0e+11~2.2e+11**（如 2.1e+11、2.06e+11）→ **Pa 体系**（SI 单位，同一钢材但用 Pa 表示）
- **E ≈ 70000~72000** → MPa 体系（铝合金）
- **E ≈ 7.0e+10** → Pa 体系（同一铝合金但用 Pa 表示）

**关键推理链**：若 E=2.1e+11 被当作 MPa 输入，则 CalculiX 认为刚度虚高 10^6 倍，
导致位移结果偏小 ~10^6 倍（mm 级变成 μm 级），应力也偏小相应倍数。
反过来，若 E=210000 被当作 Pa 输入，则刚度偏小 10^6 倍，位移和应力结果会虚大。

典型信号：
- 应力结果 ~1e-05 Pa 量级，但 E 值 ~2.1e+11 → Pa 体系被误当 MPa
- 或位移/应力结果数量级与预期相差 10^6 倍 → 单位体系混用

### 应力/应变分量顺序（CalculiX 输出）
- 应力：SXX, SYY, SZZ, SXY, SYZ, SZX
- 应变：EXX, EYY, EZZ, EXY, EYZ, EZX
- von Mises 应力在第4个位置

### CalculiX 应变输出规则
- *STEP, NLGEOM：格林/拉格朗日应变（大变形分析）
- 无 NLGEOM：线性（小变形）欧拉应变

### MPC/约束内存限制
- nmpc_：多点约束数量限制
- nboun_：边界条件数量限制
- nk_：节点数量限制
- memmpc_：MPC 内存限制

### 材料完整性检查
CalculiX 要求以下材料属性必须定义：
- *ELASTIC：弹性常数（所有分析必需）
- *DENSITY：密度（动力学分析必需）
- *CONDUCTIVITY：热传导系数（热分析必需）
- *SPECIFIC HEAT：比热容（热分析必需）

## 诊断输出要求

请按以下格式回答：

### 1. 问题定位
- **类别**：收敛/材料/单位/边界/网格/接触/载荷/file_io/dynamics/limit_exceeded
- **严重程度**：error（必须修复）/ warning（建议修复）/ info（参考）

### 2. 根因分析
- 直接原因（来自 stderr 或规则检测）
- 间接原因（可能是导致直接原因的上游问题）

### 3. 修复建议
**必须具体可操作，优先给出可直接复制粘贴的代码片段**

示例：
```
在 *STATIC 后添加初始步长参数：
*STATIC
0.01, 1.0
```

## 重要约束

**只使用 CalculiX 语法，禁止使用 Abaqus 专有卡片**
- ❌ `*CONTACT CONTROLS`、`*SURFACE INTERACTION` 参数名错误
- ❌ `*STATIC,0.01,1.0` 卡片名与参数之间不能有逗号
- ✅ 正确：`*STATIC` 后换行写参数

{CALCULIX_SYNTAX_GUARD}

请直接回答，不要泛泛而谈。"""


def make_diagnose_prompt(rule_issues: list[dict], stderr_snippets: str = "") -> str:
    """生成诊断的 prompt（极简版，专为 1.5B 模型优化）。

    1.5B 模型格式控制能力有限，不做复杂格式化，只做规则结论的翻译。
    排序和优先级在规则层代码中完成，不交给 LLM。
    """
    if rule_issues:
        # 规则层已完成排序和优先级标注，这里只翻译成自然语言
        issues_text = "\n".join(
            f"- [{i['severity']}] {i['category']}: {i['message']}"
            for i in rule_issues
        )
    else:
        issues_text = "（规则层未检出问题）"

    return f"""以下是规则检测发现的问题：

{issues_text}

请用简单的中文，针对每个问题说明原因和修复方法。
不要输出编号、优先级、标题，直接一段话说清楚。
格式越简单越好，只负责把规则层的结论翻译成自然语言。

不要读取任何原始文件，只基于上述提供的信息回答。"""


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
# Chain 推理模板（多步推理链）
# ------------------------------------------------------------------ #

CHAIN_SYSTEM = """你是一位资深的有限元分析（FEA）工程师，擅长诊断 CalculiX 仿真问题。

你采用**多步 Chain 推理**方式，每一步都建立在上一步的基础上：

1. **症状识别（Symptom）**：观察物理数据和错误信息，识别异常症状
2. **原因分析（Cause）**：基于症状，推断可能的原因
3. **验证推理（Verify）**：利用已知规则和参考数据，验证或排除每个可能原因
4. **诊断结论（Diagnosis）**：综合所有信息，给出最终诊断和修复建议

## Chain 推理约束

- **只使用 CalculiX 语法**：禁止使用 Abaqus 专有卡片
- **基于证据推理**：每一步结论都必须有明确的数据支撑
- **置信度评估**：对每个结论给出置信度（高/中/低）
- **推理路径透明**：展示完整的推理链，让人理解决策过程

## 输出格式

每步输出格式：
```
### Step N: [步骤名称]
**置信度**: [高/中/低]
**观察**: [观察到的现象]
**推理**: [基于观察的推理]
**结论**: [得出的结论]
```

最终输出结构化诊断报告。"""



def make_chain_symptom_prompt(
    issues: list[dict],
    physical_data: str,
    stderr_snippets: str,
) -> str:
    """生成 Chain Step 1: 症状识别的 prompt。"""
    issues_text = "\n".join(
        f"- [{i['severity']}] {i['category']}: {i['message']}"
        for i in issues
    ) if issues else "（规则层未检出问题）"

    return f"""## Step 1: 症状识别

你收到了以下诊断信息，请识别出所有异常**症状**（表面现象）。

### 规则检测结果
{issues_text}

### 关键物理数据
{physical_data or "（无物理数据）"}

### stderr 直接证据
{stderr_snippets or "（无 stderr 证据）"}

**任务**：
1. 列出所有观察到的异常症状
2. 对每个症状，标注其严重程度（高/中/低）
3. 识别哪些症状是**直接证据**（来自规则检测），哪些是**间接证据**（推断）

**输出格式**：
```
### 识别的症状

1. [症状描述] (严重程度: 高/中/低)
   - 来源: [直接证据/间接推断]
   - 关联规则: [触发的规则名称，如有]

2. ...
```

只输出症状识别结果，不要进行原因分析。"""


def make_chain_cause_prompt(
    symptoms: str,
    physical_data: str,
) -> str:
    """生成 Chain Step 2: 原因分析的 prompt。"""
    return f"""## Step 2: 原因分析

基于以下识别的症状，推断可能的**根本原因**。

### 已识别的症状
{symptoms}

### 关键物理数据
{physical_data or "（无物理数据）"}

**任务**：
1. 对每个症状，推断 2-3 个可能的根本原因
2. 考虑常见的 FEA 错误模式：
   - 单位不一致（最常见）
   - 边界条件错误（欠约束/过约束）
   - 材料定义错误
   - 载荷未正确施加
   - 网格质量问题
   - 接触定义错误
3. 标注每个原因与症状的关联强度（强/中/弱）

**输出格式**：
```
### 可能原因分析

**症状 1**: [症状描述]
  1. [原因1] (关联强度: 强/中/弱)
     推理: [为什么这个原因可能导致该症状]
  2. [原因2] (关联强度: 强/中/弱)
     推理: ...

**症状 2**: ...
```

只输出原因分析，不要进行验证。"""


def make_chain_verify_prompt(
    symptoms: str,
    causes: str,
    physical_data: str,
    stderr_snippets: str,
    similar_cases: list[dict],
) -> str:
    """生成 Chain Step 3: 验证推理的 prompt。"""
    cases_text = ""
    if similar_cases:
        cases_text = "\n### 参考案例\n"
        for case in similar_cases[:3]:
            cases_text += f"- **{case['name']}** (相似度: {case['similarity_score']}%)\n"
            cases_text += f"  单元类型: {case['element_type']}, 问题类型: {case['problem_type']}\n"
            cases_text += f"  预期位移上限: {case.get('expected_disp_max', 'N/A')}\n"
    else:
        cases_text = "\n### 参考案例\n（无可用参考案例）"

    return f"""## Step 3: 验证推理

基于以下信息，**验证或排除**每个可能原因，确定最可能的根因。

### 已识别的症状
{symptoms}

### 可能的原因
{causes}

### 关键物理数据
{physical_data or "（无物理数据）"}

### stderr 直接证据
{stderr_snippets or "（无 stderr 证据）"}
{cases_text}

**任务**：
1. 对每个可能原因，利用上述数据进行验证或排除
2. 量化分析：
   - 如果涉及单位问题：计算 E 值与应力结果的比值，推断单位体系
   - 如果涉及位移问题：与参考案例的预期位移对比
   - 如果涉及边界条件：检查约束完整性
3. 对每个原因给出**验证结论**（确认/可能/排除）和**置信度**（高/中/低）

**输出格式**：
```
### 验证分析

**原因 1**: [原因描述]
  - 验证数据: [使用的验证数据]
  - 计算/推理: [具体计算或推理过程]
  - 验证结论: [确认/可能/排除]
  - 置信度: [高/中/低]
  - 依据: [具体依据]

**原因 2**: ...

### 最可能的根因（按置信度排序）
1. [原因] - 置信度: 高 - 主要依据: [依据摘要]
2. ...
```

只输出验证分析，不要给出最终诊断结论。"""


def make_chain_diagnosis_prompt(
    symptoms: str,
    causes: str,
    verify: str,
    physical_data: str,
) -> str:
    """生成 Chain Step 4: 最终诊断的 prompt。"""
    return f"""## Step 4: 最终诊断

综合前 3 步的分析结果，给出最终诊断结论和修复建议。

### Step 1 - 症状识别
{symptoms}

### Step 2 - 原因分析
{causes}

### Step 3 - 验证推理
{verify}

### 关键物理数据（参考）
{physical_data or "（无物理数据）"}

**任务**：
1. 综合所有分析，确定**最终根因**（1-2 个最可能的）
2. 对每个根因，给出**具体修复建议**（可直接操作的）
3. 按优先级排序修复操作
4. 预测修复后的预期结果

**输出格式**：
```
### 最终诊断

**根因 1**: [根因描述]
**置信度**: [高/中/低]
**解释**: [综合分析的解释]

**根因 2**: ...

### 修复建议（按优先级排序）

| 优先级 | 操作 | 预期效果 | 实现难度 |
|--------|------|----------|----------|
| 1 | [具体修复操作] | [预期效果] | [易/中/难] |
| 2 | ... | ... | ... |

### 预期修复后结果
- 位移: [预期范围]
- 应力: [预期范围]
- 收敛性: [改善/正常]

### 推理链总结
[简要总结从症状到根因的完整推理链]
```"""


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


def make_diagnose_prompt_v2(
    rule_issues: list[dict],
    stderr_snippets: str = "",
    *,
    physical_data: str = "",
    stderr_summary: str = "",
    similar_cases: list[dict] | None = None,
) -> str:
    """Generate an evidence-focused prompt for local diagnosis models."""
    if rule_issues:
        issues_lines = []
        for idx, issue in enumerate(rule_issues, 1):
            location = f" | location={issue['location']}" if issue.get("location") else ""
            suggestion = f" | rule_fix={issue['suggestion']}" if issue.get("suggestion") else ""
            issues_lines.append(
                f"{idx}. [{issue['severity']}] {issue['category']}: {issue['message']}{location}{suggestion}"
            )
        issues_text = "\n".join(issues_lines)
    else:
        issues_text = "无明确规则问题。"

    if similar_cases:
        case_lines = []
        for idx, case in enumerate(similar_cases[:3], 1):
            parts = [f"{idx}. {case['name']}", f"similarity={case.get('similarity_score', 'N/A')}%"]
            if case.get("element_type"):
                parts.append(f"element={case['element_type']}")
            if case.get("problem_type"):
                parts.append(f"type={case['problem_type']}")
            if case.get("expected_disp_max") is not None:
                parts.append(f"disp_ref={case['expected_disp_max']}")
            if case.get("expected_stress_max") is not None:
                parts.append(f"stress_ref={case['expected_stress_max']}")
            case_lines.append(" | ".join(parts))
        similar_cases_text = "\n".join(case_lines)
    else:
        similar_cases_text = "无可用参考案例。"

    return f"""{DIAGNOSE_SYSTEM}

## 已提取证据

### 规则层问题
{issues_text}

### 物理量摘要
{physical_data or "无物理量摘要。"}

### 收敛摘要
{stderr_summary or "无收敛摘要。"}

### 参考案例
{similar_cases_text}

### stderr 证据片段
{stderr_snippets or "无 stderr 证据片段。"}

## 回答要求
1. 先给“最可能根因”，最多 3 条，按置信度排序。
2. 每条根因必须明确引用上面的证据，不要脱离证据猜测。
3. 修复建议必须具体到 CalculiX 可操作修改，必要时给最小 INP 片段。
4. 如果存在单位问题、边界条件问题或接触/载荷传递问题，优先指出。
5. 禁止使用 Abaqus 专有语法，只能给 CalculiX 写法。
6. 修复建议中的 CalculiX 语法必须完全正确，禁止使用任何不存在的关键词或格式。
7. 若证据中没有具体 node_id / dof / value / set 名称 / surface 名称，只能使用 `<node_id>`、`<dof>`、`<value>` 这类占位符，禁止编造具体数值。
8. 若不能确认某段 INP 语法完全正确，则不要输出代码片段，只能给文字建议。

{CALCULIX_SYNTAX_GUARD}

请按下面格式输出：
最可能根因：
- [高/中/低] 根因名称：一句话结论。证据：...

修复建议：
1. ...
2. ...

验证步骤：
1. ...
2. ...
"""
