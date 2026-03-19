# cae-cli

> **轻量化 CAE 命令行工具** — 一条命令跑仿真，一个链接看结果

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![CalculiX](https://img.shields.io/badge/CalculiX-2.22+-orange.svg)](https://www.calculix.org/)
[![HuggingFace](https://img.shields.io/badge/AI-DeepSeek%20R1-blueviolet.svg)](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B-GGUF)

**机械学生 | 独立工程师 | 小型实验室** — 用不起 ANSYS/LABA 的替代方案

---

## 5 秒快速上手

```bash
# 安装 (30 秒)
pip install cae-cli && cae install

# 生成悬臂梁模板
cae inp template cantilever_beam -o beam.inp

# 求解 + 查看结果
cae solve beam.inp && cae view results/
```

**结果预览** → 浏览器自动打开 3D 云图（ParaView Glance）

---

## 核心能力

### 仿真全流程

```
几何文件 (.step) ──► 网格 (.inp) ──► 求解 (.frd) ──► 可视化 (浏览器)
                          │                │
                      cae mesh gen     cae solve
                      cae mesh check   cae view
```

| 功能 | 命令 | 说明 |
|:----:|------|------|
| 网格划分 | `cae mesh gen geo.step -o mesh.inp` | Gmsh 自动网格 |
| 网格预览 | `cae mesh check mesh.inp` | HTML 报告 |
| 执行仿真 | `cae solve model.inp` | CalculiX 求解 |
| 3D 可视化 | `cae view results/` | 浏览器打开 |
| 一键运行 | `cae run geo.step` | 全自动 |

### INP 文件处理（135 关键词）

| 功能 | 命令 |
|------|------|
| 结构摘要 | `cae inp info model.inp` |
| 校验 | `cae inp check model.inp` |
| 显示块 | `cae inp show model.inp -k *MATERIAL -n STEEL` |
| 修改 | `cae inp modify model.inp -k *ELASTIC --set "210000, 0.3"` |
| 关键词浏览 | `cae inp list Mesh` |
| 模板生成 | `cae inp template cantilever_beam -o model.inp` |
| AI 建议 | `cae inp suggest model.inp` |

### AI 助手

```bash
# 安装模型 (~5GB)
cae model install deepseek-r1-7b

# AI 解读仿真结果
cae explain results/

# AI 诊断问题（收敛性、网格质量、应力集中）
cae diagnose results/

# AI 优化建议
cae suggest results/
```

### 格式转换

```bash
.frd → .vtu    cae convert result.frd -o out.vtu
.msh → .inp    cae convert mesh.msh -o out.inp
```

---

## 安装

```bash
# 基础安装
pip install cae-cli

# 完整安装（含 AI + 网格）
pip install cae-cli[ai,mesh]
```

**安装求解器：**

| 系统 | 命令 |
|------|------|
| 自动 | `cae install` |
| macOS | `brew install calculix` |
| Ubuntu | `sudo apt install calculix-ccx` |
| Windows | [calculix.org](https://calculix.org) 下载 |

---

## 命令速查

### `cae solve` — 求解

```bash
cae solve model.inp                    # 标准求解
cae solve model.inp -o results/       # 输出到目录
cae solve model.inp -t 3600           # 超时 1 小时
```

### `cae mesh` — 网格

```bash
cae mesh gen geo.step -o mesh.inp              # 生成网格
cae mesh gen geo.step -o mesh.inp -s 2.0      # 网格尺寸 2.0
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

### `cae model` — AI 模型

```bash
cae model list                                      # 模型列表
cae model install deepseek-r1-7b                    # 安装
cae model install deepseek-r1-7b -m hf-mirror.com  # 镜像
cae model info deepseek-r1-7b                       # 信息
cae model uninstall deepseek-r1-7b                  # 卸载
```

### `cae test` — 测试

```bash
cae test                     # 官方测试集（638 文件）
cae test --sample 20        # 采样 20 个
cae test --quiet             # 静默
```

### `cae` — 其他

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

| 模板 | 命令 | 说明 | 单元 |
|------|------|------|------|
| 悬臂梁 | `cae inp template cantilever_beam -o beam.inp` | 简支/悬臂 | B32 |
| 平板 | `cae inp template flat_plate -o plate.inp` | 四角固支 | S4 |

**参数覆盖：**
```bash
cae inp template cantilever_beam -o beam.inp --L=500 --nodes=21 --load=1000
cae inp template flat_plate -o plate.inp --Lx=200 --Ly=100 --pressure=5.0
```

---

## 内置 AI 模型

| 模型 | 大小 | 量化 | 最低显存 |
|------|------|------|----------|
| `deepseek-r1-7b` | 4.9 GB | Q4_K_M | 6 GB |
| `deepseek-r1-14b` | 9.0 GB | Q4_K_M | 8 GB |
| `qwen2.5-7b` | 4.7 GB | Q4_K_M | 6 GB |

**国内镜像：** `--mirror https://hf-mirror.com`

---

## 兼容性验证

使用 **CalculiX 官方测试集**（638 个 .inp 文件）：

| 测试 | 通过率 | 说明 |
|------|--------|------|
| INP 解析 | **638/638** | 100% |
| 求解执行 | **8/10** | 声学分析除外 |
| 格式转换 | **8/8** | 100% |

**覆盖单元：** C3D4/6/8/15/20、S3/4/6/8、B31/32、Spring1-7、热分析、接触、动力学、非线性

---

## 项目结构

```
cae-cli/
├── cae/
│   ├── main.py              # CLI 入口
│   ├── solvers/             # 求解器
│   │   ├── base.py         # 抽象基类
│   │   └── calculix.py     # CalculiX 实现
│   ├── inp/                 # INP 处理
│   │   ├── kw_list.json    # 135 关键词
│   │   ├── kw_tree.json    # 分类层级
│   │   └── template.py     # 模板引擎
│   ├── mesh/                # 网格
│   │   ├── gmsh_runner.py
│   │   └── converter.py
│   ├── viewer/              # 可视化
│   │   ├── frd_parser.py   # FRD 解析
│   │   ├── vtk_export.py   # VTK 导出
│   │   └── mesh_check.py   # 网格预览
│   ├── ai/                  # AI 功能
│   │   ├── llm_client.py   # LLM 接口
│   │   ├── explain.py      # 结果解读
│   │   └── diagnose.py      # 问题诊断
│   ├── installer/            # 安装器
│   │   ├── solver_installer.py
│   │   └── model_installer.py
│   └── config/              # 配置
├── test/
│   └── official.py          # 批量测试
└── examples/                # 示例
```

---

## 技术栈

| 组件 | 技术 |
|------|------|
| CLI | Typer + Rich |
| 网格 | Gmsh 4.x |
| 求解器 | CalculiX 2.22+ |
| 格式 | meshio 5.x |
| 可视化 | ParaView Glance |
| AI | llama-cpp-python |
| 模板 | Jinja2 |

---

## 开发

```bash
git clone https://github.com/yd5768365-hue/cae-cli
cd cae-cli
pip install -e ".[dev]"

pytest tests/ -v       # 测试
ruff check cae/        # 检查
```

---

## License

MIT
