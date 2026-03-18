# cae-cli

> 轻量化 CAE 命令行工具 — 一条命令跑仿真，一个链接看结果

机械系学生、小型实验室、装不动或买不起 ANSYS 的工程师的仿真工具。

## 特性

- **全流程自动化**: 网格划分 → 求解 → 可视化，一键完成
- **主流求解器**: 支持 CalculiX（开源 FEA）
- **交互式可视化**: 浏览器查看 VTK 结果（ParaView Glance）
- **格式转换**: 支持 .frd → .vtu, .msh → .inp 等常用格式
- **Python API**: 底层模块可独立使用

## 安装

```bash
pip install cae-cli
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
# 1. 求解示例文件
cae solve examples/simple_beam.inp

# 2. 浏览器查看结果
cae view results/simple_beam/

# 3. 完整工作流（网格 + 求解 + 可视化）
cae run examples/bracket.step

# 4. 仅网格划分
cae mesh examples/box.step

# 5. 格式转换
cae convert results/output.frd -o results/output.vtu

# 6. 查看命令帮助
cae --help
cae solve --help
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `cae solve [file.inp]` | 执行 FEA 仿真 |
| `cae run [file.step]` | 全流程一键运行（网格→求解→可视化）|
| `cae mesh [file.step]` | 交互式网格划分（Gmsh）|
| `cae view [results/]` | 浏览器查看仿真结果 |
| `cae convert [file]` | 格式转换（.frd/.msh/.inp/.vtu）|
| `cae solvers` | 列出求解器状态 |
| `cae install` | 安装/更新 CalculiX + AI 模型 |
| `cae info` | 显示配置路径与版本信息 |
| `cae explain [results/]` | AI 解读结果（需要 Ollama）|
| `cae diagnose [results/]` | AI 诊断问题（需要 Ollama）|

## 项目结构

```
cae-cli/
├── cae/
│   ├── main.py          # CLI 入口（Typer）
│   ├── solvers/         # 求解器接口
│   │   ├── base.py      # BaseSolver 抽象类
│   │   ├── calculix.py  # CalculiX 求解器实现
│   │   └── registry.py # 求解器注册表
│   ├── mesh/            # 网格处理
│   │   ├── gmsh_runner.py  # Gmsh Python API 封装
│   │   └── converter.py     # meshio 格式转换
│   ├── viewer/          # 可视化模块
│   │   ├── frd_parser.py    # CalculiX .frd 文件解析
│   │   ├── vtk_export.py   # .frd → .vtu 转换
│   │   ├── server.py        # HTTP 服务器（ParaView Glance）
│   │   ├── pyvista_renderer.py  # PyVista 渲染
│   │   └── html_generator.py    # HTML 报告生成
│   ├── installer/       # 安装器
│   │   ├── solver_installer.py  # CalculiX 安装
│   │   └── model_installer.py   # AI 模型安装
│   └── ai/              # AI 功能（需要 Ollama）
├── examples/            # 示例文件
│   ├── *.inp           # Abaqus 格式输入文件
│   └── *.step           # STEP 几何文件
└── tests/               # 单元测试
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
    ├─→ cae mesh ──→ .msh (Gmsh 网格)
    │
.inp 网格文件  ──→ cae solve ──→ .frd + .dat (CalculiX 结果)
    │                              │
    │                              ├─→ cae view ──→ 浏览器可视化
    │                              │
    │                              └─→ cae convert ──→ .vtu
    │
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
| AI（可选）| Ollama + DeepSeek R1 |

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
