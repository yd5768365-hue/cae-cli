# CAE-CLI Phase 1 Demo Pack

更新时间：2026-04-03

这份材料用于论坛发帖、私聊演示、向老师或同学介绍当前版本。

当前阶段目标不是“全自动 CAE 平台”，而是先把 `CalculiX` 的高频报错诊断做稳，做到：

- 能识别一批高频问题族
- 输出稳定、清晰、少重复
- 对少量低风险问题提供白名单自动修复
- 修复后给出明确的验证状态

## 当前状态

截至 2026-04-03，当前版本已具备：

- 诊断样本库：11 个 seed case
- 已纳入回归的问题族：10 类
- 自动修复白名单：3 类
- 回归/单测通过：33 passed

建议对外表述：

> 我现在在做一个面向 CalculiX 的诊断工具，重点解决“新手看不懂报错、老用户排查太费时间”的问题。当前版本已经有回归样本库、统一诊断输出、安全白名单自动修复和修复后验证。

## 当前支持的问题类型

下面这些问题族已经纳入回归样本，可以稳定复现和回归检查：

| 问题族 | 当前覆盖样例 | 当前能力 |
| --- | --- | --- |
| `input_syntax` | `syntax/broken_keyword` | 检测无效关键词、提示检查卡片拼写 |
| `material` | `material/missing_elastic`, `material/commented_elastic` | 识别缺少 `*ELASTIC`、材料定义不完整 |
| `boundary_condition` | `boundary/missing_boundary` | 识别未定义或明显不足的边界条件 |
| `rigid_body_mode` | `boundary/rigid_body_mode` | 结合结果特征提示可能欠约束/刚体运动 |
| `contact` | `contact/missing_surface_behavior` | 识别接触定义缺项 |
| `convergence` | `convergence/not_converged` | 识别步长/收敛失败类问题 |
| `load_transfer` | `load/zero_load_vector` | 提示载荷没有真正传到结构上 |
| `element_quality` | `mesh/distorted_elements` | 识别明显畸变单元问题 |
| `file_io` | `results/missing_frd` | 识别结果文件缺失/读取失败 |
| `unit_consistency` | `units/elastic_in_pa` | 提示单位量级异常 |

建议对外表达时，不要写成“已支持所有 CalculiX 错误”。更稳的说法是：

> 当前已先覆盖一批高频问题族，并且这些问题已经纳入回归样本，不是纯规则堆叠。

## 当前输出长什么样

当前 CLI 输出已经统一为：

- 诊断摘要
- 严重问题数 / 警告数
- 最优先问题
- 首步建议
- 按优先级排序的问题列表

适合发帖的简化示例：

```text
诊断摘要
- 严重问题：1
- 警告问题：1
- 最优先问题：Input Syntax Issue
- 首步建议：检查 INP 文件中的卡片拼写，确保与 CalculiX 支持的关键词一致

[P1] [input_syntax] 检测到无效 INP 关键词，可能是拼写错误或版本不兼容
-> 检查 INP 文件中的卡片拼写，确保与 CalculiX 支持的关键词一致

[P2] [input_syntax] BOUNDARY 定义在 *STEP 之前，可能无效
-> 载荷和边界条件通常应定义在 *STEP 块内部（或 *STEP 之后）
```

这类输出的目标不是“解释所有细节”，而是让用户快速知道：

- 先改哪个问题
- 为什么大概会错
- 下一步该改哪里

## 典型示例

### 示例 1：材料缺少 `*ELASTIC`

输入片段：

```text
*MATERIAL, NAME=STEEL
*DENSITY
7.85e-09
```

stderr 片段：

```text
ERROR: no elastic constants were assigned to material STEEL
*ERROR in material definition
```

当前诊断核心输出：

```text
[P1] [material] 材料缺少弹性常数（Elastic modulus）
-> 在 *MATERIAL 中添加 *ELASTIC 或 *ELASTIC,TYPE=ISOTROPIC 定义弹性模量
```

### 示例 2：无效关键词 / 输入语法问题

当前诊断核心输出：

```text
[P1] [input_syntax] 检测到无效 INP 关键词，可能是拼写错误或版本不兼容
-> 检查 INP 文件中的卡片拼写，确保与 CalculiX 支持的关键词一致
```

### 示例 3：收敛失败

stderr 片段：

```text
WARNING: too many attempts made for this increment
ERROR: increment size smaller than minimum
job finished with nonconvergence
```

当前诊断核心输出：

```text
[P2] [convergence] 增量步小于最小值，收敛困难
-> 减小初始步长（*STATIC 首参数），或增大允许的最小步长，或放宽收敛容差
```

### 示例 4：载荷没有真正传到结构

当前诊断核心输出：

```text
[P1] [load_transfer] 载荷向量为零（RHS only consists of 0.0），载荷未正确传递到结构
-> 检查 *COUPLING / *DISTRIBUTING / *DLOAD 的组合是否正确
```

### 示例 5：白名单自动修复

当前已经能处理的一个安全修复示例：

修复前：

```text
*MATERIAL, NAME=STEEL
*DENSITY
7.85e-09
```

自动修复动作：

```text
Added *ELASTIC placeholder for material STEEL
```

修复后验证状态：

```text
verification_status=passed
verification_notes=material_missing_elastic: *ELASTIC block present
```

修复后文件片段：

```text
*MATERIAL, NAME=STEEL
*ELASTIC
210000, 0.3
*DENSITY
7.85e-09
```

## 自动修复白名单边界

当前自动修复只允许低风险、结构性修改。

允许自动修复：

- 缺少 `*ELASTIC`
- 缺少 `*STEP`
- `*STATIC` 初始增量过大

明确不自动修复：

- 边界条件数值
- 载荷大小
- 接触参数
- 真实材料参数
- 网格密度或网格策略
- 任何会直接改变物理意图的修改

推荐对外直接这样说：

> 现阶段自动修复只做“确定性强、低风险”的结构性补全，不会自动改载荷、约束或真实材料值，避免把一个物理上错误的模型修成“数值上能跑”的模型。

## 当前已知限制

这部分建议在发帖时主动写出来，能提高可信度。

- 当前样本库还不大，只有第一批 11 个 seed case
- 现在更适合高频报错和新手排障，不适合复杂非线性问题的完整专家替代
- 有些样本会同时暴露多个问题，当前输出会按优先级排序，但还不是最终形态
- 自动修复还非常克制，只覆盖 3 个白名单问题
- AI 深度分析不是这一阶段重点，现在优先保证规则层可靠

## 发帖时建议重点展示什么

如果你只放 3 个点，优先放这些：

1. 一个真实报错输入 + 诊断输出
2. 一个自动修复前后对比 + 验证状态
3. 一张“当前支持的问题类型”列表

不要重点展示这些：

- 宏大愿景
- 企业版设想
- 很重的 AI 名词
- “以后会支持一切”

## 建议收集的反馈

论坛发帖时，重点问用户这 4 个问题：

1. 你最常见的 3 类 CalculiX 报错是什么？
2. 你最想自动化的是“定位问题”还是“给修复建议”？
3. 你能接受工具自动改哪些内容，哪些一定要人工确认？
4. 如果你愿意试用，你最想先验证哪一类问题？
