# DEV_LOG.md

## 2026年3月19日

### 新增：CAE-CLI AI 模式功能

- **问题描述**：用户需要完整的 AI 模式功能，包括 llama-cpp-python 外部进程支持、流式输出、AI 解读、规则检测 + AI 诊断、优化建议生成、CadQuery 基础部件生成。

- **解决方法**：

  1. 新增 `cae/ai/` 模块，包含以下文件：
     - `llm_client.py` — LLMClient 管理 llama-cpp-python，支持 direct/server 两种模式
     - `stream_handler.py` — StreamHandler 使用 rich.live.Live 实时显示 SSE 流
     - `prompts.py` — Prompt 模板库（explain/diagnose/suggest）
     - `explain.py` — AI 结果解读，解析 .frd 文件提取节点/单元/位移/应力统计
     - `diagnose.py` — 规则检测 + AI 诊断，支持收敛性/网格质量/应力集中/位移范围检测
     - `suggest.py` — 优化建议生成，基于诊断结果的规则 + AI 混合建议
     - `cad_generator.py` — CadGenerator 参数化几何创建（梁/圆柱/板），懒加载 cadquery
     - `__init__.py` — 模块导出（懒加载 heavy dependencies）

  2. 更新 `pyproject.toml`：
     - 新增 `ai` 可选依赖：`requests>=2.31`, `cadquery>=2.4`

  3. 更新 `main.py`：
     - 新增 `suggest` 命令：`cae suggest <results_dir> [--no-ai] [--stream/--no-stream]`

- **解决效果**：
  - `explain`、`diagnose`、`suggest` 三个 AI 命令完整可用
  - Direct 模式省内存（推荐 8GB 以下机器使用）
  - Server 模式支持多并发请求
  - 模块懒加载，不安装 ai 依赖时不会报错
  - CadQuery 几何生成支持参数化部件创建

- **关键复用**：
  - `cae/solvers/base.py:SolveResult` — 参考 dataclass 封装模式
  - `cae/solvers/calculix.py` — 复用 subprocess 进程管理逻辑
  - `cae/config/__init__.py:settings` — 直接使用配置单例
  - `cae/viewer/__init__.py` — 参考懒加载 `__getattr__` 模式
  - `cae/viewer/frd_parser.py:parse_frd()` — 直接使用解析 .frd 文件

### 问题1：llama-cpp-python 版本兼容

- **问题描述**：
  - 初始安装的 llama-cpp-python 0.3.2 不支持 DeepSeek-R1-Distill-Qwen-7B-Q2_K 模型
  - 错误：`unknown pre-tokenizer type: 'deepseek-r1-qwen'`

- **解决方法**：
  ```bash
  pip install --upgrade llama-cpp-python
  ```
  升级到 0.3.16 后模型可正常加载。

### 问题2：Direct API vs Server API

- **问题描述**：
  - llama-server 模式需要 ~2.3GB logits buffer，在部分机器上内存不足
  - Server 模式启动失败：`ArrayMemoryError: Unable to allocate 2.32 GiB`

- **解决方法**：
  - 重构 `LLMClient` 支持 Direct 模式
  - Direct 模式直接调用 `llama_cpp.Llama`，内存效率更高
  - 默认使用 Direct 模式，设置 `use_server=True` 可切换到 Server 模式
  - 降低默认 context_size=2048 避免内存问题

### 测试结果

```bash
# 测试 explain
$ cae explain results/cantilever
Success: True
Summary: 网格信息里有2650个节点和10388个单元...（中文解读正常）

# 测试 diagnose
$ cae diagnose results/cantilever
Success: True
Issue count: 1
[warning] mesh_quality: 节点/单元比例过低 (0.26)

# 测试 suggest
$ cae suggest results/cantilever
Success: True
Suggestions count: 1
[2] 优化网格划分: 网格质量警告...
```

---

## 2026年3月19日（下午）

### 项目全面优化

- **问题描述**：项目存在重复代码、缺少缓存策略、懒加载不完善等问题。

- **解决方法**：

  1. **新建 `cae/viewer/_utils.py` 共享工具模块**：
     - 提取 `von_mises()` 函数，消除 pyvista_renderer.py 和 vtk_export.py 的重复实现
     - 提取 `parse_numbers()` 数字解析工具
     - 提取 `find_frd()` 查找 .frd 文件的工具函数

  2. **更新 `cae/viewer/vtk_export.py`**：
     - 移除本地 `_von_mises()` 定义
     - 改用 `from cae.viewer._utils import von_mises`

  3. **更新 `cae/viewer/pyvista_renderer.py`**：
     - 移除本地 `_von_mises_from_tensor()` 定义（与 `_utils.von_mises` 重复）
     - 改用 `from cae.viewer._utils import von_mises`
     - 保留原有 `_find_field()` 工具函数（仅限本模块使用）

  4. **优化 `cae/solvers/calculix.py`**：
     - 添加 `@functools.lru_cache(maxsize=1)` 缓存 `_find_binary()` 结果
     - 避免每次 solve 时重复搜索 ccx 二进制文件
     - 添加 `import functools`

  5. **检查 `main.py` 懒加载**：
     - 确认 `gmsh`、`pyvista`、`llama` 相关导入均使用函数内 `from ... import` 模式
     - 无需额外修改

  6. **检查模块 `__all__` 导出**：
     - `cae/solvers/__init__.py` — 已有完整 `__all__` 和直接导入
     - `cae/ai/__init__.py` — 已有完整 `__all__` 和懒加载 `__getattr__`
     - `cae/viewer/__init__.py` — 已有完整 `__all__` 和懒加载 `__getattr__`

- **解决效果**：
  - 代码重复消除：`von_mises` 函数在两处重复定义 → 统一到 `_utils.py`
  - 缓存优化：`CalculixSolver._find_binary()` 结果被缓存，避免重复文件系统搜索
  - 模块结构清晰：重工具函数归入 `_utils.py`，公共 API 显式导出
  - 懒加载完善：所有 heavy dependencies 均通过 `__getattr__` 按需加载

---

## 2026年3月19日（傍晚）

### 新增：`cae/inp/` 模块 — .inp 解析与修改

- **问题描述**：用户希望支持"直接修改已有 .inp 文件"，参考 cae-master 的 kw_list.xml 结构。

- **解决方法**：

  1. **新建 `cae/inp/kw_list.json`**：
     - 从 cae-master `config/kw_list.xml` 转换而来
     - 135 个关键词的完整参数定义
     - 支持 form（Line/Int/Float/Bool/Combo/Text）、required、options、default 等属性

  2. **新建 `cae/inp/__init__.py`**：

     - `Block` 数据类：保留原始 INP 文本结构（comments/lead_line/data_lines），支持 `get_param()` / `set_param()` 获取和修改参数

     - `InpParser` 解析器：
       - `read_lines()` 递归处理 `*INCLUDE`
       - `split_on_blocks()` 分割为 Block 列表
       - `parse_params()` 解析关键词参数

     - `InpModifier` 修改器：
       - `find_blocks()` / `find_block()` 按关键词 + NAME 精确定位
       - `update_blocks()` 修改参数或数据行
       - `insert_block()` 插入新块
       - `delete_blocks()` 删除块
       - `write()` 重新生成 INP 文件

     - `replace_values()` 辅助函数：替换数据行中的数值

- **解决效果**：
  - 完整解析 .inp 文件，保留原始格式
  - 支持按关键词 + 参数精确定位修改
  - 可扩展：kw_list.json 可随时从 cae-master 同步更新

  3. **新增 `cae inp` CLI 命令组**：
     - `cae inp info model.inp` — 显示关键词统计摘要
     - `cae inp check model.inp` — 对照 kw_list.json 校验必填参数
     - `cae inp show model.inp -k *MATERIAL -n STEEL` — 显示指定块内容
     - `cae inp modify model.inp -k *MATERIAL -n STEEL --set E=210000` — 修改参数
     - `cae inp modify model.inp -k *STEP --delete` — 删除块

### Phase 3 完成 — 智能化

- **问题描述**：需要 AI 辅助修改建议 + 完整的格式保留。

- **解决方法**：

  1. **格式保留生成**：
     - `Block` 新增 `line_range` 字段，追踪原始文件行位置
     - `InpModifier.generate_preserving()` 保留原始注释、空行、块之间结构
     - `_clean_empty_lines()` 清理多余连续空行（最多保留2个）

  2. **kw_list 参数校验**：
     - `validate_block()` 校验单个 Block 的必填参数
     - `validate_inp()` 校验整个文件
     - `ValidationIssue` 数据类记录 severity/keyword/parameter/message

  3. **AI 辅助修改建议**：
     - `suggest_inp_modifications()` 生成修改建议（规则 + AI 混合）
     - `_rule_based_suggestions()` 自动检测常见问题：
       - 材料缺少密度定义
       - STEP 缺少分析 procedure
       - 边界条件未指定节点集
     - `_ai_suggestions()` 调用 LLM 基于 INP 内容生成具体修改建议
     - `_build_inp_summary()` 提取关键词统计、材料、载荷、STEP 信息供 AI 分析
     - `ModificationSuggestion` 数据类：category/severity/keyword/name/action/params/reason

  4. **新增 `cae inp suggest` 命令**：
     - `cae inp suggest model.inp [-r results_dir] [--no-ai] [--stream/--no-stream]`
     - 结合仿真结果（results_dir）分析最大位移/应力
     - 流式输出修改建议列表
