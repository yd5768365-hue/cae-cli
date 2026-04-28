<div align="center">
  <img src="logo.svg" alt="cae-cli" width="380">
  <h1>cae-cli</h1>
  <p>轻量级 CAE 命令行与桌面工具：一行命令运行仿真，一键查看结果。</p>
  <p>基于 <a href="https://www.calculix.org/">CalculiX</a>，支持网格、求解、可视化、诊断与报告全流程。</p>
</div>

<p align="center">
  <a href="https://github.com/yd5768365-hue/cae-cli">GitHub</a> |
  <a href="https://pypi.org/project/cae-cxx/">PyPI</a> |
  <a href="DEVELOPMENT_LOG.md">开发日志</a> |
  <a href="https://github.com/yd5768365-hue/cae-cli/issues">Issues</a>
</p>

---

## 功能特性

- **端到端工作流**：网格生成 → 求解 → 可视化 → 诊断 → PDF 报告
- **本地优先**：核心计算与结果处理在本地机器运行
- **AI 辅助诊断**：规则检查 + 参考案例 + 可选深度 AI 分析，三级诊断体系
- **INP 工具链**：检查、查看、修改、生成模板、修复建议
- **多求解器 Docker 工作流**：CalculiX、SU2、OpenFOAM、Code_Aster、Elmer 容器化运行
- **桌面 GUI**：Tauri + Vue 3 桌面应用，集成求解、可视化、诊断与 Docker 管理
- **MCP 集成**：通过 stdio MCP 服务器接入 OpenCode 等 AI 编码工具
- **微调数据集**：2000 条高质量诊断训练数据，支持 CAE 领域模型微调
- **自动化友好**：CLI 优先设计，适配脚本与批处理

---

## 安装

```bash
pip install cae-cxx
```

可选扩展：

```bash
# AI 诊断功能
pip install "cae-cxx[ai]"

# 网格支持 (Gmsh / meshio)
pip install "cae-cxx[mesh]"

# PDF 报告 (weasyprint)
pip install "cae-cxx[report]"

# MCP 服务器集成
pip install "cae-cxx[mcp]"
```

手动安装 CalculiX：

1. 从 [calculix.org](https://www.calculix.org/) 下载安装 CalculiX。
2. 确保 `ccx` / `ccx.exe` 在 `PATH` 中，或通过 `cae config` 配置 `solver_path`。

---

## 快速开始

```bash
# 1) 生成 INP 模板
cae inp template cantilever_beam -o beam.inp

# 2) 运行求解
cae solve beam.inp

# 3) 浏览器查看结果（FRD 自动转 VTU）
cae view results/

# 4) 诊断问题（可选）
cae diagnose results/

# 5) 生成 PDF 报告（可选）
cae report results/
```

---

## 命令总览

主命令：

| 命令 | 说明 |
| --- | --- |
| `cae solve` | 运行 FEA 求解 |
| `cae solvers` | 查看求解器可用性 |
| `cae info` | 显示配置与版本信息 |
| `cae view` | 浏览器中查看仿真结果 |
| `cae convert` | 手动转换 `.frd -> .vtu` |
| `cae diagnose` | 诊断仿真问题 |
| `cae docker` | Docker/容器化求解器工具 |
| `cae report` | 生成 PDF 报告 |
| `cae inp` | 解析与修改 INP 文件 |
| `cae mesh` | 网格工具 |
| `cae model` | 管理本地 Ollama 模型 |
| `cae config` | 管理工作区配置 |
| `cae-mcp` | 运行 MCP 服务器 |

`cae inp` 子命令：`info` / `check` / `show` / `modify` / `suggest` / `list` / `template`

`cae mesh` 子命令：`gen` / `check`

`cae model` 子命令：`list` / `pull` / `show` / `delete` / `set`

AI 诊断模型优先级：`--model-name` > `CAE_AI_MODEL` 环境变量 > `cae model set` > 默认 `deepseek-r1:1.5b`

---

## 桌面 GUI

`cae-gui/` 提供基于 Tauri + Vue 3 的桌面应用，无需命令行即可完成 CAE 工作流。

### 技术栈

- **前端**：Vue 3 + TypeScript + Vite + Tailwind CSS + Pinia
- **后端**：Tauri v2 (Rust)
- **可视化**：VTK.js 三维渲染 + ECharts 图表
- **图标**：Iconify

### 功能页面

| 页面 | 路由 | 功能 |
| --- | --- | --- |
| 项目管理 | `/project` | 打开/管理工作区目录 |
| 求解 | `/solve` | 配置并运行求解器 |
| 结果查看 | `/viewer` | VTK.js 三维可视化 |
| 诊断 | `/diagnose` | 运行诊断并查看结果 |
| Docker | `/docker` | 管理容器化求解器 |
| 设置 | `/settings` | 应用配置 |

### 开发运行

```bash
cd cae-gui
npm install

# 前端开发模式
npm run dev

# Tauri 桌面应用开发模式
npm run tauri dev

# 构建桌面安装包
npm run tauri build
```

GUI 通过 `useCaeCli` 组合式函数调用 CLI 后端，支持 `solve`、`diagnose`、`docker`、`inp` 等全部命令。

---

## 常用操作

```bash
# 指定输出目录求解
cae solve model.inp -o results/

# 检查与查看 INP 文件
cae inp check model.inp
cae inp show model.inp -k *MATERIAL

# 修改 INP 文件
cae inp modify model.inp -k *ELASTIC --set "210000, 0.3"

# 生成网格
cae mesh gen geo.step -o mesh.inp

# AI 深度诊断
cae diagnose results/ --ai

# 指定 AI 模型（适合微调 A/B 测试）
cae diagnose results/ --ai --model-name cae-ft:v1

# 导出结构化诊断 JSON
cae diagnose results/ --json
cae diagnose results/ --json-out out/diagnose.json

# 覆盖证据守卫配置
cae diagnose results/ --json --guardrails cae/ai/data/evidence_guardrails.json

# 启用诊断历史校准 (SQLite)
cae diagnose results/ --json --history-db out/diagnosis_history.db
```

---

## Docker 工作流

Docker 支持独立于原生求解命令。`cae solve` 用于本地 CalculiX，`cae docker ...` 用于容器化工作流。

### WSL Docker 一键部署

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-cae-cli-docker-wsl.ps1
```

### Docker Compose 运行时

运行时定义在 `docker.yml`，可从仓库根目录构建：

```bash
docker compose -f docker.yml up --build cae-cli
docker tag cae-cli:latest cae-cli:calculix
```

Compose 流程基于 `docker/cae-cli/Dockerfile` 构建本地 `cae-cli:latest` 镜像，验证 CalculiX 可执行文件，并保持资源独立。PowerShell 脚本封装同样的 Compose 路径，安装 Docker Engine 到 WSL 后，标记默认运行时为 `cae-cli:latest` / `cae-cli:calculix`。

- `-All`：同时拉取较大的可选求解器镜像
- `-Mirrors`：指定 Docker Hub 镜像源，如 `-Mirrors "https://dockerproxy.net,https://docker.1panel.live"`

### 容器化求解

```bash
# CalculiX
cae docker pull cae-cli --set-default
cae docker calculix model.inp -o results/model-docker

# OpenFOAM 腔体流动
cae docker pull openfoam-lite
cae docker run openfoam-lite examples/openfoam_cavity_smoke --cmd "bash -lc 'blockMesh && icoFoam'" -o results/openfoam-cavity-smoke

# Code_Aster
cae docker pull code-aster
cae docker run code-aster examples/code_aster_minimal_smoke/case.comm -o results/code-aster-smoke

# SU2 CFD
cae docker build-su2-runtime --tag local/su2-runtime:8.3.0
cae docker run su2-runtime examples/su2_inviscid_bump/inv_channel_smoke.cfg -o results/su2-inviscid-bump-smoke

# Elmer 多物理场
cae docker run elmer examples/elmer_steady_heat/case.sif -o results/elmer-heat
```

### 内置求解器镜像

| 别名 | 求解器 | 典型用途 |
| --- | --- | --- |
| `calculix-parallelworks` | CalculiX | 结构/热 FEM `.inp` 输入 |
| `code-aster` | Code_Aster | 非线性结构、接触、热力学 |
| `openfoam` / `openfoam-lite` | OpenFOAM | CFD 流体计算 |
| `su2-runtime` | SU2 | 本地构建的 SU2_CFD 运行时 |
| `elmer` | Elmer | 多物理场 FEM `.sif` 输入 |

已验证的冒烟测试示例：`openfoam_cavity_smoke`、`su2_inviscid_bump`、`code_aster_minimal_smoke`、`elmer_steady_heat`。

---

## MCP 服务器

`cae-cli` 可作为 MCP 服务器通过 `stdio` 运行，供 OpenCode 等 AI 编码工具调用。

```bash
pip install "cae-cxx[mcp]"
cae-mcp
```

提供的 MCP 工具：

| 工具 | 说明 |
| --- | --- |
| `cae_health` | 健康检查 |
| `cae_solvers` | 查看求解器 |
| `cae_solve` | 运行求解 |
| `cae_diagnose` | 诊断问题 |
| `cae_inp_check` | 检查 INP 文件 |
| `cae_docker_status` | Docker 状态 |
| `cae_docker_catalog` | 求解器目录 |
| `cae_docker_recommend` | 推荐求解器 |
| `cae_docker_images` | 列出镜像 |
| `cae_docker_pull` | 拉取镜像 |
| `cae_docker_run` | 运行容器 |
| `cae_docker_build_su2_runtime` | 构建 SU2 运行时 |
| `cae_docker_calculix` | 运行 CalculiX 容器 |

返回格式：成功 `{"ok": true, "data": ...}`，失败 `{"ok": false, "error": {"code": "...", "message": "..."}}`

OpenCode 配置示例：

```json
{
  "mcpServers": {
    "cae-cli": {
      "command": "python",
      "args": ["-m", "cae.mcp_server"]
    }
  }
}
```

---

## 诊断与守卫

`cae diagnose --json` 导出带证据标注的结构化问题：

- `evidence_line`：`file:line: 摘录` 证据定位
- `evidence_score`：置信度 `[0,1]`
- `evidence_support_count`：独立支撑文件数
- `evidence_conflict`：矛盾标注

守卫阈值按类别配置：

- 默认配置：`cae/ai/data/evidence_guardrails.json`
- CLI 覆盖：`--guardrails <path>`
- 环境变量：`CAE_EVIDENCE_GUARDRAILS_PATH=<path>`

历史一致性校准（可选）：

- CLI：`--history-db <path>`
- 环境变量：`CAE_DIAG_HISTORY_DB_PATH=<path>`

当证据薄弱或矛盾时，严重级别自动降级（如 `error -> warning`）以减少误报。

---

## 微调数据集

`cae-cli` 提供结构化诊断微调数据集，用于训练 CAE 领域语言模型。

### v2 数据集（291 条）

位于 `cae_cli_v2/`，从项目测试用例、求解器日志和路由策略导出。

```text
cae_cli_v2/
├── all.jsonl              # 完整记录（含元数据 + messages）
├── train.jsonl            # 训练集 (221)
├── val.jsonl              # 验证集 (36)
├── test.jsonl             # 测试集 (34)
├── *_hq.jsonl             # 高质量子集 (quality_score >= 0.9)
└── manifest.json          # 数据集清单
```

### v2-2000 扩展数据集（2000 条）

位于 `cae_cli_v2_2000/`，扩展了更丰富的错误场景、错误诊断纠正、证据守卫检查、风险评分和求解器家族检测。

```text
cae_cli_v2_2000/
├── all.jsonl              # 2000 条完整记录
├── train.jsonl            # 训练集 (~1525)
├── val.jsonl              # 验证集 (~260)
├── test.jsonl             # 测试集 (~215)
├── *_chat.jsonl           # 纯对话格式（适配主流微调框架）
├── *_hq.jsonl             # 高质量子集 (quality_score >= 0.9, ~1485)
└── manifest.json          # 数据集清单
```

**20 种任务类型**：

| 任务类型 | 说明 | 条数 |
| --- | --- | --- |
| `status_reason_routing_augmented` | 运行时状态原因映射到求解器路由 | 518 |
| `evidence_guardrail_check` | 证据守卫阈值检查 | 367 |
| `fixture_route_mapping` | 问题路由到诊断通道 | 269 |
| `risk_score_calculation` | 诊断问题风险评分 | 165 |
| `solver_route_decision_augmented` | 增强求解器门控路由 | 124 |
| `guarded_executor_decision_augmented` | 守卫写入资格评估 | 104 |
| `status_reason_routing` | 状态原因映射 | 62 |
| `issue_key_extraction` | 从 INP+stderr 提取诊断标签 | 61 |
| `inp_keyword_validation` | CalculiX INP 关键字验证 | 54 |
| `wrong_diagnosis_correction` | 错误诊断纠正与解释 | 27 |
| ... | （其余 10 种） | ... |

**数据集特点**：

- 同时包含**正确诊断**和**错误诊断纠正**样本，支持对比训练
- 确定性路由策略：`failed→runtime_remediation`、`not_converged→convergence_tuning`、`success→physics_diagnosis`、`unknown→evidence_expansion`
- 多求解器覆盖：CalculiX、SU2、OpenFOAM、Code_Aster、Elmer
- 守卫执行器写入安全决策与备份策略
- 证据守卫阈值通过/失败结果
- 风险评分含类别感知严重度权重

重新生成数据集：

```bash
python scripts/export_finetune_dataset.py          # v2 (291 条)
python scripts/generate_2000_training_data.py       # v2-2000 (2000 条)
```

---

## 项目结构

```text
cae-cli/
|-- cae/                    # Python 核心代码
|   |-- main.py              # CLI 入口 (Typer)
|   |-- mcp_server.py        # MCP stdio 服务器
|   |-- docker/              # Docker/容器化求解器
|   |-- runtimes/            # 运行时适配器（原生/WSL Docker）
|   |-- inp/                 # INP 解析、检查、编辑、模板
|   |-- mesh/                # 网格功能
|   |-- solvers/             # 求解器抽象与注册
|   |-- viewer/              # FRD 解析、转换、可视化、报告
|   |-- ai/                  # 诊断与 AI 功能
|   |   |-- diagnose.py       # 三级诊断引擎
|   |   |-- fix_rules.py      # 自动修复规则
|   |   |-- solver_output.py  # 跨求解器输出桥接
|   |   `-- data/             # 诊断数据（守卫配置、参考案例）
|   |-- installer/           # 求解器/模型安装
|   `-- config/              # 配置管理
|-- cae-gui/                # Tauri + Vue 3 桌面 GUI
|   |-- src/                  # Vue 前端源码
|   |-- src-tauri/            # Tauri/Rust 后端
|   `-- dist/                 # 前端构建产物
|-- scripts/                # 构建、导出、部署脚本
|-- tests/                  # 测试
|   `-- fixtures/             # 诊断用例 fixture
|-- examples/               # 求解器冒烟测试示例
|-- docker.yml              # Docker Compose 运行时定义
`-- README.md
```

---

## 开发

```bash
git clone --recurse-submodules https://github.com/yd5768365-hue/cae-cli.git
cd cae-cli
```

### Windows PowerShell

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip

# 最小开发安装（CLI、诊断、lint、测试）
python -m pip install -e ".[dev]"

# 完整开发安装
python -m pip install -e ".[dev,ai,mesh,report,mcp]"
```

若 PowerShell 阻止虚拟环境激活：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pip install -e ".[dev,ai,mesh,report,mcp]"
```

### 验证

```bash
python -m ruff check cae tests
python -m pytest tests/ -v
```

### 运行 CLI

```bash
cae --help
cae diagnose tests/fixtures/diagnosis_cases/convergence/not_converged
cae diagnose tests/fixtures/diagnosis_cases/convergence/not_converged --json
```

### Docker/WSL 检查

```bash
cae docker status
cae docker catalog
cae docker recommend "CFD smoke test"
```

---

## 许可证

MIT. See [LICENSE](LICENSE).
