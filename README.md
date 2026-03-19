# cae-cli

> 轻量化 CAE 命令行工具 — 一条命令跑仿真，一个链接看结果

机械系学生、小型实验室、装不动或买不起 ANSYS 的工程师的仿真工具。

## 特性

- **全流程自动化**: 网格划分 → 求解 → 可视化，一键完成
- **主流求解器**: 支持 CalculiX（开源 FEA）
- **交互式可视化**: 浏览器查看 VTK 结果（ParaView Glance）
- **INP 文件处理**: 解析、检查、修改、模板生成
- **AI 智能辅助**: 解读结果、诊断问题、优化建议
- **Python API**: 底层模块可独立使用

## 安装

```bash
pip install cae-cli
pip install cae-cli[ai]    # 可选：AI 功能
pip install cae-cli[mesh]   # 可选：高级网格功能
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

## 快速上手

```bash
# 1. 从模板生成 INP 文件
cae inp template cantilever_beam -o beam.inp
cae inp template flat_plate -o plate.inp --Lx=150 --pressure=2.0

# 2. 求解示例文件
cae solve examples/simple_beam.inp

# 3. 浏览器查看结果
cae view results/simple_beam/

# 4. 完整工作流（网格 + 求解 + 可视化）
cae run examples/bracket.step

# 5. 仅网格划分
cae mesh gen examples/box.step -o box.inp

# 6. 网格预览（CGX 风格）
cae mesh check box.inp
```

## 命令一览

### 核心命令

| 命令 | 说明 |
|------|------|
| `cae solve [file.inp]` | 执行 FEA 仿真 |
| `cae run [file.step]` | 全流程一键运行（网格→求解→可视化）|
| `cae view [results/]` | 浏览器查看仿真结果 |
| `cae convert [file]` | 格式转换（.frd/.msh/.inp/.vtu）|
| `cae solvers` | 列出求解器状态 |
| `cae install` | 安装/更新 CalculiX + AI 模型 |
| `cae info` | 显示配置路径与版本信息 |

### INP 文件处理

| 命令 | 说明 |
|------|------|
| `cae inp template --list` | 列出所有 INP 模板 |
| `cae inp template [name] -o file.inp` | 从模板生成 INP 文件 |
| `cae inp template [name] --params` | 查看模板参数说明 |
| `cae inp info [file.inp]` | 显示 INP 文件结构摘要 |
| `cae inp check [file.inp]` | 校验 INP 文件（对照 kw_list） |
| `cae inp show [file.inp] -k *MATERIAL` | 显示指定关键词块内容 |
| `cae inp show [file.inp] -k *MATERIAL -n STEEL` | 显示 NAME=STEEL 的材料块 |
| `cae inp modify [file.inp] -k *ELASTIC --set "210000, 0.3"` | 修改 INP 参数 |
| `cae inp modify [file.inp] -k *STEP --delete` | 删除指定块 |
| `cae inp suggest [file.inp] -r results/` | AI 生成修改建议 |
| `cae inp list` | 浏览关键词分类 |
| `cae inp list Mesh` | 查看 Mesh 类所有关键词 |
| `cae inp list -k *NODE` | 查看 *NODE 关键词详情 |

### 网格处理

| 命令 | 说明 |
|------|------|
| `cae mesh gen [file.step] -o file.inp` | Gmsh 网格划分 |
| `cae mesh check [file.inp]` | 网格预览（CGX 风格，生成 HTML 报告）|

### AI 功能

```bash
pip install cae-cli[ai]
cae install --model deepseek-r1-7b-qwen
```

| 命令 | 说明 |
|------|------|
| `cae explain [results/]` | AI 解读仿真结果 |
| `cae diagnose [results/]` | AI 诊断仿真问题 |
| `cae diagnose [results/] --no-ai` | 仅规则检测 |
| `cae suggest [results/]` | AI 生成优化建议 |

**CaqQuery 几何生成**（可选）：

```python
from cae.ai.cad_generator import CadGenerator, BeamParams, PlateParams

g = CadGenerator()
result = g.create_beam(BeamParams(length=100, width=20, height=30))
g.export_step(result.workplane, 'my_beam')
```

## 内置模板

| 模板 | 描述 | 关键参数 |
|------|------|----------|
| `cantilever_beam` | 悬臂梁（B32 梁单元）| L, n_nodes, load_value, load_type |
| `flat_plate` | 平板（S4 壳单元，四角固支）| Lx, Ly, n_x, n_y, pressure |

```bash
# 生成悬臂梁
cae inp template cantilever_beam -o beam.inp --L=200 --nodes=21 --load=500

# 生成平板
cae inp template flat_plate -o plate.inp --Lx=150 --Ly=75 --pressure=2.0
```

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
│   │   ├── __init__.py      # 解析器、修改器、验证器
│   │   ├── kw_list.json     # 135 个关键词参数定义
│   │   ├── kw_tree.json      # 关键词分类层级
│   │   ├── template.py       # 模板引擎
│   │   └── templates/        # INP 模板文件
│   ├── mesh/                # 网格处理
│   │   ├── gmsh_runner.py    # Gmsh Python API 封装
│   │   └── converter.py      # meshio 格式转换
│   ├── viewer/              # 可视化模块
│   │   ├── frd_parser.py    # CalculiX .frd 文件解析
│   │   ├── vtk_export.py     # .frd → .vtu 转换
│   │   ├── pyvista_renderer.py  # PyVista 渲染
│   │   ├── mesh_check.py     # CGX 风格网格预览
│   │   └── html_generator.py # HTML 报告生成
│   ├── installer/           # 安装器
│   │   ├── solver_installer.py  # CalculiX 安装
│   │   └── model_installer.py   # AI 模型安装
│   ├── ai/                 # AI 功能
│   │   ├── llm_client.py      # LLM 客户端
│   │   ├── explain.py         # AI 结果解读
│   │   ├── diagnose.py        # AI 问题诊断
│   │   ├── suggest.py         # AI 优化建议
│   │   ├── cad_generator.py   # CadQuery 几何生成
│   │   └── prompts.py         # Prompt 模板
│   └── config/              # 配置管理
│       └── __init__.py       # settings 单例
├── examples/               # 示例文件
│   ├── *.inp              # Abaqus 格式输入文件
│   └── *.step              # STEP 几何文件
└── tests/                  # 单元测试
```

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

## 工作流程

```
用户输入                    cae-cli 自动处理
─────────────────────────────────────────────────
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
    │                              └─→ cae convert ──→ .vtu

.inp 模板生成    ──→ cae inp template ──→ 参数化 .inp 文件
    │
    └─→ cae inp modify ──→ 修改后的 .inp 文件

└─→ cae run ──→ 完整流程（mesh + solve + view）
```

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

## 测试

```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/CalculiX\ 求解器单元测试.py
pytest tests/mesh\ 模块单元测试.py
pytest tests/viewer\ 模块单元测试.py
```

## License

MIT
