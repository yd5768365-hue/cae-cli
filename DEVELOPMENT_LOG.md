# Development Log

> Dated engineering notes for `cae-cli`. This log tracks implementation
> milestones and verification results rather than formal release notes.

## 2026-04-21 | Verified Docker solver smoke cases

### Completed

- Added real smoke examples for SU2, Code_Aster, and OpenFOAM under
  `examples/`.
- Verified a tutorial-derived SU2 CFD smoke case through `su2-runtime`
  using `examples/su2_inviscid_bump/inv_channel_smoke.cfg`.
- Verified a minimal Code_Aster smoke case through
  `simvia/code_aster:stable` using
  `examples/code_aster_minimal_smoke/case.comm`.
- Verified an OpenFOAM cavity smoke case through
  `microfluidica/openfoam:11` using
  `examples/openfoam_cavity_smoke` with `blockMesh && icoFoam`.
- Pushed commit `6558d62` (`feat: add verified solver docker smoke cases`)
  to `main`.

### Runtime and environment decisions

- Standardized the active Docker environment on the dedicated WSL distro
  `CAE-Docker` at `D:\WSL\CAE-Docker`.
- Switched the Docker registry setup in that distro to a multi-mirror
  configuration after `dockerproxy.net` became unreliable for some image
  namespaces.
- Kept the broken legacy `Ubuntu` distro out of the active Docker path
  instead of continuing to build on an unstable WSL instance.

### Code changes

- `cae/docker/generic.py`: copy solver sidecar inputs for SU2
  `*_FILENAME` references and Code_Aster `.export`-referenced local files
  into the mounted work directory.
- `cae/docker/images.py`: fixed runnable commands for Code_Aster,
  switched `openfoam-lite` to `microfluidica/openfoam:11`, and aligned the
  `su2-runtime` command with the image entrypoint.
- `tests/test_docker_feature.py`: expanded Docker feature coverage around
  smoke-case inputs and catalog behavior.

### Verification

```text
ruff check
python -m pytest
115 passed
```

### Runtime artifacts

- `results/su2-inviscid-bump-smoke/history.csv`
- `results/code-aster-smoke/docker-code_aster.log`
- `results/openfoam-cavity-smoke/docker-openfoam.log`

### Next

- Normalize solver output harvesting so logs, residuals, and result files
  can feed the diagnosis pipeline in a consistent shape.
- Add solver selection and preflight scoring on top of the current Docker
  catalog.
- Keep PINN as an augmentation layer after the traditional solver baseline
  remains stable and reproducible.

## 2026-04-21 | Cross-solver diagnosis bridge and next agent-routing step

### Completed locally

- Added a solver-output bridge so the diagnosis layer can recognize
  `calculix`, `su2`, `openfoam`, `code_aster`, and `elmer` result
  directories instead of assuming a CalculiX-only results layout.
- Unified diagnosis evidence intake across `docker-*.log`,
  `history.csv`, `.sta`, `.stderr`, `.dat`, and `.cvg`.
- Extended diagnosis JSON with a `solver_run` summary plus
  `meta.detected_solver` and `meta.solver_status`.
- Added lightweight non-CalculiX runtime/convergence diagnosis so Docker
  solver results can already produce structured issues.
- Verification after the bridge:

```text
ruff check
python -m pytest
121 passed
```

### Current working memory

The next highest-leverage step is no longer more Docker plumbing. It is to
push `solver_run` into `mcp_server` agent context so the Agent can branch by
solver status before choosing fixes or physics diagnosis.

### Next control point

- Extend MCP agent context with `solver_run.solver`, `solver_run.status`,
  `solver_run.status_reason`, and route-specific next actions.
- Route `failed` runs to runtime remediation first:
  image, command, sidecar inputs, mount path, environment, permissions.
- Route `not_converged` runs to convergence tuning:
  iteration budget, initialization, time-step control, solver settings.
- Route `success` runs with valid artifacts to result interpretation and
  physics diagnosis.
- Route `unknown` runs to evidence expansion:
  inspect logs, extract more metadata, avoid premature auto-fix.

### Decision rule

Do not let the Agent treat runtime failure as a physics issue. First decide
whether the run failed, ran but did not converge, or finished with usable
artifacts; only then choose diagnosis, auto-fix, or next solver action.

## 2026-04-21 | MCP agent context now routes by solver status

### Completed locally

- Extended `cae.mcp_server.tool_diagnose()` so the returned `agent` context
  now carries a compact `solver_run` summary in addition to the top-level
  diagnosis payload.
- Added an explicit `solver_status_gate` block to the MCP agent context with
  route metadata for `failed`, `not_converged`, `success`, and `unknown`.
- Added a top-level `routing` block so upstream MCP callers can branch on
  solver route, decision source, blocked actions, and the selected next step
  without re-parsing the nested `agent` context.
- Added route-specific `routing.followup` context so the first downstream
  caller can immediately see the route objective, artifact snapshot,
  prioritized issues, and route-specific checklist. Runtime remediation and
  convergence tuning now carry the richest follow-up state.
- Expanded `routing.followup` for `physics_diagnosis` and
  `evidence_expansion` so the caller can now read result-interpretation
  readiness, action priorities, similar-case hints, evidence classification
  gaps, and next collection targets from one place.
- Split `runtime_remediation` and `convergence_tuning` into standalone MCP
  tools that reuse the same diagnosis-routing pipeline as `tool_diagnose()`.
  They now return `applicable`, expected/actual route, route-specific
  follow-up context, and a structured route-mismatch message instead of
  forcing callers to inspect the full diagnosis payload first.
- Added standalone MCP tools for `physics_diagnosis` and
  `evidence_expansion`, completing the four-lane route-tool layout on top of
  the shared diagnosis and routing pipeline.
- Added route-specific action tools on top of the four-lane route API:
  runtime retry checks, convergence parameter suggestions, a grounded
  physics-interpretation prompt package, and an evidence-collection plan.
- Added solver-specific action rules on top of the generic action tools:
  Docker-focused runtime retry checks plus SU2/OpenFOAM-specific convergence
  parameter suggestions.
- Extended solver-specific action rules to cover Elmer and Code_Aster, and
  added deeper Docker runtime heuristics such as sidecar/mount-path failure
  modes and container writeability checks.
- Added solver-native Agent prompt packages for runtime remediation and
  convergence tuning, reusing the same structured action payloads so Agent
  callers can branch on solver family while staying aligned with the route
  tools and deterministic action builders.
- Extended `tool_diagnose()` so both `routing` and `agent` now carry the
  selected route action context directly. The Agent can continue from the
  diagnosis payload itself without making an extra follow-up tool call just
  to fetch runtime, convergence, physics, or evidence context.
- Added machine-stable route targets on top of the runtime/convergence
  action contexts so the selected route now carries deterministic
  `remediation_targets` or `edit_targets` instead of only free-form prompts
  and checklist text. This is the first bounded layer for controlled
  solver-native auto-fix candidates.
- Extended those runtime/convergence targets with bounded file/block scopes
  and allowed actions so Agent callers now receive aggregated
  `bounded_edit_scopes` alongside each route context instead of having to
  infer candidate files, config blocks, or safe edit boundaries from prompt
  text alone.
- Added explicit scope-level write policies plus route-level
  `controlled_edit_candidates` so runtime and convergence lanes can now
  distinguish inspect-only surfaces from proposal-ready bounded edits before
  any auto-fix layer is allowed to write.
- Mapped those proposal-ready candidates into deterministic
  `edit_payload_templates` with executor kinds, file targets, selector hints,
  operations, preconditions, and success criteria so Agent can now move from
  candidate selection into solver-native edit preparation without inferring
  its own patch shape.
- Added preview-only `edit_execution_plans` on top of the payload templates
  so each runtime or convergence candidate now carries a deterministic,
  single-pass execution plan with steps, artifacts, verification checks, and
  non-goals before any real write executor is introduced.
- Added a selection/execution entry point that can accept one
  `payload_id` or `plan_id` and expand it into a single preview-only
  `structured_patch_plan` or `parameter_change_plan`, so Agent can now
  request one deterministic pass instead of re-reading the entire aggregate
  route payload.
- Added render-ready previews on top of the selected execution output so the
  same single-pass entry point now returns either preview patch text or a
  concrete parameter-write payload template, while still staying preview-only
  and scoped to one bounded edit surface.
- Added preview-only `dry_run_validation` on top of the selected execution
  output so the same single-pass entry point now reports resolved target-file
  paths, selector/token matches, and single-surface write guards against the
  real `results_dir` before any future write executor is allowed to proceed.
- Pushed the selected route execution back into `tool_diagnose()` so both
  `agent` and `routing` contexts now carry a default `selected_route_execution`
  plus a compact `route_handoff` summary. Route-aware Agent flows can branch
  directly on `write_readiness` and `preferred_agent_branch` without
  re-fetching `plan_id` details from a second tool call.
- Converted that route handoff into an explicit `post_route_step` so Agent now
  receives concrete post-route actions such as
  `resolve_declared_targets`, `inspect_target_surface`, or
  `guarded_write_candidate` instead of having to infer them from the raw
  preview payload. The same step now carries branch-specific details like
  unresolved targets or verified target files.
- Added the first guarded write executor as `execute_guarded_edit_plan`. The
  current executor only permits bounded numeric parameter updates after
  `ready_for_write_guard` passes, writes a `.cae-cli.bak` backup before
  modifying the target file, and keeps structured runtime patch plans in
  explicit `unsupported_executor` preview-only mode.
- Extended guarded execution so the first structured patch subset can now
  write for real as well: Code_Aster `.export` reference rewrites. The
  executor can reconcile guarded `F comm`/`F mmed` path entries against the
  resolved artifact inputs while preserving the same backup-first,
  single-surface guard model. Other structured patch families still remain in
  explicit `unsupported_executor` mode until their text transforms are
  derived concretely enough to stay bounded.
- Extended guarded execution to the first OpenFOAM runtime-layout subset as
  well: `restore_case_layout` can now pass dry-run validation and create the
  missing required `0/`, `constant/`, and `system/` directories inside the
  selected case root. This keeps the same single-surface guard while avoiding
  speculative text edits in `controlDict` or `boundary` before a concrete
  replacement rule exists.
- Extended guarded execution to the first OpenFOAM runtime dictionary subset
  as well: `repair_dictionary_references` on `system/controlDict` can now
  restore a missing `writeInterval` entry when `application` and `startFrom`
  are already present, keeping the patch single-file, backup-first, and
  bounded to one deterministic dictionary key.
- Extended that OpenFOAM dictionary subset to `system/fvSolution` too:
  when the `solvers` block exists and `relaxationFactors` is missing, the
  guarded executor now restores one bounded `relaxationFactors` block and
  writes through the same backup-first contract. Selector checks now preserve
  `missing_tokens`, so partial dictionary matches can still pass write guard
  while explicitly exposing unresolved keys.
- Extended target resolution and selector dry-run coverage for wildcard
  surfaces such as `0/*`. Target checks now keep `matched_paths` (all
  resolved existing files) in addition to the first `matched_path`, and
  selector checks now read all resolved files per declared target instead of a
  single path.
- Extended guarded execution to the first OpenFOAM boundary-field subset:
  `repair_missing_entries` + `patch_field_entries` can now restore missing
  patch blocks inside `0/*` field `boundaryField` sections using bounded
  `zeroGradient` inserts, while preserving backup-first and single-surface
  write guards.
- Extended guarded execution to the first OpenFOAM boundary-name subset:
  `rename_declared_symbols` + `patch_name_entries` can now apply one
  deterministic rename in `constant/polyMesh/boundary` when exactly one
  unambiguous pair exists between boundary patch names and `0/*`
  `boundaryField` entries. This keeps the same backup-first, single-surface
  guard model and leaves ambiguous multi-rename cases explicitly unsupported.
- Extended that OpenFOAM boundary-name subset from single-pair rename to
  multi-pair rename when the pair inference remains provably unambiguous.
  The guarded executor now accepts multiple renames in one pass only when all
  pairings are mutual-best and collision-free; ambiguous mappings remain
  blocked with explicit pairing-error context.
- Extended OpenFOAM `patch_field_entries` guarded repair with template-aware
  inserts. Missing `boundaryField` entries are now generated from boundary
  patch type plus field metadata (`FoamFile class`/field name), including
  stable defaults such as `noSlip` for vector wall patches and
  `fixedValue + value uniform ...` for inlet-like names, while preserving
  fallback `zeroGradient` behavior for generic cases.
- Changed agent next-step selection so `failed`, `not_converged`, and
  `unknown` solver states override the generic diagnosis execution plan and
  force the Agent onto the correct first lane:
  runtime remediation, convergence tuning, or evidence expansion.
- Preserved the existing diagnosis execution plan for `success` runs so a
  converged solver can still flow directly into issue handling and physics
  interpretation.

### Verification

```text
ruff check cae/mcp_server.py tests/test_mcp_server.py
python -m pytest tests/test_mcp_server.py
54 passed
```

### Next

- Decide whether the guarded executor should consume the existing
  `post_route_step` contract directly or whether it should receive one thinner
  executor-specific handoff schema derived from it.
- Extend guarded execution beyond OpenFOAM layout restoration, OpenFOAM
  dictionary repairs, OpenFOAM boundary-field entry repair, OpenFOAM
  multi-pair boundary-name alignment (when unambiguous), and Code_Aster
  export rewrites so
  other runtime `structured_patch_plan` previews can graduate from
  `unsupported_executor` into bounded single-surface file edits with the same
  backup and guard model.
- Decide whether runtime patch previews and parameter-write payload previews
  should stay as separate executor families or converge on one write/report
  interface now that guarded execution has started to land.

## [2026-04-23] finetune-dataset-export + model-resolution-hardening

### Changed

- Added a reusable export pipeline at `scripts/export_finetune_dataset.py`
  that collects samples from:
  `tests/fixtures/diagnosis_cases`, `results/*`, `DEVELOPMENT_LOG.md`,
  `tests/test_mcp_server.py`, and `examples/*` smoke inputs.
- Added deterministic quality controls in the exporter:
  normalization, clipping, key-log extraction, dedupe, split assignment, and
  quality score filtering.
- Added an HQ subset export path (`*_hq*.jsonl` + `manifest_hq.json`) so
  fine-tuning can start from a cleaner high-confidence dataset.
- Removed hardcoded diagnose model defaults from runtime routing surfaces and
  switched to a unified resolver chain:
  `explicit model_name` -> `CAE_AI_MODEL` -> `settings.active_model`
  -> fallback `deepseek-r1:1.5b`.
- Added model-resolution telemetry to diagnosis metadata:
  `meta.resolved_model_name` + `meta.model_resolution_source`
  (`explicit` / `env` / `settings` / `default`) for MCP-side routing traces.
- Updated `cae main` AI entry points to use the same resolver and exposed
  `--model-name` on `cae diagnose` for explicit model pinning per run.

### Verification

```text
python scripts/export_finetune_dataset.py
ruff check cae/ai/llm_client.py cae/main.py cae/mcp_server.py tests/test_mcp_server.py tests/test_ai_model_resolution.py
python -m pytest tests/test_ai_model_resolution.py tests/test_mcp_server.py -q
59 passed
```

### Next

- Wire a single config-facing helper for MCP tool metadata so route tools can
  advertise the resolved model source (`explicit/env/settings/default`) in
  diagnostics payload metadata.
- Add one end-to-end smoke check for `cae diagnose --ai --model-name <ft-model>`
  to lock CLI behavior before full fine-tune rollout.

## [2026-04-24] solver-run-routing-context-hardening

### 变更

- 加固了 `cae/mcp_server.py` 的求解器状态路由：先把输入状态归一化，
  再决定进入哪条路线。现在 `FAILED`、`completed`、`not-converged`
  等写法都会映射到标准的 `failed` / `success` / `not_converged`。
- 扩展了 `agent.solver_run`，让 Agent 除了拿到数量统计，还能直接拿到
  标准化后的证据预览：`input_files`、`log_files`、`result_files`、
  `text_sources`。
- 在 `solver_status_gate` 和顶层 `routing` 上下文里加入
  `has_primary_log` 和 artifact 预览字段，后续工具可以少做重复解析。
- 扩展了 route payload 构建逻辑，让 `_selected_route_action_context` 和
  `_route_data_from_diagnosis_payload` 都带上紧凑的 `solver_run` 快照。
- 把同一份 `solver_run` 快照接入四条主要路线：
  `runtime_remediation`、`convergence_tuning`、`physics_diagnosis`、
  `evidence_expansion`。
- runtime、convergence、physics 三类提示词现在都会带
  `Solver-run evidence preview`，其中包括 `primary_log`、日志文件、输入文件、
  结果文件和文本证据源。
- evidence collection 现在也返回 `solver_run` 和 `available_evidence`，
  可以直接判断当前是否已有主日志、文本证据、运行日志和结果文件。
- 增加 MCP 回归测试，锁定：
  1. 大写或别名状态值也能正确路由；
  2. 标准化 artifact 预览能进入 agent/routing 上下文；
  3. physics/evidence 两条路线也能拿到统一的 `solver_run` 快照。
- 增加混合求解器 artifact 回归测试，覆盖 OpenFOAM 风格日志、
  SU2 `history.csv` 风格结果、重复路径、Windows 反斜杠路径、
  非 dict 类型 `text_sources` 和异常 count 值。
- 优化 `text_sources` 归一化逻辑：现在按路径去重，并优先保留更明确的
  `kind`，避免同一个日志同时以字符串和 dict 出现时重复进入 Agent 上下文。
- 新增 `solver_run_branch` 细分分支推断：在四条大路线之下，Agent 现在能
  继续看到更具体的执行方向，例如 `openfoam_case_repair`、
  `su2_cfl_iteration_tuning`、`result_interpretation`、
  `collect_result_artifacts`、`classify_mixed_evidence`。
- `solver_run_branch` 已接入 route action payload、runtime/convergence/physics
  提示词、route handoff 和 post-route step。这样 Agent 可以同时看到：
  当前大路线、写入守卫状态、以及由求解器证据推断出的下一层工作重点。
- 增加 MCP 回归断言，锁定 runtime、convergence、physics、evidence 四条路线
  都能返回预期的 `solver_run_branch`，并且 handoff/post-route step 不丢失该字段。
- 打通 `solver_run_branch` 与 guarded edit candidate 默认排序：
  `_preferred_edit_execution_plan_id` 现在会先给分支相关计划加权，再保留原有的
  目标文件具体程度、单目标、preview-only、人工复核等排序因素。
- OpenFOAM `openfoam_case_repair` 分支现在会优先选择
  `restore_case_layout` / case-tree / dictionary 相关计划；SU2
  `su2_cfl_iteration_tuning` 分支会优先选择 `CFL_NUMBER` / CFL / time-step
  相关计划，而不是只按目标文件路径顺序选择。
- 更新 MCP 测试，锁定 OpenFOAM 运行时修复默认选中
  `payload:runtime:openfoam_case_tree:openfoam_case_layout:restore_case_layout`，
  SU2 收敛调参默认选中
  `payload:convergence:cfl_or_time_step:su2_cfl_controls:decrease_cfl_growth`。
- 新增默认计划选择解释字段：`selected_route_execution`、route handoff 和
  post-route step 现在都会返回 `selection_reason` 与 `branch_score_breakdown`。
  其中 `branch_score_breakdown` 包含当前分支、分支得分、基础计划得分、总分、
  以及命中的分支关键词。
- 增加测试断言，锁定 OpenFOAM 选择原因中包含 `openfoam_case_repair` 和
  `restore_case_layout`，SU2 选择原因中包含 `su2_cfl_iteration_tuning` 和
  `decrease_cfl_growth` / `cfl_number`，避免后续排序逻辑退化成不可解释的黑盒。

### 验证

```text
ruff check cae/mcp_server.py tests/test_mcp_server.py
python -m pytest tests/test_mcp_server.py tests/test_solver_output_bridge.py -q
66 passed
```

### 下一步

- 下一轮可以继续把 `branch_score_breakdown` 用到提示词或 CLI 展示层，
  让用户在命令行里也能直接看到“为什么默认选择这个修复计划”。

## [2026-04-25] CLI-diagnose-route-explanation

### 变更

- 把 MCP 内部的 agent/routing 构建流程封装为
  `attach_agent_routing_context(payload)`，CLI 和 MCP 现在可以复用同一套
  路由、细分分支、默认计划选择和选择原因逻辑。
- `cae diagnose --json` 现在会输出完整的 `agent` 与 `routing` 字段，
  包括 `selected_route_execution.selection_reason` 和
  `routing.post_route_step.branch_score_breakdown`。
- 普通 `cae diagnose` 文本输出新增 “Agent 路由” 区块，显示：
  路线、决策来源、推荐下一步、细分分支、默认计划、写入准备状态、
  选择原因和选择评分。
- 增加 CLI 回归测试，锁定文本输出中必须包含
  `Agent 路由`、`路线: convergence_tuning`、`选择原因:`、`选择评分:`，
  并锁定 JSON 输出中必须包含 route/agent 解释字段。

### 验证

```text
ruff check cae/main.py cae/mcp_server.py tests/test_diagnose_json_cli.py tests/test_mcp_server.py
python -m pytest tests/test_diagnose_json_cli.py tests/test_mcp_server.py tests/test_solver_output_bridge.py -q
71 passed
```

### 下一步

- 可以继续把 route explanation 做成更紧凑的 CLI 表格，或者增加
  `--route-only` / `--explain-route` 这类轻量诊断入口，专门查看 Agent
  为什么选择当前路线和默认修复计划。

## [2026-04-25] developer-onboarding-clone-setup

### 变更

- 优化 README 的 Development 部分，把原来很短的开发命令扩展为可直接复制的
  新开发者上手流程。
- 新增推荐 clone 命令：
  `git clone --recurse-submodules https://github.com/yd5768365-hue/cae-cli.git`，
  同时补充已 clone 后初始化 submodule 的命令。
- 分别补充 Windows PowerShell 和 macOS/Linux 的虚拟环境创建、激活、pip 升级、
  最小开发安装和完整 extras 安装命令。
- 增加 PowerShell 执行策略阻止 `.venv` 激活时的临时解决命令。
- 增加本地验证命令、从源码运行 CLI 的 smoke 命令，以及 Docker/WSL 可选检查命令。

### 验证

```text
README-only change; no code behavior changed.
```

### 下一步

- 后续可以增加 `CONTRIBUTING.md`，把提交规范、测试范围、Docker/WSL 注意事项和
  PR 检查流程独立出来，README 只保留最短上手路径。
