<div align="center">
  <img src="logo.svg" alt="cae-cli" width="380">
  <h1>cae-cli</h1>
  <p>轻量化 CAE 命令行工具：一条命令跑仿真，一个链接看结果。</p>
  <p>基于 <a href="https://www.calculix.org/">CalculiX</a>，支持网格、求解、可视化、诊断与报告。</p>
</div>

<p align="center">
  <a href="https://github.com/yd5768365-hue/cae-cli">GitHub</a> ·
  <a href="https://pypi.org/project/cae-cxx/">PyPI</a> ·
  <a href="https://github.com/yd5768365-hue/cae-cli/issues">Issues</a>
</p>

---

## 特性

- 端到端流程：网格生成 -> 求解 -> 可视化 -> 诊断 -> PDF 报告
- 本地计算：核心计算与结果处理均在本机完成
- AI 诊断：规则层 + 参考案例 + 可选 AI 深度分析
- INP 工具链：检查、展示、修改、模板生成、建议修复
- 适合自动化：CLI 友好，便于脚本与批处理集成

---

## 安装

```bash
pip install cae-cxx
```

可选依赖：

```bash
# AI 能力
pip install "cae-cxx[ai]"

# 网格能力（Gmsh / meshio）
pip install "cae-cxx[mesh]"

# PDF 报告（weasyprint）
pip install "cae-cxx[report]"
```

安装 CalculiX：

```bash
cae install
```

---

## 快速开始

```bash
# 1) 生成一个 INP 模板
cae inp template cantilever_beam -o beam.inp

# 2) 运行求解
cae solve beam.inp

# 3) 浏览器查看结果（会自动把 frd 转成 vtu）
cae view results/

# 4) 诊断问题（可选）
cae diagnose results/

# 5) 生成 PDF 报告（可选）
cae report results/
```

---

## 命令总览

主命令：

- `cae solve`：执行 FEA 仿真求解
- `cae solvers`：查看求解器状态
- `cae info`：显示配置与版本信息
- `cae view`：浏览器查看仿真结果
- `cae convert`：手动 `.frd -> .vtu`
- `cae install`：安装 CalculiX
- `cae install ai`：安装 AI 模型
- `cae diagnose`：诊断仿真问题
- `cae report`：生成 PDF 报告
- `cae inp`：INP 文件解析与修改
- `cae mesh`：网格工具
- `cae model`：本地 Ollama 模型管理
- `cae setting`：工作目录/API Key 配置

`cae inp` 子命令：

- `info` / `check` / `show` / `modify` / `suggest` / `list` / `template`

`cae mesh` 子命令：

- `gen` / `check`

`cae model` 子命令：

- `list` / `pull` / `show` / `delete` / `set`

---

## 常见用法

```bash
# 求解并指定输出目录
cae solve model.inp -o results/

# INP 检查与查看
cae inp check model.inp
cae inp show model.inp -k *MATERIAL

# INP 修改（示例）
cae inp modify model.inp -k *ELASTIC --set "210000, 0.3"

# 网格划分
cae mesh gen geo.step -o mesh.inp

# 网格检查
cae mesh check mesh.inp

# 开启 AI 深度诊断
cae diagnose results/ --ai

# 指定 DeepSeek 诊断
cae diagnose results/ --ai --provider deepseek
```

---

## 项目结构

```text
cae-cli/
├─ cae/                  # 主代码
│  ├─ main.py            # CLI 入口（Typer）
│  ├─ inp/               # INP 解析、检查、修改与模板
│  ├─ mesh/              # 网格相关
│  ├─ solvers/           # 求解器抽象与注册
│  ├─ viewer/            # FRD 解析、转换、可视化与报告
│  ├─ ai/                # 诊断与 AI 能力
│  ├─ installer/         # 求解器/模型安装
│  └─ config/            # 配置管理
├─ tests/                # 测试
└─ README.md
```

---

## 开发

```bash
git clone https://github.com/yd5768365-hue/cae-cli
cd cae-cli
pip install -e ".[dev,ai,mesh,report]"
pytest tests/ -v
ruff check cae/
```

---

## 许可证

MIT，见 [LICENSE](LICENSE)。
