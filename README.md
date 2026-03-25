# cae-cli

> **买不起商业软件的机械工程学生和小型实验室** — 用 CalculiX 做仿真，AI 帮你诊断问题

<p align="center">

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/badge/PyPI-cae--cxx%20v1.4.0-blue.svg)](https://pypi.org/project/cae-cxx/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Test](https://img.shields.io/badge/Tests-100%20passed-brightgreen.svg)](#兼容性验证)
[![CalculiX](https://img.shields.io/badge/CalculiX-2.22+-orange.svg)](https://www.calculix.org/)

</p>

**学生 | 工程师 | 独立开发者** — 快速验证想法，AI 辅助分析，本地运行保护数据隐私

---

## AI 诊断系统

> **不用猜，规则层直接告诉你哪里错了**

求解失败后，`cae diagnose` 能准确定位问题根因，并给出**可直接复制粘贴的修复命令**。

```bash
$ cae solve contact.inp
╭───────────────────────╮
║  求解失败  耗时 0.1s   ║
╰───────────────────────╯

$ cae diagnose results/
规则检测：发现 2 个问题
[X] [material] 材料缺少弹性常数
    -> 在 *MATERIAL 中添加 *ELASTIC 或 *ELASTIC,TYPE=ISOTROPIC

[X] [convergence] 增量步小于最小值
    -> 减小初始步长（*STATIC 首参数）
```

### 核心优势：基于源码硬编码，0 幻觉

传统 AI 诊断依赖 LLM 理解错误信息，容易产生**幻觉建议**（如把 Abaqus 语法当作 CalculiX）。

本项目采用**规则层优先**策略：

| 层级 | 数据来源 | 可靠性 |
|------|----------|--------|
| **Level 1** | 527 个 CalculiX 源码硬编码错误模式 | ✅ 100% 准确 |
| Level 2 | 638 个官方测试集物理数据 | ✅ 基于真实求解 |
| Level 3 | LLM 推理（可选） | ⚠️ 需 Prompt 约束 |

规则层建议**直接来自 CalculiX 源码**，通过 `grep -r "\*ERROR\|WARNING" src/*.f` 提取：
```fortran
! CalculiX/src/calinput.f
WRITE(*,*) '*ERROR in calinput: no elastic constants'
```
解析为：
```python
{"pattern": "no elastic constants", "suggestion": "在 *MATERIAL 中添加 *ELASTIC"}
```

### 三层诊断架构

```
┌─────────────────────────────────────────────────────────────┐
│  Level 1: 规则检测（无条件，0 LLM 调用）                    │
│  527 个源码硬编码模式，覆盖：                               │
│  - 材料缺失：no elastic / no density / no material          │
│  - 输入语法：card cannot be interpreted / parameter error   │
│  - 收敛性：not converged / divergence / increment stalled   │
│  - 单元质量：negative jacobian / hourglassing               │
├─────────────────────────────────────────────────────────────┤
│  Level 2: 参考案例对比                                       │
│  638 个官方测试集，物理数据相似度匹配                       │
│  判断当前位移/应力是否在合理范围内                          │
├─────────────────────────────────────────────────────────────┤
│  Level 3: AI 深度分析（可选）                               │
│  Prompt 内置约束：禁止 Abaqus 语法                         │
└─────────────────────────────────────────────────────────────┘
```

### 与 Ansys Copilot 的差异

| 维度 | Ansys Copilot | CAE-CLI |
|------|---------------|---------|
| 知识来源 | 文档 + 问答 | **源码硬编码** + 真实求解记录 |
| 准确性 | 可能幻觉 | **0 幻觉**（规则层） |
| 覆盖范围 | 通用 CAE | **CalculiX 特定** |

CalculiX 文档零散、不完整，但**真实错误输出是确定的**。本项目直接解析 solver 输出，匹配源码中的硬编码错误，准确性高于基于文档的 AI 方案。

---

## 常见问题

**Q: 支持 Windows 吗？**
> ✅ 支持，Windows 10/11 + Python 3.10+

**Q: 和 ANSYS/Abaqus 有什么区别？**
> cae-cli 不追求替代商业软件，而是专注于**快速验证**和**AI 辅助**。当你有一个想法想快速验证时，30 秒启动，一条命令出结果。商业软件适合交付最终设计，cae-cli 适合探索初期方案。

**Q: AI 能帮我做什么？**
> 三层诊断系统：1) 自动检测收敛性、网格质量、应力集中问题；2) 对比 638 个官方测试案例判断结果是否合理；3) AI 深度分析给出修复建议。简单问题秒级诊断，复杂问题给出排查方向。

**Q: 数据安全吗？**
> 所有计算和 AI 分析都在本地运行，不上传任何数据。适合处理涉及机密或敏感数据的项目。

**Q: 需要 GPU 吗？**
> 不需要。CalculiX 求解器和 AI 模型都支持 CPU 运行。AI 模型约 5 GB（Q4 量化），在普通笔记本上即可运行。

**Q: 和 FreeCAD FEM 有什么区别？**
> FreeCAD FEM 是 GUI 界面，适合鼠标操作。本项目是**命令行工具**，适合：1) 批量处理多个模型；2) 自动化流程集成；3) AI 辅助诊断（规则层直接解析错误输出，给出修复建议）。如果你习惯鼠标操作，FreeCAD 更直观；如果你需要自动化或快速调试，cae-cli 更高效。

---

## 新增功能

### v1.4.0 (2026-03)

**工作目录设置**：
- `cae setting` 交互式设置工作目录
- 自动创建 `output/` 和 `solvers/` 子目录
- `cae solve` 输出自动进入 `工作目录/output/`
- 求解器路径自动设为 `工作目录/solvers/ccx`

**AI 诊断规则层增强**：
- Level 1 规则检测：527 个 CalculiX 源码硬编码错误模式
- 新增：`MATERIAL_PATTERNS`、`PARAMETER_PATTERNS`、`MPC_LIMIT_PATTERNS`
- 新增：步长停滞检测（连续5个增量 INC TIME 不增大）
- Prompt 约束：禁止 Abaqus 专有卡片语法

### v1.3.1 (2026-03)

**三层次诊断系统**：
- **Level 1（规则检测）**：基于 527 个 CalculiX 源码硬编码错误/警告模式，无条件执行
  - 收敛性：`not converged`, `increment size smaller`, `divergence`
  - 材料缺失：`no elastic constants`, `no density`, `no material`
  - 输入语法：`card image cannot be interpreted`, `parameter not recognized`
  - 单元质量：`negative/nonpositive jacobian`, `hourglassing`
  - 步长停滞：连续5个增量 INC TIME 不增大
- **Level 2（参考案例对比）**：638 个 CalculiX 官方测试集案例匹配
- **Level 3（AI 深度分析）**：可选，基于规则检测结果 + 物理数据 + 相似案例

**架构优势**：
- 规则层基于**真实 solver 输出**（源码硬编码），而非文档描述，无幻觉
- Prompt 内置 CalculiX 语法约束，禁止 Abaqus 专有卡片

**AI 可选插件**：
- `cae install` — 只安装 CalculiX 求解器
- `cae install ai` — 单独安装 AI 模型
- 不安装 AI 时仍可使用规则检测 + 参考案例对比

### v1.3.0

**协议接口**：所有关键词类实现 `IKeyword` 协议，支持类型检查和 IDE 自动补全

**材料模型**：
- `HyperElastic` — 超弹性材料（Mooney-Rivlin / Ogden / Yeoh / Arruda-Boyce）
- `Plastic` — 塑性材料（等向/运动/组合硬化 + 循环硬化）

**接触分析**：
- `SurfaceInteraction` / `SurfaceBehavior` / `Friction` — 完整接触定义
- `ContactPair` — 接触对（NODE_TO_SURFACE / SURFACE_TO_SURFACE）
- `Tie` — 绑定接触
- `Gap` / `GapUnit` — 间隙单元

**约束**：
- `Coupling` — KINEMATIC / DISTRIBUTING 耦合
- `Mpc` — MPC 多点约束（BEAM / PLANE / STRAIGHT / MEANROT / DIST）
- `Equation` — 线性方程约束 + `EquationFactory` 工厂方法

**载荷**：
- `Amplitude` — 载荷-时间幅值曲线
- `Cload` / `Dload` / `Boundary` — 载荷和边界条件

---

---

## 快速开始

```bash
# 1. 安装 (30 秒)
pip install cae-cxx && cae install

# 2. 生成悬臂梁模板
cae inp template cantilever_beam -o beam.inp

# 3. 求解
cae solve beam.inp

# 4. AI 诊断（可选）
cae diagnose results/
```

**诊断输出示例：**

```
$ cae solve contact.inp
╭───────────────────────╮
║  求解失败  耗时 0.1s   ║
╰───────────────────────╯

$ cae diagnose results/
规则检测：发现 2 个问题
[X] [material] 材料缺少弹性常数（Elastic modulus）
    -> 在 *MATERIAL 中添加 *ELASTIC 或 *ELASTIC,TYPE=ISOTROPIC 定义弹性模量
[X] [input_syntax] 检测到无效 INP 关键词
    -> 检查卡片拼写，确保与 CalculiX 支持的关键词一致

参考案例匹配：找到 3 个相似案例
- contact_mortar (相似度 87.3%)
  预期位移: 1.234e-03
  预期应力: 45.2 MPa
```

**诊断说明：**
- Level 1 规则检测**无需 AI**，基于 527 个 CalculiX 源码硬编码模式，0 幻觉
- Level 3 AI 分析需要 `pip install cae-cxx[ai]`，用于复杂场景深度解读

浏览器自动打开 ParaView Glance 显示位移 / 应力云图

---

## 核心能力

### 🎯 快速验证（30 秒启动，一条命令出结果）

| 功能 | 命令 | 说明 |
|:----:|------|------|
| ⚡ 执行仿真 | `cae solve model.inp` | CalculiX 求解 |
| 🌐 3D 可视化 | `cae view results/` | 浏览器打开 |
| 🔍 AI 诊断 | `cae diagnose results/` | 自动发现 4 类问题 |
| 📄 PDF 报告 | `cae report results/` | 一键生成报告 |

### 📦 完整仿真流程

| 功能 | 命令 | 说明 |
|:----:|------|------|
| 🔲 网格划分 | `cae mesh gen geo.step -o mesh.inp` | Gmsh 自动网格 |
| 👁 网格预览 | `cae mesh check mesh.inp` | HTML 报告 |
| ⚡ 执行仿真 | `cae solve model.inp` | CalculiX 求解 |
| 🌐 3D 可视化 | `cae view results/` | 浏览器打开 |
| 🚀 一键运行 | `cae run geo.step` | 全自动 |

### INP 文件处理

| 功能 | 命令 |
|------|------|
| 📋 结构摘要 | `cae inp info model.inp` |
| ✔️ 校验 | `cae inp check model.inp` |
| 👁 显示块 | `cae inp show model.inp -k *MATERIAL -n STEEL` |
| ✏️ 修改 | `cae inp modify model.inp -k *ELASTIC --set "210000, 0.3"` |
| 📚 关键词浏览 | `cae inp list Mesh` |
| 📝 模板生成 | `cae inp template cantilever_beam -o model.inp` |
| 🤖 AI 建议 | `cae inp suggest model.inp` |

### AI 助手

| 功能 | 命令 | 说明 |
|------|------|------|
| 📥 安装模型 | `cae install ai` | ~5 GB |
| 🔍 AI 诊断 | `cae diagnose results/ -i model.inp` | 规则+案例+AI+解读+建议 |
| 📄 PDF 报告 | `cae report results/` | 最大位移/应力/安全系数/云图，一键发给导师 |

**诊断三层架构：**

```
┌─────────────────────────────────────────────────────────┐
│  Level 1: 规则检测（无条件执行，0 LLM 调用）           │
│  ├── 527 个 CalculiX 源码硬编码模式                    │
│  ├── 收敛性 / 材料缺失 / 输入语法 / 单元质量 / 步长停滞  │
├─────────────────────────────────────────────────────────┤
│  Level 2: 参考案例对比（638 个真实求解记录）            │
│  └── 物理数据相似度匹配                                │
├─────────────────────────────────────────────────────────┤
│  Level 3: AI 深度分析（可选，LLM 调用）                │
│  └── 基于规则检测结果 + 物理数据 + 相似案例            │
└─────────────────────────────────────────────────────────┘
```

**规则层检测规则（Level 1）：**

| 规则 | 匹配内容 | 建议 |
|------|----------|------|
| 收敛性 | `not converged`, `divergence` | 检查载荷步设置 |
| 步长停滞 | 连续5个 `increment size` 不增大 | 检查接触设置 |
| 材料缺失 | `no elastic constants`, `no density` | 添加材料卡片 |
| 输入语法 | `card image cannot be interpreted` | 检查拼写 |
| 参数错误 | `parameter not recognized` | 检查参数名大小写 |
| 单元质量 | `negative/nonpositive jacobian` | 检查网格质量 |
| 位移异常 | 位移超出合理范围 | 检查边界条件 |

### 格式转换

```
.frd → .vtu    cae convert result.frd -o out.vtu
.msh → .inp    cae convert mesh.msh -o out.inp
.dat → .csv    cae convert result.dat -o out.csv
```

---

## 安装

```bash
# 基础安装
pip install cae-cxx

# 安装 AI 支持
pip install cae-cxx[ai]

# 安装网格和 PDF 支持
pip install cae-cxx[mesh,report]
```

### 安装求解器

| 系统 | 一键安装 | 手动安装 |
|------|----------|----------|
| Windows | `cae install` | [calculix.org](https://calculix.org) |
| macOS | `cae install` | `brew install calculix` |
| Ubuntu | `cae install` | `sudo apt install calculix-ccx` |

### 安装 AI 模型

```bash
cae install ai                    # 安装默认模型 (deepseek-r1-7b)
cae install ai --model deepseek-r1-14b  # 安装大模型
```

---

## 命令速查

### `cae setting` — 工作目录设置

```bash
cae setting                              # 交互式设置工作目录
cae setting -w ~/my_cae_project         # 指定工作目录
```

设置后，`cae solve` 的输出自动进入 `工作目录/output/`，求解器路径自动设为 `工作目录/solvers/ccx`。

### `cae solve` — 求解

```bash
cae solve model.inp                    # 标准求解
cae solve model.inp -o results/      # 输出到目录
cae solve model.inp --timeout 7200    # 超时 2 小时
cae solve model.inp -s calculix       # 指定求解器
```

### `cae mesh` — 网格

```bash
cae mesh gen geo.step -o mesh.inp              # 生成网格
cae mesh gen geo.step -o mesh.inp -s 2.0      # 网格尺寸
cae mesh gen geo.step -o mesh.inp --order 2   # 二阶单元
cae mesh check mesh.inp                        # 预览网格
```

### `cae inp` — INP 文件

```bash
cae inp info model.inp                       # 结构摘要
cae inp check model.inp                      # 校验
cae inp show model.inp -k *MATERIAL         # 显示块
cae inp modify model.inp -k *ELASTIC --set "210000, 0.3"  # 修改
cae inp list                                 # 关键词分类
cae inp list Mesh                            # Mesh 类关键词
cae inp list -k *BOUNDARY                   # 关键词详情
cae inp template --list                      # 模板列表
cae inp template cantilever_beam -o beam.inp # 生成
cae inp suggest model.inp                    # AI 建议
```

### `cae diagnose` — 三层诊断

```bash
cae diagnose results/                           # 规则+案例+AI解读+AI建议
cae diagnose results/ -i model.inp            # 指定 INP 进行案例匹配
cae diagnose results/ -i model.inp --no-ai    # 跳过 AI 分析
cae diagnose results/ --no-explain             # 跳过 AI 解读
cae diagnose results/ --no-suggest            # 跳过 AI 建议
```

### 自动修复 — 一键修复常见错误

诊断后自动修复检测到的问题，定位由规则层硬编码（确定性），原文件永远不变：

```bash
# 完整流程
cae solve model.inp        # 求解失败
cae diagnose results/ -i model.inp   # 诊断问题

# 诊断结果
规则检测：发现 1 个问题
[X] 材料 STEEL 缺少弹性常数
    -> 在 *MATERIAL 中添加 *ELASTIC

是否自动修复？[y/N]: y
✓ 原文件已保留：model_original.inp
✓ 修复文件已生成：model_fixed.inp

# 验证修复
cae solve model_fixed.inp  # 求解成功！
```

**对比展示**（比任何文字描述都有说服力）：

| 状态 | constants per material | 求解结果 |
|------|----------------------|----------|
| 修复前 | **0** | ✗ ERROR: no elastic constants |
| 修复后 | **2** | ✓ Job finished |

### `cae test` — 测试

```bash
cae test                     # 官方测试集（638 文件）
cae test --sample 20        # 采样 20 个
cae test --quiet             # 静默
```

### `cae report` — PDF 报告

```bash
cae report results/                         # 生成报告（默认输出到 results/report_*.pdf）
cae report results/ -o report.pdf           # 指定输出路径
cae report results/ -i model.inp           # 附带 INP 材料属性
cae report results/ -y 350 -j beam_test     # 手动指定屈服强度和工况名
cae report results/ -s 100                  # 调整变形放大倍数（云图）
```

> 需要 weasyprint：`pip install cae-cxx[report]`

### 其他命令

```bash
cae run geo.step             # 一键运行
cae view results/            # 查看结果
cae convert file.frd -o.vtu  # 格式转换
cae solvers                  # 求解器状态
cae info                     # 配置信息
cae download URL -o path/    # 下载文件
```

---

## 内置模板

| 模板 | 命令 | 单元 | 典型应用 |
|------|------|------|----------|
| 悬臂梁 | `cantilever_beam` | B32 | 桥梁、建筑梁 |
| 平板 | `flat_plate` | S4 | 板壳结构 |

```bash
# 参数覆盖示例
cae inp template cantilever_beam -o beam.inp --L=500 --nodes=21 --load=1000
cae inp template flat_plate -o plate.inp --Lx=200 --Ly=100 --pressure=5.0
```

---

## Python API

除了命令行，cae-cli 还提供完整的 Python API：

```python
from cae.inp import ModelBuilder, StaticStep
from cae.material import Elastic, Plastic
from cae.contact import ContactPair, SurfaceInteraction, SurfaceBehavior
from cae.enums import ContactType, PressureOverclosure, HardeningRule

# 构建模型
model = ModelBuilder()
model.add_node(1, (0, 0, 0))
model.add_node(2, (100, 0, 0))
model.add_element("C3D8", [1, 2, 3, 4, 5, 6, 7, 8])

# 添加材料（塑性）
elastic = Elastic(params=(210000, 0.3))
plastic = Plastic(stress=[200, 250], strain=[0, 0.1], hardening=HardeningRule.ISOTROPIC)
model.add_material("STEEL", elastic, plastic)

# 添加接触
si = SurfaceInteraction(name="STEEL_CONTACT")
sb = SurfaceBehavior(pressure_overclosure=PressureOverclosure.EXPONENTIAL, c0=0.05, p0=5e7)
cp = ContactPair(interaction=si, type=ContactType.SURFACE_TO_SURFACE, dep_surf=..., ind_surf=...)

# 添加载荷步
step = StaticStep(time_period=1.0, nlgeom=True)
step.add_boundary(nodes={1}, dofs={1: 0, 2: 0, 3: 0})
step.add_load(nodes={2}, dofs={3: -1000})

# 输出 INP
print(model.to_inp())
```

---

| 模型 | 大小 | 量化 | 最低显存 | 来源 |
|------|------|------|----------|------|
| `deepseek-r1-7b` | 4.9 GB | Q4_K_M | 6 GB | HuggingFace |
| `deepseek-r1-14b` | 9.0 GB | Q4_K_M | 8 GB | HuggingFace |
| `qwen2.5-7b` | 4.7 GB | Q4_K_M | 6 GB | HuggingFace |

> 💡 国内用户添加 `--mirror https://hf-mirror.com` 加速下载

---

## 兼容性验证

使用 **CalculiX 官方 ccx_2.23.test 测试集**（638 个 .inp 文件）：

| 测试 | 通过率 | 说明 |
|------|--------|------|
| INP 解析 | ✅ 638/638 (100%) | 100% |
| 求解执行 | ✅ 8/10 | 声学分析除外 |
| 格式转换 | ✅ 8/8 (100%) | 100% |

**638 个测试用例已提取参考数据**：
- 332 个案例包含位移参考值
- 149 个案例包含应力参考值
- 单元类型、边界条件、载荷类型等元数据完整
- 用于三层次诊断系统的 Level 2 参考案例对比

**覆盖单元类型：**
- 实体单元：C3D4/6/8/15/20（含二阶）
- 壳单元：S3/4/6/8（含减缩积分）
- 梁单元：B31/B32
- 弹簧单元：Spring1~Spring7
- 接触分析：Contact1~19、Mortar
- 热分析：稳态/瞬态/热-结构耦合
- 动力学：模态/频率响应/瞬态响应
- 非线性：几何非线性/材料非线性

---

## 项目结构

```
cae-cli/
├── cae/
│   ├── main.py              # CLI 入口 (Typer)
│   ├── enums.py             # 枚举定义 (50+ 类型)
│   ├── _utils.py            # 工具函数 (f2s 格式化)
│   ├── protocols.py         # 接口协议 (IKeyword/IStep)
│   ├── solvers/             # 求解器接口
│   │   ├── base.py         # 抽象基类
│   │   └── calculix.py     # CalculiX 实现
│   ├── inp/                 # INP 文件处理
│   │   ├── kw_list.json    # 135 关键词参数
│   │   ├── kw_tree.json    # 关键词分类
│   │   ├── template.py     # Jinja2 模板
│   │   ├── model_builder.py # Python 类模板 (CantileverBeam/FlatPlate)
│   │   ├── step_keywords.py # 载荷步关键词 (Amplitude/CLOAD/DLOAD/BOUNDARY/Coupling)
│   │   ├── equation.py     # 方程约束 (Equation/EQUATION)
│   │   └── steps.py        # 载荷步类 (Static/Dynamic/Frequency/Buckle)
│   ├── mesh/                # 网格处理
│   │   ├── element.py       # 单元类型定义
│   │   ├── surface.py       # 接触面/载荷面定义
│   │   ├── gmsh_runner.py  # Gmsh API
│   │   └── converter.py    # meshio 转换
│   ├── contact/             # 接触分析
│   │   ├── surface_interaction.py  # 表面相互作用
│   │   ├── surface_behavior.py     # 表面行为 (压力过盈)
│   │   ├── friction.py             # 摩擦模型
│   │   ├── contact_pair.py         # 接触对
│   │   ├── tie.py                  # 绑定接触
│   │   └── gap.py                  # 间隙单元 (Gap/GapUnit)
│   ├── coupling/            # 耦合约束
│   │   ├── coupling.py      # KINEMATIC/DISTRIBUTING 耦合
│   │   └── mpc.py           # MPC 多点约束
│   ├── material/            # 材料模型
│   │   ├── elastic.py       # 弹性模型 (ISO/ORTHO/ANISO)
│   │   ├── plastic.py       # 塑性模型 (等向/运动/组合硬化)
│   │   └── hyperelastic.py  # 超弹性模型 (Mooney-Rivlin/Arruda-Boyce/Ogden/Yeoh)
│   ├── viewer/              # 可视化
│   │   ├── frd_parser.py    # FRD 解析
│   │   ├── dat_parser.py    # DAT 解析
│   │   ├── _utils.py       # 应力工具 (von_mises/主应力/剪切应力)
│   │   ├── vtk_export.py    # VTK 导出
│   │   ├── pyvista_renderer.py  # PyVista 渲染引擎
│   │   ├── mesh_check.py    # 网格预览 HTML
│   │   ├── html_generator.py    # HTML 报告生成器
│   │   └── pdf_report.py    # PDF 报告生成器
│   ├── ai/                  # AI 功能
│   │   ├── llm_client.py    # LLM 接口
│   │   ├── explain.py       # 结果解读
│   │   ├── diagnose.py       # 三层诊断 (规则/案例/AI)
│   │   ├── reference_cases.py # 638 参考案例库
│   │   ├── prompts.py       # Prompt 模板库
│   │   └── suggest.py        # 优化建议
│   └── installer/           # 安装器
│       ├── solver_installer.py  # CalculiX 求解器
│       └── model_installer.py   # AI 模型
├── tests/                  # 测试用例 (100 passed)
└── examples/              # 示例文件
```

---

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| CLI | Typer + Rich | 命令行 + 美化输出 |
| 网格 | Gmsh 4.x | 自动网格划分 |
| 求解器 | CalculiX 2.22+ | 开源 FEA |
| 格式 | meshio 5.x | 多格式转换 |
| 可视化 | ParaView Glance | Web 3D  viewer |
| AI | llama-cpp-python | 本地 LLM |
| 模板 | Jinja2 | 参数化生成 |

---

## 开发

```bash
# 克隆
git clone https://github.com/yd5768365-hue/cae-cli
cd cae-cli

# 安装开发版
pip install -e ".[dev]"

# 测试
pytest tests/ -v

# 代码检查
ruff check cae/
```

---

## License

MIT
