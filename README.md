# cae-cli

> 轻量化 CAE 命令行工具 — 一条命令跑仿真，一个链接看结果

机械系学生、小型实验室、装不动或买不起 ANSYS 的工程师的仿真工具。

## 特性

- **全流程自动化**: 网格划分 → 求解 → 可视化，一键完成
- **主流求解器**: 支持 CalculiX（开源 FEA）
- **交互式可视化**: 浏览器查看 VTK 结果（ParaView Glance）
- **INP 文件处理**: 解析、检查、修改、模板生成、关键词浏览
- **AI 智能辅助**: 解读结果、诊断问题、优化建议
- **Python API**: 底层模块可独立使用

## 安装

```bash
pip install cae-cli
pip install cae-cli[ai]    # 可选：AI 功能
pip install cae-cli[mesh]  # 可选：高级网格功能
```

**安装 CalculiX 求解器**:

```bash
cae install          # 自动下载安装（推荐）
```

**手动安装**:

```bash
# macOS
brew install calculix

# Ubuntu / Debian
sudo apt install calculix-ccx

# Windows: 从 https://calculix.org 下载并放到 PATH
```

---

## 全部功能列表

### 1. INP 文件处理

#### 1.1 模板生成

```bash
# 列出所有模板
cae inp template --list

# 查看模板参数
cae inp template cantilever_beam --params

# 从模板生成 INP 文件（使用默认参数）
cae inp template cantilever_beam -o beam.inp

# 从模板生成 INP 文件（自定义参数）
cae inp template cantilever_beam -o beam.inp --L=200 --nodes=21 --load=500
cae inp template flat_plate -o plate.inp --Lx=150 --Ly=75 --pressure=2.0
```

#### 1.2 文件解析与显示

```bash
# 显示 INP 文件结构摘要
cae inp info model.inp

# 显示指定关键词块的内容
cae inp show model.inp -k *MATERIAL
cae inp show model.inp -k *MATERIAL -n STEEL      # 按 NAME 精确查找
cae inp show model.inp -k *STEP
cae inp show model.inp -k *BOUNDARY
```

#### 1.3 文件校验

```bash
# 对照 kw_list.json 校验 INP 文件（检查必填参数）
cae inp check model.inp
```

#### 1.4 文件修改

```bash
# 修改指定关键词块的参数
cae inp modify model.inp -k *ELASTIC --set "210000, 0.3"
cae inp modify model.inp -k *MATERIAL -n STEEL --set "E=210000"
cae inp modify model.inp -k *BOUNDARY --set "1, 1, 3, 0.0"

# 修改数据行中的数值
cae inp modify model.inp -k *CLOAD --replace "1000, 2000"

# 删除指定块
cae inp modify model.inp -k *STEP --delete

# 插入新块
cae inp modify model.inp -k "*MATERIAL, NAME=NEW_STEEL" --insert

# 输出到新文件（保留原始文件）
cae inp modify model.inp -k *ELASTIC --set "210000, 0.3" -o modified.inp
```

#### 1.5 AI 修改建议

```bash
# 基于 INP 内容生成修改建议
cae inp suggest model.inp

# 结合仿真结果分析
cae inp suggest model.inp -r results/folder/
```

#### 1.6 关键词浏览

```bash
# 显示所有关键词分类
cae inp list

# 显示指定分类下的所有关键词
cae inp list Mesh
cae inp list Properties
cae inp list Step
cae inp list "Loads & BC"

# 显示关键词详细信息（参数列表）
cae inp list -k *NODE
cae inp list -k *BOUNDARY
cae inp list -k *MATERIAL
cae inp list -k *BEAM SECTION
```

### 2. 网格处理

```bash
# Gmsh 网格划分
cae mesh gen geometry.step -o mesh.inp
cae mesh gen geometry.step -o mesh.inp --mesh-size=2.0 --order=2

# 网格预览（CGX 风格，生成 HTML 报告）
cae mesh check mesh.inp
# 自动打开浏览器显示：
#   - 网格按单元类型着色
#   - 节点按 NSET 着色（不同颜色代表不同边界条件）
#   - CLOAD 载荷箭头可视化
```

### 3. FEA 求解

```bash
# 执行 FEA 仿真
cae solve model.inp
cae solve model.inp -o results/folder/      # 指定输出目录
cae solve model.inp -s calculix             # 指定求解器

# 全流程一键运行（网格 + 求解 + 可视化）
cae run geometry.step
```

### 4. 结果可视化

```bash
# 浏览器查看仿真结果（ParaView Glance）
cae view results/folder/

# 格式转换
cae convert results.frd -o output.vtu        # .frd → .vtu
cae convert mesh.msh -o output.inp         # .msh → .inp
cae convert results.vtu                     # 自动检测格式
```

### 5. AI 功能

```bash
pip install cae-cli[ai]
cae install --model deepseek-r1-7b-qwen
```

```bash
# AI 解读仿真结果
cae explain results/folder/
# 输出：
#   - 节点数、单元数
#   - 最大/最小位移及位置
#   - 最大/最小应力及位置
#   - 安全评价

# AI 诊断问题（规则检测 + AI 分析）
cae diagnose results/folder/
cae diagnose results/folder/ --no-ai       # 仅规则检测，无 AI
# 检测项：
#   - 收敛性问题
#   - 网格质量问题（单元比例、长宽比）
#   - 应力集中检测
#   - 位移范围异常

# AI 生成优化建议
cae suggest results/folder/
# 输出：
#   - 优先级建议（1-5）
#   - 预期改进效果
#   - 实现难度（easy/medium/hard）
```

### 6. 系统管理

```bash
# 查看求解器状态
cae solvers
# 显示：
#   - 求解器名称
#   - 安装状态
#   - 版本
#   - 支持格式

# 安装/更新 CalculiX + AI 模型
cae install
cae install --model deepseek-r1-7b-qwen   # 仅安装 AI 模型

# 显示配置信息
cae info
# 显示：
#   - 配置目录
#   - 数据目录
#   - 求解器目录
#   - 模型目录
#   - 默认求解器
#   - 当前 AI 模型
```

---

## 内置模板

| 模板 | 描述 | 关键参数 |
|------|------|----------|
| `cantilever_beam` | 悬臂梁（B32 梁单元）| title, E, L, width, height, n_nodes, load_type, load_value |
| `flat_plate` | 平板（S4 壳单元，四角固支）| title, E, Lx, Ly, thickness, n_x, n_y, load_type, pressure |

---

## 项目结构

```
cae-cli/
├── cae/
│   ├── main.py              # CLI 入口（Typer）
│   ├── solvers/             # 求解器接口
│   │   ├── base.py          # BaseSolver 抽象类
│   │   ├── calculix.py      # CalculiX 求解器实现
│   │   └── registry.py       # 求解器注册表
│   ├── inp/                 # INP 文件处理
│   │   ├── __init__.py      # 解析器（Block/InpParser/InpModifier）
│   │   ├── kw_list.json     # 135 个关键词参数定义
│   │   ├── kw_tree.json     # 关键词分类层级（7 大类）
│   │   ├── template.py      # 模板引擎
│   │   └── templates/       # INP 模板文件
│   ├── mesh/                # 网格处理
│   │   ├── gmsh_runner.py   # Gmsh Python API 封装
│   │   └── converter.py      # meshio 格式转换
│   ├── viewer/              # 可视化模块
│   │   ├── frd_parser.py    # CalculiX .frd 文件解析
│   │   ├── vtk_export.py    # .frd → .vtu 转换
│   │   ├── pyvista_renderer.py  # PyVista 渲染
│   │   ├── mesh_check.py    # CGX 风格网格预览
│   │   └── html_generator.py # HTML 报告生成
│   ├── installer/           # 安装器
│   │   ├── solver_installer.py  # CalculiX 安装
│   │   └── model_installer.py   # AI 模型安装
│   ├── ai/                  # AI 功能
│   │   ├── llm_client.py    # LLM 客户端（llama-cpp-python）
│   │   ├── explain.py       # AI 结果解读
│   │   ├── diagnose.py      # AI 问题诊断
│   │   ├── suggest.py       # AI 优化建议
│   │   ├── cad_generator.py # CadQuery 几何生成
│   │   └── prompts.py       # Prompt 模板
│   └── config/              # 配置管理
│       └── __init__.py      # settings 单例
├── examples/               # 示例文件
│   ├── *.inp               # Abaqus 格式输入文件
│   └── *.step               # STEP 几何文件
└── tests/                   # 单元测试
```

---

## 示例文件

| 文件 | 说明 |
|------|------|
| `examples/simple_beam.inp` | 简单梁单元测试（1 个 C3D8 单元）|
| `examples/simple_cantilever.inp` | 悬臂梁测试（2 个 C3D8 单元）|
| `examples/thermal.inp` | 热分析示例 |
| `examples/box.step` | 立方体几何（用于网格划分）|
| `examples/bracket.step` | 角支架几何 |
| `examples/plate_with_hole.step` | 带孔板几何 |
| `examples/shaft.step` | 轴类零件几何 |

---

## 兼容性测试

使用 CalculiX 官方 `ccx_2.23.test` 测试集（共 638 个 .inp 文件）进行批量验证：

| 阶段 | 测试内容 | 结果 |
|------|----------|------|
| Phase 1 | `inp info` 解析全部 638 个文件 | **638/638 OK** |
| Phase 2 | `solve` 求解 10 个样本文件 | **8/10 OK** |
| Phase 3 | `convert` 转换求解结果 (.frd → .vtu) | **8/8 OK** |

**Phase 2 失败文件说明：**
- `acou1.inp`、`acou2.inp` — 声学分析文件（acoustic analysis），需要特殊求解器配置

**测试覆盖的单元类型：**
- 实体单元：C3D4（四面体）、C3D6（五面体）、C3D8/C3D8R（六面体）、C3D15、C3D20/C3D20R
- 壳单元：S3、S4、S4R、S6、S8、S8R
- 梁单元：B31、B32
- 弹簧单元：Spring1~Spring7
- 接触分析：Contact1~Contact19、Mortar 接触
- 热分析：稳态热、瞬态热、热-结构耦合
- 动力学：模态分析、频率响应、瞬态响应
- 非线性：几何非线性、材料非线性

---

## 工作流程

```
用户输入                    cae-cli 自动处理
─────────────────────────────────────────────────────────────
.step 几何文件
    │
    ├─→ cae mesh gen ──→ .inp (Gmsh 网格)
    │
    └─→ cae mesh check ──→ HTML 预览（CGX 风格）

.inp 网格文件  ──→ cae solve ──→ .frd + .dat (CalculiX 结果)
    │                              │
    │                              ├─→ cae view ──→ 浏览器可视化
    │                              │
    │                              ├─→ cae explain ──→ AI 解读
    │                              │
    │                              ├─→ cae diagnose ──→ AI 诊断
    │                              │
    │                              └─→ cae convert ──→ .vtu

.inp 模板生成    ──→ cae inp template ──→ 参数化 .inp 文件
    │
    ├─→ cae inp modify ──→ 修改后的 .inp 文件
    │
    └─→ cae inp suggest ──→ AI 修改建议

└─→ cae run ──→ 完整流程（mesh + solve + view）
```

---

## 技术选型

| 模块 | 选择 |
|------|------|
| 语言 | Python 3.10+ |
| CLI 框架 | Typer + Rich |
| 网格 | Gmsh 4.x |
| 求解器 | CalculiX 2.22+ |
| 格式转换 | meshio 5.x |
| 可视化 | ParaView Glance (WebGL) |
| AI（可选）| llama-cpp-python + DeepSeek R1 |
| 模板引擎 | Jinja2 |

---

## CalculiX 输入文件注意

CalculiX 需要在 `*STEP ... *END STEP` 内部使用 `*NODE FILE` 和 `*EL FILE` 才能输出结果到 `.frd`:

```inp
*STEP
*STATIC
1., 1.
*CLOAD
3, 1, 1000.0
*NODE FILE
U
*EL FILE
S
*END STEP
```

- `*NODE FILE` / `*EL FILE` — 输出到 `.frd`（用于可视化）
- `*NODE PRINT` / `*EL PRINT` — 输出到 `.dat`（用于文本查看）

**cae-cli 会自动插入** `*NODE FILE` / `*EL FILE`，无需手动添加。

---

## 开发

```bash
# 克隆并安装
git clone https://github.com/yd5768365-hue/cae-cli
cd cae-cli
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v

# 代码风格检查
ruff check cae/
```

## License

MIT
