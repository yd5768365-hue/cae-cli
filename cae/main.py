# CLI 入口
"""
cae-cli 主入口
CLI 框架：Typer + Rich

已实现命令：
  cae solve [FILE]        — 调用 CalculiX 执行仿真         （第一周）
  cae solvers             — 列出已注册求解器及安装状态      （第一周）
  cae info                — 显示配置路径信息                （第一周）
  cae view [RESULTS_DIR]  — 浏览器查看 VTK 仿真结果        （第二周）
  cae convert [FRD_FILE]  — 手动转换 .frd → .vtu           （第二周）
  cae mesh [GEO_FILE]     — 交互式网格划分（Gmsh）          （第三周）
  cae run [MODEL_FILE]    — 全流程一键运行                  （第三周）
  cae inp                  — INP 文件解析、检查、修改         （第四周）
  cae test                 — CalculiX 官方测试集批量测试    （第四周）

后续周次将补充：
  cae install / cae explain / cae diagnose / cae suggest
"""
from __future__ import annotations

import os
# 确保子进程使用 UTF-8 编码（避免 Windows GBK 编码问题）
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import box

from cae.config import settings
from cae.solvers.registry import get_solver, list_solvers

# ------------------------------------------------------------------ #
# mesh 命令组
# ------------------------------------------------------------------ #

mesh_app = typer.Typer(help="[bold]Mesh 网格工具[/bold] — 网格划分与检查")


@mesh_app.command(name="check")
def mesh_check(
    inp_file: Path = typer.Argument(..., help=".inp 文件路径（用于网格预览）"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出 HTML 路径"),
    browser: bool = typer.Option(True, "--browser/--no-browser", help="完成后打开浏览器"),
) -> None:
    """
    [bold]网格检查[/bold] — 在求解前预览网格、边界条件和载荷

    解析 .inp 文件，渲染网格可视化，快速检查模型设置是否正确。
    类似 CGX 的实时预览效果。

    \b
    示例：
      cae mesh check model.inp
      cae mesh check model.inp -o mesh_report.html
    """
    from cae.viewer.mesh_check import render_mesh_check, generate_mesh_check_html

    console.print()
    console.print(Panel.fit(
        "[bold cyan]cae mesh check[/bold cyan] — 网格预览",
        border_style="cyan",
    ))
    console.print()

    out_path = output or Path("mesh_check_report.html")
    screenshot_path = out_path.with_suffix(".png")

    result = render_mesh_check(inp_file, screenshot_path)

    if not result.success:
        err_console.print(f"\n  {result.error}\n")
        raise typer.Exit(1)

    summary = result.summary
    console.print(f"  [green][OK][/green] 解析成功")
    console.print(f"  节点: {summary.n_nodes:,}  单元: {summary.n_elements:,}")
    console.print(f"  节点集: {summary.n_nsets}  单元集: {summary.n_elsets}")
    console.print(f"  边界条件: {len(summary.boundaries)}  CLOAD: {len(summary.cloads)}")
    console.print()

    if result.warnings:
        for w in result.warnings:
            console.print(f"  [yellow][!][/yellow] {w}")
        console.print()

    # 生成 HTML
    generate_mesh_check_html(summary, screenshot_path, out_path, inp_file.name)
    console.print(f"  报告已生成: [green]{out_path}[/green]")

    # 自动打开浏览器
    if browser:
        import webbrowser
        webbrowser.open(f"file://{out_path.resolve()}")
        console.print(f"  已在浏览器中打开\n")


# ------------------------------------------------------------------ #
# inp 命令组
# ------------------------------------------------------------------ #

inp_app = typer.Typer(help="[bold]INP 文件解析与修改[/bold] — 解析、检查、修改 Abaqus/CalculiX .inp 文件")


@inp_app.command()
def info(
    inp_file: Path = typer.Argument(..., help=".inp 文件路径"),
) -> None:
    """[bold]显示 .inp 文件结构摘要[/bold]"""
    from cae.inp import InpParser

    console.print()
    console.print(Panel.fit("[bold cyan]cae inp info[/bold cyan] — INP 文件结构", border_style="cyan"))
    console.print()

    try:
        parser = InpParser()
        blocks = parser.parse(inp_file)
    except Exception as exc:
        err_console.print(f"\n  解析失败: {exc}\n")
        raise typer.Exit(1)

    # 按关键词分组统计
    kw_count: dict[str, int] = {}
    kw_names: dict[str, list[str]] = {}
    for b in blocks:
        name = b.keyword_name
        kw_count[name] = kw_count.get(name, 0) + 1
        n = b.get_param("NAME")
        if n:
            kw_names.setdefault(name, []).append(n)

    table = Table(title="关键词统计", box=box.ROUNDED)
    table.add_column("关键词", style="cyan")
    table.add_column("数量", justify="right", style="yellow")
    table.add_column("名称（NAME）", style="green")

    for kw, cnt in sorted(kw_count.items()):
        names = ", ".join(kw_names.get(kw, [])[:5])
        if len(kw_names.get(kw, [])) > 5:
            names += f" ... (+{len(kw_names[kw]) - 5})"
        table.add_row(kw, str(cnt), names or "-")

    console.print(table)
    console.print(f"\n  共 {len(blocks)} 个块，{len(kw_count)} 种关键词\n")


@inp_app.command()
def check(
    inp_file: Path = typer.Argument(..., help=".inp 文件路径"),
) -> None:
    """[bold]校验 .inp 文件（对照 kw_list.json）[/bold]"""
    from cae.inp import InpParser, load_kw_list

    console.print()
    console.print(Panel.fit("[bold cyan]cae inp check[/bold cyan] — INP 文件校验", border_style="cyan"))
    console.print()

    try:
        parser = InpParser()
        blocks = parser.parse(inp_file)
    except Exception as exc:
        err_console.print(f"\n  解析失败: {exc}\n")
        raise typer.Exit(1)

    kw_list = load_kw_list()
    unknown_kw = []
    missing_required: list[tuple[str, str]] = []

    for b in blocks:
        kw_def = kw_list.get(b.keyword_name)
        if kw_def is None:
            if b.keyword_name not in unknown_kw:
                unknown_kw.append(b.keyword_name)
        else:
            # 检查必填参数
            for arg in kw_def.get("arguments", []):
                if arg.get("required") and not b.get_param(arg["name"]):
                    missing_required.append((b.keyword_name, arg["name"]))

    if unknown_kw:
        console.print(f"  [yellow]未知关键词 ({len(unknown_kw)}):[/yellow]")
        for kw in unknown_kw[:10]:
            console.print(f"    {kw}")
        if len(unknown_kw) > 10:
            console.print(f"    ... (+{len(unknown_kw) - 10})")
        console.print()

    if missing_required:
        console.print(f"  [yellow]缺少必填参数 ({len(missing_required)}):[/yellow]")
        seen = set()
        for kw, arg in missing_required[:10]:
            key = f"{kw}:{arg}"
            if key not in seen:
                console.print(f"    {kw} → {arg} (必填)")
                seen.add(key)
        console.print()

    if not unknown_kw and not missing_required:
        console.print("  [green]校验通过：未发现问题[/green]\n")
    else:
        console.print(f"  共 {len(blocks)} 个块，已对照 kw_list.json 校验\n")


@inp_app.command()
def show(
    inp_file: Path = typer.Argument(..., help=".inp 文件路径"),
    keyword: str = typer.Option(None, "--keyword", "-k", help="关键词，如 *MATERIAL"),
    name: str = typer.Option(None, "--name", "-n", help="NAME 参数值"),
    limit: int = typer.Option(20, "--limit", "-l", help="最大显示行数"),
) -> None:
    """[bold]显示指定关键词块的内容[/bold]"""
    from cae.inp import InpModifier

    try:
        mod = InpModifier(inp_file)
    except Exception as exc:
        err_console.print(f"\n  解析失败: {exc}\n")
        raise typer.Exit(1)

    blocks = mod.find_blocks(keyword=keyword.upper() if keyword else None, name=name)
    if not blocks:
        kw_hint = f" 关键词 '{keyword}'" if keyword else ""
        name_hint = f" NAME='{name}'" if name else ""
        console.print(f"  未找到{kw_hint}{name_hint}的块\n")
        raise typer.Exit(0)

    console.print(f"  找到 {len(blocks)} 个匹配的块：\n")
    for i, b in enumerate(blocks):
        console.print(f"  [cyan]--- Block {i+1}: {b.keyword_name} ---[/cyan]")
        if b.lead_line:
            console.print(f"    {b.lead_line}")
        if b.data_lines:
            for line in b.data_lines[:limit]:
                console.print(f"    {line}")
            if len(b.data_lines) > limit:
                console.print(f"    ... (+{len(b.data_lines) - limit} 行)")
        console.print()


@inp_app.command()
def modify(
    inp_file: Path = typer.Argument(..., help=".inp 文件路径"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件路径"),
    keyword: str = typer.Option(None, "--keyword", "-k", help="关键词，如 *MATERIAL"),
    name: str = typer.Option(None, "--name", "-n", help="NAME 参数值"),
    set_param: list[str] = typer.Option([], "--set", help="设置参数，格式 KEY=VALUE"),
    delete: bool = typer.Option(False, "--delete", help="删除匹配的块"),
) -> None:
    """[bold]修改 .inp 文件（按关键词+NAME 定位）[/bold]"""
    from cae.inp import InpModifier

    if keyword is None and name is None and not delete:
        err_console.print("\n  请指定 --keyword 或 --name，或使用 --delete\n")
        raise typer.Exit(1)

    out_path = output or inp_file.with_suffix(".modified.inp")

    try:
        mod = InpModifier(inp_file)
    except Exception as exc:
        err_console.print(f"\n  加载失败: {exc}\n")
        raise typer.Exit(1)

    if delete:
        n = mod.delete_blocks(keyword=keyword.upper() if keyword else None, name=name)
        console.print(f"  已删除 {n} 个块\n")

    if set_param:
        params = {}
        for p in set_param:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k.strip()] = v.strip()
        if params:
            n = mod.update_blocks(
                keyword=keyword.upper() if keyword else None,
                name=name,
                params=params,
            )
            console.print(f"  已更新 {n} 个块：{params}\n")

    mod.write(out_path)
    console.print(f"  已写入: [green]{out_path}[/green]\n")


@inp_app.command()
def suggest(
    inp_file: Path = typer.Argument(..., help=".inp 文件路径"),
    results_dir: Optional[Path] = typer.Option(
        None, "--results", "-r", help="结果目录（用于结合诊断结果）"
    ),
    no_ai: bool = typer.Option(False, "--no-ai", help="只用规则建议，不用 AI"),
    stream: bool = typer.Option(True, "--stream/--no-stream"),
) -> None:
    """[bold]AI 生成 INP 修改建议[/bold]"""
    from cae.inp import suggest_inp_modifications
    from cae.ai.llm_client import LLMClient

    console.print()
    console.print(Panel.fit("[bold cyan]cae inp suggest[/bold cyan] — INP 修改建议", border_style="cyan"))
    console.print()

    # 收集诊断问题（如果提供了 results_dir）
    diagnose_issues = None
    if results_dir is not None:
        from cae.viewer._utils import find_frd
        frd_file = find_frd(results_dir)
        if frd_file is not None:
            from cae.viewer.frd_parser import parse_frd
            try:
                frd_data = parse_frd(frd_file)
                # 取最大位移和最大应力作为诊断依据
                if frd_data.results:
                    last = frd_data.results[-1]
                    if last.displacements:
                        max_disp = max(abs(v) for vals in last.displacements.values() for v in vals)
                        console.print(f"  最大位移: {max_disp:.4e}")
                    if last.stresses:
                        max_stress = max(abs(v) for vals in last.stresses.values() for v in vals)
                        console.print(f"  最大应力: {max_stress:.4e}")
            except Exception:
                pass

    # AI client
    client = None
    if not no_ai:
        client = LLMClient()
        if not client.is_running():
            console.print("  llama-server 未运行，使用规则建议\n")
            client = None
        else:
            console.print("  AI 正在分析，请稍候...\n")

    result = suggest_inp_modifications(inp_file, diagnose_issues, client, stream=stream)

    if not result.success:
        err_console.print(f"\n  {result.error}\n")
        raise typer.Exit(1)

    if result.suggestions:
        console.print(f"  [bold]共 {len(result.suggestions)} 条建议：[/bold]\n")
        for i, s in enumerate(result.suggestions, 1):
            icon = {"high": "[red]![/red]", "medium": "[yellow]~[/yellow]", "low": "[green]-[/green]"}.get(s.severity, "-")
            console.print(f"  {i}. {icon} [{s.category}] {s.action.upper()} {s.target_keyword}"
                          + (f" NAME={s.target_name}" if s.target_name else ""))
            console.print(f"     原因: {s.reason}")
            if s.params:
                console.print(f"     参数: {s.params}")
            console.print()
    else:
        console.print("  [green]未发现问题，无需修改建议[/green]\n")


# ------------------------------------------------------------------ #
# cae inp list — 浏览关键词分类
# ------------------------------------------------------------------ #

@inp_app.command("list")
def list_keywords_cmd(
    category: Optional[str] = typer.Argument(
        None,
        help="分类名称（如 Mesh/Properties/Step）",
        show_default=False,
    ),
    keyword: Optional[str] = typer.Option(
        None, "--keyword", "-k",
        help="关键词名称（如 *NODE）",
        show_default=False,
    ),
) -> None:
    """[bold]浏览关键词分类[/bold] — 查看所有分类或指定分类下的关键词"""
    from cae.inp import list_keywords, get_keyword_info

    if keyword:
        # 显示指定关键词的详细信息
        info = get_keyword_info(keyword)
        if not info["known"]:
            console.print(f"  [yellow]未知关键词: {keyword}[/yellow]")
            return

        console.print()
        console.print(Panel.fit(f"[bold cyan]{info['keyword']}[/bold cyan]", border_style="cyan"))
        console.print(f"  路径: {' > '.join(info['path'])}")
        console.print(f"  分类: {info['category']}")
        if info["args"]:
            console.print("  参数:")
            for arg in info["args"]:
                req_mark = "[red]*[/red]" if arg.get("required") else "  "
                form = arg.get("form", "Line")
                opts = f" ({', '.join(arg['options'])})" if arg.get("options") else ""
                console.print(f"    {req_mark} {arg['name']}: {form}{opts}")
                if arg.get("default"):
                    console.print(f"        默认值: {arg['default']}")
        console.print()
        return

    if category:
        # 显示指定分类下的关键词
        kws = list_keywords(category)
        if not kws:
            available = [c for c in _get_inp_categories() if not c.startswith("_")]
            console.print(f"  [yellow]未知分类: {category}[/yellow]")
            console.print(f"  可用分类: {', '.join(available)}")
            return

        console.print()
        console.print(Panel.fit(f"[bold cyan]{category}[/bold cyan] — {len(kws)} 个关键词", border_style="cyan"))
        for kw in sorted(kws):
            console.print(f"  {kw}")
        console.print()
    else:
        # 显示所有分类
        tree = _get_inp_tree()
        console.print()
        console.print(Panel.fit("[bold cyan]关键词分类[/bold cyan]", border_style="cyan"))
        for coll_name, coll_data in tree.get("Collections", {}).items():
            if coll_name.startswith("_"):
                continue
            kws = list_keywords(coll_name)
            console.print(f"\n  [bold]{coll_name}[/bold] ({len(kws)})")
            # 显示前5个关键词作为示例
            sample = sorted(kws)[:5]
            for kw in sample:
                console.print(f"    {kw}")
            if len(kws) > 5:
                console.print(f"    ... 还有 {len(kws) - 5} 个")


def _get_inp_tree():
    from cae.inp import load_kw_tree
    return load_kw_tree()


def _get_inp_categories():
    from cae.inp import load_kw_tree
    tree = load_kw_tree()
    return list(tree.get("Collections", {}).keys())


# ------------------------------------------------------------------ #
# cae inp template — 生成 INP 模板
# ------------------------------------------------------------------ #

@inp_app.command()
def template(
    name: Optional[str] = typer.Argument(None, help="模板名称"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出文件路径"),
    list_templates: bool = typer.Option(False, "--list", help="列出所有可用模板"),
    show_params: bool = typer.Option(False, "--params", help="显示模板参数"),
    title: Optional[str] = typer.Option(None, "--title", help="模型标题"),
    E: Optional[float] = typer.Option(None, "--E", help="弹性模量 (MPa)"),
    L: Optional[float] = typer.Option(None, "--L", help="长度 (mm)"),
    Lx: Optional[float] = typer.Option(None, "--Lx", help="板长 (mm)"),
    Ly: Optional[float] = typer.Option(None, "--Ly", help="板宽 (mm)"),
    pressure: Optional[float] = typer.Option(None, "--pressure", help="均匀压力 (MPa)"),
    load_value: Optional[float] = typer.Option(None, "--load", help="载荷值"),
    load_type: Optional[str] = typer.Option(None, "--load-type", help="载荷类型 (force/moment/pressure)"),
    n_nodes: Optional[int] = typer.Option(None, "--nodes", help="节点数"),
    n_elements: Optional[int] = typer.Option(None, "--elements", help="单元数"),
    n_x: Optional[int] = typer.Option(None, "--n-x", help="X方向节点数"),
    n_y: Optional[int] = typer.Option(None, "--n-y", help="Y方向节点数"),
    thickness: Optional[float] = typer.Option(None, "--thickness", help="板厚 (mm)"),
) -> None:
    """[bold]生成 INP 模板[/bold] — 使用 Python 类生成参数化 .inp 文件"""
    from cae.inp.model_builder import CantileverBeam, FlatPlate

    # 列出模板
    if list_templates:
        console.print()
        console.print(Panel.fit("[bold cyan]可用模板[/bold cyan]", border_style="cyan"))
        console.print("\n  [bold]cantilever_beam[/bold] — 悬臂梁 (B32 梁单元)")
        console.print("    参数: --L, --load, --nodes, --load-type, --E")
        console.print("\n  [bold]flat_plate[/bold] — 平板 (S4 壳单元，四角固支)")
        console.print("    参数: --Lx, --Ly, --thickness, --n-x, --n-y, --pressure, --load-type")
        console.print()
        return

    # 如果没有指定 name，显示帮助
    if name is None:
        console.print("  [yellow]请指定模板名称[/yellow]")
        console.print("  使用 --list 查看所有模板")
        return

    # 生成 INP 内容
    try:
        if name == "cantilever_beam":
            # 收集参数
            kwargs = {}
            if title is not None:
                kwargs["title"] = title
            if E is not None:
                kwargs["E"] = E
            if L is not None:
                kwargs["L"] = L
            if load_value is not None:
                kwargs["load_value"] = load_value
            if n_nodes is not None:
                kwargs["n_nodes"] = n_nodes
            if n_elements is not None:
                kwargs["n_elements"] = n_elements
            if load_type is not None:
                kwargs["load_type"] = load_type

            beam = CantileverBeam(**kwargs)
            content = beam.to_inp()

        elif name == "flat_plate":
            # 收集参数
            kwargs = {}
            if title is not None:
                kwargs["title"] = title
            if E is not None:
                kwargs["E"] = E
            if Lx is not None:
                kwargs["Lx"] = Lx
            if Ly is not None:
                kwargs["Ly"] = Ly
            if pressure is not None:
                kwargs["pressure"] = pressure
            if load_value is not None:
                kwargs["load_value"] = load_value
            if load_type is not None:
                kwargs["load_type"] = load_type
            if n_x is not None:
                kwargs["n_x"] = n_x
            if n_y is not None:
                kwargs["n_y"] = n_y
            if thickness is not None:
                kwargs["thickness"] = thickness

            plate = FlatPlate(**kwargs)
            content = plate.to_inp()

        else:
            console.print(f"  [red]未知模板: {name}[/red]")
            console.print(f"  可用模板: cantilever_beam, flat_plate")
            console.print("  使用 --list 查看所有模板")
            return

        # 写入文件
        out_path = output or Path(f"{name}.inp")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

        console.print(f"  [green]生成成功: {out_path}[/green]")
        console.print(f"  使用 --params 查看所有参数")

    except Exception as e:
        console.print(f"  [red]生成失败: {e}[/red]")


# ------------------------------------------------------------------ #
# App 初始化
# ------------------------------------------------------------------ #

app = typer.Typer(
    name="cae",
    help="轻量化 CAE 命令行工具 — 一条命令跑仿真，一个链接看结果",
    add_completion=False,
    rich_markup_mode="rich",
    no_args_is_help=True,
)
app.add_typer(inp_app, name="inp")
app.add_typer(mesh_app, name="mesh")

# ------------------------------------------------------------------ #
# cae model - AI 模型管理
# ------------------------------------------------------------------ #

model_app = typer.Typer(
    name="model",
    help="[bold]AI 模型管理[/bold] — 下载、安装、查看模型",
    no_args_is_help=True,
)


@model_app.callback()
def model_callback():
    """AI 模型管理命令组"""
    pass


@model_app.command(name="install")
def model_install(
    model_name: str = typer.Argument(..., help="模型名称（如 deepseek-r1-7b）"),
    mirror: Optional[str] = typer.Option(None, "--mirror", "-m", help="下载镜像 URL"),
) -> None:
    """
    [bold]下载并安装 AI 模型[/bold]

    从 Hugging Face 下载 GGUF 模型文件到 ~/.cae-cli/models/

    \b
    示例：
      cae model install deepseek-r1-7b
      cae model install deepseek-r1-7b --mirror https://hf-mirror.com
    """
    from cae.installer.model_installer import ModelInstaller

    console.print()
    console.print(Panel.fit(f"[bold cyan]cae model install[/bold cyan] — 安装 AI 模型", border_style="cyan"))
    console.print()

    mi = ModelInstaller()

    # 检查是否已安装
    if mi.is_installed(model_name):
        console.print(f"  [green]模型已安装:[/green] {model_name}")
        info = mi._find_model(model_name)
        if info:
            console.print(f"  路径: {mi.models_dir / info.filename}")
        return

    # 显示模型信息
    info = mi._find_model(model_name)
    if info:
        console.print(f"  [bold]模型:[/bold] {info.description}")
        console.print(f"  [bold]大小:[/bold] ~{info.size_gb} GB")
        console.print(f"  [bold]来源:[/bold] huggingface.co/{info.repo_id}")
    else:
        console.print(f"  [yellow]警告:[/yellow] 未找到模型元数据，将作为自定义模型下载")
    console.print()

    console.print("  这可能需要几分钟，取决于网络速度...")
    console.print()

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  TimeElapsedColumn(), console=console) as progress:
        task = progress.add_task("  下载中...", total=None)

        def _progress(pct: float, msg: str) -> None:
            progress.update(task, description=f"  {msg}", completed=pct * 100)

        result = mi.install(model_name, progress_callback=_progress, mirror=mirror)

    if result.success:
        console.print()
        console.print(f"  [green]安装成功！[/green]")
        console.print(f"  路径: {result.install_path}")

        # 询问是否激活
        console.print()
        activate = console.input("  [bold]设为默认模型？[/bold] [y/N]: ")
        if activate.lower() == "y":
            mi.activate(model_name)
            console.print("  [green]已设为默认模型[/green]")
    else:
        console.print()
        console.print(f"  [red]安装失败: {result.error_message}[/red]")
        raise typer.Exit(code=1)


@model_app.command(name="list")
def model_list() -> None:
    """
    [bold]列出已知模型[/bold]

    显示所有可用模型及其安装状态
    """
    from cae.installer.model_installer import ModelInstaller, KNOWN_MODELS

    console.print()
    console.print(Panel.fit("[bold cyan]可用模型列表[/bold cyan]", border_style="cyan"))
    console.print()

    mi = ModelInstaller()
    table = Table(
        "名称", "大小", "描述", "状态",
        box=box.ROUNDED,
        header_style="bold cyan",
    )

    for info in KNOWN_MODELS.values():
        status = "[green]已安装[/green]" if mi.is_installed(info.name) else "[dim]未安装[/dim]"
        table.add_row(
            f"[bold]{info.name}[/bold]",
            f"{info.size_gb:.1f} GB",
            info.description,
            status,
        )

    console.print(table)
    console.print()

    # 显示已安装的文件
    installed = mi.list_installed()
    if installed:
        console.print(f"  已安装文件 ({len(installed)}):")
        for f in installed:
            size_mb = f.stat().st_size / (1024 * 1024)
            console.print(f"    - {f.name} ({size_mb:.1f} MB)")
    else:
        console.print("  暂无已安装的模型文件")


@model_app.command(name="info")
def model_info(
    model_name: str = typer.Argument(None, help="模型名称（留空则显示默认模型）"),
) -> None:
    """
    [bold]显示模型详细信息[/bold]

    查看模型元数据、路径、SHA256 校验码等
    """
    from cae.installer.model_installer import ModelInstaller, KNOWN_MODELS

    mi = ModelInstaller()

    # 如果未指定，显示默认模型
    if not model_name:
        from cae.config import settings
        model_name = settings.active_model or "（无）"

    console.print()
    console.print(Panel.fit(f"[bold cyan]模型信息: {model_name}[/bold cyan]", border_style="cyan"))
    console.print()

    # 查找模型信息
    info = mi._find_model(model_name)
    model_path = mi.get_install_path(model_name)
    installed = model_path.exists()

    # 基本信息
    console.print(f"  [bold]名称:[/bold] {model_name}")
    console.print(f"  [bold]安装路径:[/bold] {model_path}")
    console.print(f"  [bold]状态:[/bold] {'[green]已安装[/green]' if installed else '[dim]未安装[/dim]'}")

    if info:
        console.print(f"  [bold]描述:[/bold] {info.description}")
        console.print(f"  [bold]大小:[/bold] ~{info.size_gb} GB")
        console.print(f"  [bold]来源:[/bold] huggingface.co/{info.repo_id}")
        console.print(f"  [bold]文件名:[/bold] {info.filename}")
        if info.sha256:
            console.print(f"  [bold]SHA256:[/bold] {info.sha256[:16]}...")

    # 校验信息
    if installed:
        console.print()
        console.print("  [bold]文件校验:[/bold]")
        verify = mi.verify_file(model_path, info.sha256 if info else "")
        if verify.success:
            console.print(f"    [green]文件完整[/green]")
        else:
            console.print(f"    [yellow]未校验或校验失败[/yellow]")
        size_mb = model_path.stat().st_size / (1024 * 1024)
        console.print(f"    文件大小: {size_mb:.1f} MB")


@model_app.command(name="uninstall")
def model_uninstall(
    model_name: str = typer.Argument(..., help="模型名称"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
) -> None:
    """
    [bold]卸载 AI 模型[/bold]

    删除模型文件（默认需要确认）
    """
    mi = ModelInstaller()
    model_path = mi.get_install_path(model_name)

    if not model_path.exists():
        console.print(f"  [yellow]模型未安装: {model_name}[/yellow]")
        return

    # 确认
    if not force:
        console.print()
        confirm = console.input(f"  [bold]确认删除 {model_path.name}？[/bold] [y/N]: ")
        if confirm.lower() != "y":
            console.print("  已取消")
            return

    try:
        model_path.unlink()
        console.print(f"  [green]已删除: {model_path.name}[/green]")
    except Exception as e:
        console.print(f"  [red]删除失败: {e}[/red]")
        raise typer.Exit(code=1)


app.add_typer(model_app, name="model")

import sys
# Windows MSYS 环境：强制 stdout/stderr 使用 UTF-8
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(legacy_windows=False, force_terminal=True)
err_console = Console(stderr=True, style="bold red", legacy_windows=False)

# ------------------------------------------------------------------ #
# cae solve
# ------------------------------------------------------------------ #

@app.command()
def solve(
    inp_file: Optional[Path] = typer.Argument(
        None,
        help=".inp 输入文件路径（交互模式下可省略）",
        show_default=False,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="结果输出目录（默认 results/<job_name>/）",
        show_default=False,
    ),
    solver: str = typer.Option(
        None,
        "--solver", "-s",
        help="求解器名称（默认使用配置中的 default_solver）",
        show_default=False,
    ),
    timeout: int = typer.Option(
        3600,
        "--timeout",
        help="求解超时秒数",
    ),
) -> None:
    """
    [bold]执行 FEA 仿真求解[/bold]

    \b
    示例：
      cae solve bracket.inp
      cae solve bracket.inp --output ./my_results
      cae solve  （纯交互模式）
    """
    console.print()
    console.print(Panel.fit(
        "[bold cyan]cae solve[/bold cyan] — FEA 仿真求解",
        border_style="cyan",
    ))
    console.print()

    # ---- 交互式获取输入文件 ----
    if inp_file is None:
        raw = typer.prompt("  请输入 .inp 文件路径")
        inp_file = Path(raw.strip())

    # ---- 校验文件存在 ----
    if not inp_file.exists():
        err_console.print(f"\n  文件不存在: {inp_file}\n")
        raise typer.Exit(1)

    # ---- 交互式获取输出目录 ----
    if output is None:
        default_out = settings.default_output_dir / inp_file.stem
        raw_out = typer.prompt(
            f"  输出目录",
            default=str(default_out),
        )
        output = Path(raw_out.strip())

    # ---- 交互式选择求解器 ----
    if solver is None:
        solver = settings.default_solver

    console.print()

    # ---- 实例化求解器 ----
    try:
        solver_instance = get_solver(solver)
    except ValueError as exc:
        err_console.print(f"\n  {exc}\n")
        raise typer.Exit(1)

    # ---- 检查/设置求解器路径 ----
    binary = solver_instance._find_binary() if hasattr(solver_instance, '_find_binary') else None

    if binary is None:
        # 询问用户求解器路径
        console.print("  [yellow]未找到求解器，请指定 CalculiX 路径[/yellow]")
        console.print()

        # 尝试查找可能的路径
        possible_paths = [
            str(Path.home() / ".cae-cli" / "solvers" / "calculix" / "bin" / "ccx.exe"),
            str(Path.home() / ".cae-cli" / "solvers" / "calculix" / "bin"),
            "C:\\CalculiX\\bin\\ccx.exe",
        ]

        default_path = possible_paths[0]
        for p in possible_paths:
            if Path(p).exists() or Path(p).parent.exists():
                default_path = p
                break

        raw_path = typer.prompt(
            "  求解器路径 (ccx.exe)",
            default=default_path,
            show_default=True,
        )
        solver_path = Path(raw_path.strip())

        # 如果用户输入的是目录，取其中的 ccx.exe
        if solver_path.is_dir():
            for ccx_name in ["ccx.exe", "ccx"]:
                ccx_in_dir = solver_path / ccx_name
                if ccx_in_dir.is_file():
                    solver_path = ccx_in_dir
                    break

        # 保存路径到配置
        settings.solver_path = str(solver_path.resolve())

        # 清除求解器缓存
        if hasattr(solver_instance, '_find_binary'):
            # 清除 _find_binary 的缓存
            solver_instance._find_binary.cache_clear()

        # 重新查找
        binary = solver_instance._find_binary()

    # ---- 检查安装状态 ----
    if binary is None or not solver_instance.check_installation():
        console.print(
            f"  [bold red]未找到有效的求解器[/bold red]\n"
            "  请检查路径是否正确。\n"
        )
        raise typer.Exit(1)

    version = solver_instance.get_version()
    console.print(f"  使用求解器: [green]{solver}[/green]"
                  + (f"  [dim]({version})[/dim]" if version else ""))
    console.print(f"  求解器路径: [cyan]{binary}[/cyan]")
    console.print(f"  输入文件:   [cyan]{inp_file}[/cyan]")
    console.print(f"  输出目录:   [cyan]{output}[/cyan]")
    console.print()

    # ---- 执行求解（带进度条）----
    result = None
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("  [bold yellow]求解中...[/bold yellow]", total=None)
        result = solver_instance.solve(
            inp_file.resolve(),
            output.resolve(),
            timeout=timeout,
        )
        progress.update(task, completed=True)

    # ---- 显示结果 ----
    console.print()
    _print_solve_result(result, inp_file)


def _print_solve_result(result, inp_file: Path) -> None:
    """渲染求解结果摘要。"""
    from cae.solvers.base import SolveResult

    if result.success:
        console.print(Panel(
            f"[bold green]求解完成！[/bold green]  耗时 {result.duration_str}",
            border_style="green",
            expand=False,
        ))
        console.print()

        # 输出文件表格
        table = Table(
            "文件", "大小", box=box.SIMPLE, show_header=True,
            header_style="bold dim",
        )
        for f in result.output_files:
            size = _fmt_size(f.stat().st_size) if f.exists() else "-"
            table.add_row(str(f.name), size)

        console.print("  [bold]输出文件:[/bold]")
        console.print(table)

        if result.frd_file:
            console.print(
                f"  查看结果: [bold]`cae view {result.output_dir}`[/bold]"
            )
        if result.warnings:
            console.print(
                f"\n  [yellow]警告: {len(result.warnings)} 条[/yellow]"
                " — 运行 [bold]`cae diagnose`[/bold] 查看详情"
            )
        console.print(
            "\n  输入 [bold]`cae explain`[/bold] 让 AI 解读结果\n"
        )

    else:
        console.print(Panel(
            f"[bold red]求解失败[/bold red]  耗时 {result.duration_str}",
            border_style="red",
            expand=False,
        ))
        console.print()
        if result.error_message:
            console.print("  [bold]错误信息:[/bold]")
            for line in result.error_message.strip().splitlines():
                console.print(f"  [red]{line}[/red]")
        console.print(
            "\n  运行 [bold]`cae diagnose`[/bold] 让 AI 诊断问题\n"
        )
        raise typer.Exit(1)


# ------------------------------------------------------------------ #
# cae solvers
# ------------------------------------------------------------------ #

@app.command(name="solvers")
def list_solvers_cmd() -> None:
    """列出所有已注册求解器及其安装状态。"""
    console.print()
    table = Table(
        "名称", "状态", "版本", "支持格式", "描述",
        box=box.ROUNDED,
        header_style="bold cyan",
    )

    for info in list_solvers():
        status = "[green]已安装[/green]" if info["installed"] else "[red]未安装[/red]"
        version = info["version"] or "-"
        fmts = ", ".join(info["formats"])
        table.add_row(
            f"[bold]{info['name']}[/bold]",
            status,
            version,
            fmts,
            info["description"],
        )

    console.print(table)
    console.print()


# ------------------------------------------------------------------ #
# cae test
# ------------------------------------------------------------------ #

@app.command(name="test")
def test_official(
    test_dir: Optional[Path] = typer.Option(
        None, "--test-dir",
        help="测试文件目录（默认: ccx_2.23.test/CalculiX/ccx_2.23/test）",
    ),
    sample: int = typer.Option(
        10, "--sample",
        help="Phase 2/3 采样测试的文件数量",
    ),
    quiet: bool = typer.Option(False, "--quiet", help="静默模式"),
) -> None:
    """
    [bold]运行 CalculiX 官方测试集批量测试[/bold]

    使用 ccx_2.23.test 测试集验证 INP 解析、求解和格式转换功能。

    示例：
      cae test
      cae test --sample 20
      cae test --test-dir /path/to/test/files
    """
    from cae.test.official import run_official_tests

    try:
        result = run_official_tests(
            test_dir=test_dir,
            sample_size=sample,
            verbose=not quiet,
        )
        console.print()
        console.print(Panel.fit(
            f"[bold]测试完成[/bold]\n"
            f"Phase 1 (inp info): {result.phase1.ok}/{result.phase1.total} OK\n"
            f"Phase 2 (solve):    {result.phase2.ok}/{result.phase2.total} OK\n"
            f"Phase 3 (convert):  {result.phase3.ok}/{result.phase3.total} OK",
            border_style="green" if result.total_pass else "yellow",
        ))

        if not result.total_pass:
            raise typer.Exit(code=1)
    except FileNotFoundError as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(code=2)
    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(code=2)


# ------------------------------------------------------------------ #
# cae info
# ------------------------------------------------------------------ #

@app.command()
def info() -> None:
    """显示 cae-cli 配置路径与版本信息。"""
    console.print()
    console.print(Panel.fit("[bold cyan]cae-cli 配置信息[/bold cyan]", border_style="cyan"))
    console.print()

    rows = [
        ("配置目录", str(settings.config_dir)),
        ("数据目录", str(settings.data_dir)),
        ("求解器目录", str(settings.solvers_dir)),
        ("模型目录", str(settings.models_dir)),
        ("默认求解器", settings.default_solver),
        ("当前 AI 模型", settings.active_model or "（未设置）"),
    ]

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column(style="bold dim", no_wrap=True)
    table.add_column()
    for k, v in rows:
        table.add_row(k, v)

    console.print(table)
    console.print()


# ------------------------------------------------------------------ #
# 占位命令（后续周次实现）
# ------------------------------------------------------------------ #

@app.command()
def run(
    model_file: Optional[Path] = typer.Argument(
        None,
        help="模型文件路径（.step/.brep/.iges → 自动划网格；.inp → 直接求解）",
        show_default=False,
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="结果输出目录（默认 results/<name>/）",
    ),
    quality: str = typer.Option(
        "medium", "--quality", "-q",
        help="网格精度 [coarse/medium/fine]",
    ),
    solver_name: str = typer.Option(
        None, "--solver", "-s",
        help="求解器名称",
    ),
    timeout: int = typer.Option(3600, "--timeout", help="求解超时秒数"),
    no_view: bool = typer.Option(False, "--no-view", help="完成后不启动可视化"),
) -> None:
    """
    [bold]全流程一键运行[/bold] — 网格 → 求解 → 可视化

    \b
    .step / .brep / .iges 文件：自动划网格 + 求解 + 查看结果
    .inp 文件：跳过划网格，直接求解 + 查看结果

    示例：
      cae run bracket.step
      cae run bracket.inp --quality fine
      cae run               （纯交互模式）
    """
    from cae.mesh.gmsh_runner import (
        MeshQuality, mesh_geometry, check_gmsh, SUPPORTED_GEO_FORMATS,
    )
    from cae.solvers.registry import get_solver
    from cae.viewer.vtk_export import frd_to_vtu

    console.print()
    console.print(Panel.fit(
        "[bold cyan]cae run[/bold cyan] — 全流程仿真",
        border_style="cyan",
    ))
    console.print()

    # ---- 获取输入文件 ----
    if model_file is None:
        raw = typer.prompt("  请输入模型文件路径")
        model_file = Path(raw.strip())

    if not model_file.exists():
        err_console.print(f"\n  文件不存在: {model_file}\n")
        raise typer.Exit(1)

    # ---- 判断是否需要划网格 ----
    ext = model_file.suffix.lower()
    needs_mesh = ext in SUPPORTED_GEO_FORMATS and ext != ".inp"
    is_inp = ext == ".inp"

    if not needs_mesh and not is_inp:
        err_console.print(
            f"\n  不支持的格式 '{ext}'\n"
            f"  几何格式: {', '.join(SUPPORTED_GEO_FORMATS.keys())}\n"
            f"  网格格式: .inp\n"
        )
        raise typer.Exit(1)

    # ---- 输出目录 ----
    if output is None:
        default_out = settings.default_output_dir / model_file.stem
        raw_out = typer.prompt("  输出目录", default=str(default_out))
        output = Path(raw_out.strip()).resolve()

    output.mkdir(parents=True, exist_ok=True)

    # ---- 求解器 ----
    solver_name = solver_name or settings.default_solver
    try:
        solver_instance = get_solver(solver_name)
    except ValueError as exc:
        err_console.print(f"\n  {exc}\n")
        raise typer.Exit(1)

    if not solver_instance.check_installation():
        err_console.print(
            f"\n  求解器 '{solver_name}' 未安装\n"
            "  请运行: [bold]cae install[/bold]\n"
        )
        raise typer.Exit(1)

    total_steps = 3 if needs_mesh else 2
    step_n = 0

    def step(label: str) -> None:
        nonlocal step_n
        step_n += 1
        console.print(f"  [{step_n}/{total_steps}] {label}")

    inp_file: Optional[Path] = None

    # ================================================================
    # 阶段 1：划网格（仅几何文件）
    # ================================================================
    if needs_mesh:
        if not check_gmsh():
            err_console.print(
                "\n  未找到 gmsh，无法自动划网格\n"
                "  请运行: [bold]pip install gmsh[/bold]\n"
                "  或者先在 CAD 软件中导出 .inp 文件，再用 cae solve\n"
            )
            raise typer.Exit(1)

        try:
            q = MeshQuality(quality.strip().lower())
        except ValueError:
            q = MeshQuality.MEDIUM

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"  [{1}/{total_steps}] 划分网格...",
                total=None,
            )
            mesh_result = mesh_geometry(
                model_file.resolve(),
                output,
                quality=q,
                output_format=".inp",
            )
            progress.update(task, completed=True)

        if not mesh_result.success:
            console.print(f"  网格划分失败: {mesh_result.error}\n")
            raise typer.Exit(1)

        console.print(
            f"  网格完成  "
            f"节点: {mesh_result.node_count}  "
            f"单元: {mesh_result.element_count}  "
            f"耗时: {mesh_result.duration_str}"
        )
        inp_file = mesh_result.inp_file
        step_n = 1

    else:
        inp_file = model_file.resolve()

    # ================================================================
    # 阶段 2：求解
    # ================================================================
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"  [{step_n+1}/{total_steps}] 求解中...",
            total=None,
        )
        solve_result = solver_instance.solve(inp_file, output, timeout=timeout)
        progress.update(task, completed=True)

    if not solve_result.success:
        console.print(f"  求解失败: {solve_result.error_message}\n")
        raise typer.Exit(1)

    console.print(
        f"  求解完成  耗时: {solve_result.duration_str}"
    )
    step_n += 1

    # ================================================================
    # 阶段 3：生成可视化
    # ================================================================
    vtu_file: Optional[Path] = None
    if solve_result.frd_file:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"  [{step_n+1}/{total_steps}] 生成可视化...",
                total=None,
            )
            vtk_result = frd_to_vtu(solve_result.frd_file, output)
            progress.update(task, completed=True)

        if vtk_result.success:
            console.print(f"  可视化文件生成完成")
            vtu_file = vtk_result.vtu_file
        else:
            console.print(f"  VTK 转换失败: {vtk_result.error}")

    # ================================================================
    # 完成摘要
    # ================================================================
    console.print()
    console.print(Panel(
        f"[bold green]全流程完成！[/bold green]",
        border_style="green",
        expand=False,
    ))
    console.print()

    if vtu_file and not no_view:
        console.print(f"  查看结果: [bold]`cae view {output}`[/bold]")
    if solve_result.warnings:
        console.print(f"  警告: {len(solve_result.warnings)} 条 — 运行 `cae diagnose` 查看")
    console.print(f"\n  输入 [bold]`cae explain {output}`[/bold] 让 AI 解读结果\n")

    # 自动启动浏览器
    if not no_view and vtu_file:
        _launch_viewer = typer.confirm("  现在打开结果查看器？", default=True)
        if _launch_viewer:
            from cae.viewer.server import start_server
            try:
                server, url, files = start_server(output, open_browser=True, auto_convert=False)
                console.print(f"\n  可视化: [bold cyan]{url}[/bold cyan]  (Ctrl+C 退出)\n")
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    server.shutdown()
                    console.print("\n  服务已停止\n")
            except Exception as exc:
                console.print(f"  无法启动查看器: {exc}\n")


@mesh_app.command(name="gen")
def mesh_gen(
    geo_file: Optional[Path] = typer.Argument(
        None,
        help="几何文件路径（.step / .brep / .iges / .geo）",
        show_default=False,
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="网格输出目录（默认 results/<name>/）",
    ),
    quality: str = typer.Option(
        "medium", "--quality", "-q",
        help="网格精度 [coarse/medium/fine]",
    ),
    fmt: str = typer.Option(
        "inp", "--format", "-f",
        help="输出格式 [inp/msh/vtu]",
    ),
    order: int = typer.Option(
        1, "--order",
        help="单元阶次（1=线性, 2=二次）",
    ),
    no_optimize: bool = typer.Option(
        False, "--no-optimize",
        help="跳过网格质量优化",
    ),
) -> None:
    """
    [bold]交互式网格划分[/bold]（Gmsh）

    \b
    示例：
      cae mesh gen bracket.step
      cae mesh gen bracket.step --quality fine --format inp
      cae mesh gen             （纯交互模式）
    """
    from cae.mesh.gmsh_runner import (
        MeshQuality, mesh_geometry, check_gmsh, get_gmsh_version,
        SUPPORTED_GEO_FORMATS,
    )

    console.print()
    console.print(Panel.fit(
        "[bold cyan]cae mesh gen[/bold cyan] — 网格划分（Gmsh）",
        border_style="cyan",
    ))
    console.print()

    # ---- 检查 Gmsh ----
    if not check_gmsh():
        err_console.print(
            "\n  未找到 gmsh\n"
            "  请运行: [bold]pip install gmsh[/bold]\n"
        )
        raise typer.Exit(1)

    gmsh_ver = get_gmsh_version()
    console.print(f"  Gmsh 版本: [green]{gmsh_ver}[/green]")
    console.print()

    # ---- 交互式获取几何文件 ----
    if geo_file is None:
        fmts = " / ".join(SUPPORTED_GEO_FORMATS.keys())
        raw = typer.prompt(f"  请输入几何文件路径 ({fmts})")
        geo_file = Path(raw.strip())

    if not geo_file.exists():
        err_console.print(f"\n  文件不存在: {geo_file}\n")
        raise typer.Exit(1)

    # ---- 交互式精度选择 ----
    quality_raw = typer.prompt(
        "  网格精度 [coarse/medium/fine]",
        default=quality,
    )
    try:
        q = MeshQuality(quality_raw.strip().lower())
    except ValueError:
        err_console.print(f"\n  无效精度 '{quality_raw}'，可选: coarse / medium / fine\n")
        raise typer.Exit(1)

    # ---- 输出目录 ----
    if output is None:
        default_out = settings.default_output_dir / geo_file.stem
        raw_out = typer.prompt("  输出目录", default=str(default_out))
        output = Path(raw_out.strip())

    out_ext = f".{fmt.lstrip('.')}"

    console.print()
    console.print(f"  输入几何: [cyan]{geo_file}[/cyan]")
    console.print(f"  精度:     [cyan]{q.label_cn}[/cyan] (lc_factor={q.lc_factor})")
    console.print(f"  输出格式: [cyan]{out_ext}[/cyan]")
    console.print(f"  输出目录: [cyan]{output}[/cyan]")
    console.print()

    # ---- 执行划分 ----
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("  划分网格中...", total=None)
        result = mesh_geometry(
            geo_file.resolve(),
            output.resolve(),
            quality=q,
            output_format=out_ext,
            element_order=order,
            optimize=not no_optimize,
        )
        progress.update(task, completed=True)

    console.print()
    if result.success:
        console.print(Panel(
            f"[bold green]网格划分完成！[/bold green]  耗时 {result.duration_str}",
            border_style="green",
            expand=False,
        ))
        console.print()
        console.print(f"  节点数:   [bold]{result.node_count}[/bold]")
        console.print(f"  单元数:   [bold]{result.element_count}[/bold]")
        console.print(f"  输出文件: [cyan]{result.mesh_file}[/cyan]")

        if result.mesh_file and result.mesh_file.suffix == ".msh":
            console.print(
                f"\n  转换为 CalculiX 格式: "
                f"[bold]`cae convert {result.mesh_file} --to inp`[/bold]"
            )
        elif result.inp_file:
            console.print(
                f"\n  下一步求解: [bold]`cae solve {result.inp_file}`[/bold]"
            )
        console.print()
    else:
        console.print(Panel(
            f"[bold red]网格划分失败[/bold red]",
            border_style="red",
            expand=False,
        ))
        if result.error:
            console.print(f"\n  {result.error}\n")
        raise typer.Exit(1)


@app.command()
def view(
    results_dir: Optional[Path] = typer.Argument(
        None,
        help="包含 .vtu / .frd 文件的结果目录",
        show_default=False,
    ),
    port: int = typer.Option(8888, "--port", "-p", help="HTTP 服务端口"),
    no_browser: bool = typer.Option(False, "--no-browser", help="不自动打开浏览器"),
    no_convert: bool = typer.Option(False, "--no-convert", help="跳过 .frd → .vtu 自动转换"),
    report: bool = typer.Option(True, "--report/--no-report", help="自动生成 HTML 报告（含云图）"),
) -> None:
    """
    [bold]在浏览器中查看仿真结果[/bold]（ParaView Glance）

    \b
    示例：
      cae view results/bracket
      cae view results/ --port 9000
      cae view          （交互模式，提示输入路径）
    """
    from cae.viewer.server import start_server
    from cae.viewer.vtk_export import frd_to_vtu

    console.print()
    console.print(Panel.fit(
        "[bold cyan]cae view[/bold cyan] — 仿真结果可视化",
        border_style="cyan",
    ))
    console.print()

    # ---- 交互式获取目录 ----
    if results_dir is None:
        raw = typer.prompt("  请输入结果目录路径")
        results_dir = Path(raw.strip())

    if not results_dir.exists():
        err_console.print(f"\n  目录不存在: {results_dir}\n")
        raise typer.Exit(1)

    # ---- 检查 / 转换文件 ----
    vtu_files = list(results_dir.glob("*.vtu")) + list(results_dir.glob("*.vtk"))
    frd_files = list(results_dir.glob("*.frd"))

    if not vtu_files and not frd_files:
        err_console.print(
            f"\n  目录中没有 .vtu / .vtk / .frd 文件\n"
            f"  目录: {results_dir}\n"
            "  提示：先运行 [bold]`cae solve`[/bold] 生成结果\n"
        )
        raise typer.Exit(1)

    if not no_convert and frd_files and not vtu_files:
        console.print(f"  发现 [cyan]{len(frd_files)}[/cyan] 个 .frd 文件，正在转换为 VTK...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            for frd in frd_files:
                task = progress.add_task(f"  转换 {frd.name}", total=None)
                result = frd_to_vtu(frd, results_dir)
                if result.success:
                    progress.update(task, description=f"  {frd.name}", completed=True)
                    console.print(
                        f"    节点: {result.node_count}  "
                        f"单元: {result.element_count}  "
                        f"字段: {', '.join(result.fields) or '-'}"
                    )
                else:
                    progress.update(task, description=f"  {frd.name}", completed=True)
                    err_console.print(f"    转换失败: {result.error}")
        console.print()
        vtu_files = list(results_dir.glob("*.vtu"))

    # ---- 生成 HTML 报告 ----
    if report and vtu_files:
        from cae.viewer import pyvista_renderer, html_generator, ReportConfig, ReportSection

        console.print("  正在生成 HTML 报告...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            for vtu_file in vtu_files:
                task = progress.add_task(f"  处理 {vtu_file.name}", total=None)
                output_dir = vtu_file.parent
                job_name = vtu_file.stem

                try:
                    # 加载网格信息
                    mesh = pyvista_renderer.load_result(vtu_file)
                    info = pyvista_renderer.get_mesh_info(mesh)

                    # 渲染图像
                    renders: dict[str, pyvista_renderer.RenderResult] = {}
                    renders["displacement"] = pyvista_renderer.render_displacement(
                        vtu_file, output_dir / f"{job_name}_disp.png", scale_factor=50.0
                    )
                    renders["von_mises"] = pyvista_renderer.render_von_mises(
                        vtu_file, output_dir / f"{job_name}_vm.png"
                    )
                    renders["slice_x"] = pyvista_renderer.render_slice(
                        vtu_file, output_dir / f"{job_name}_slice_x.png", normal="x"
                    )
                    renders["slice_y"] = pyvista_renderer.render_slice(
                        vtu_file, output_dir / f"{job_name}_slice_y.png", normal="y"
                    )
                    renders["slice_z"] = pyvista_renderer.render_slice(
                        vtu_file, output_dir / f"{job_name}_slice_z.png", normal="z"
                    )

                    # 构建报告
                    sections: list[ReportSection] = []
                    _SECTION_LABELS = {
                        "displacement": ("变形云图", "位移场 U（放大50倍）"),
                        "von_mises": ("Von Mises 应力", "等效应力 (MPa)"),
                        "slice_x": ("截面切片 — X", "沿 X 轴中点截面"),
                        "slice_y": ("截面切片 — Y", "沿 Y 轴中点截面"),
                        "slice_z": ("截面切片 — Z", "沿 Z 轴中点截面"),
                    }
                    for key, res in renders.items():
                        label, caption = _SECTION_LABELS.get(key, (key, ""))
                        if res.success and res.first():
                            sections.append(ReportSection(
                                title=label,
                                image_path=res.first(),
                                caption=caption,
                            ))

                    config = ReportConfig(
                        title=f"{job_name} 仿真报告",
                        job_name=job_name,
                        node_count=info.n_points,
                        element_count=info.n_cells,
                        sections=sections,
                    )

                    report_path = output_dir / f"{job_name}_report.html"
                    html_generator.generate_report(config, report_path)

                    progress.update(task, description=f"  {vtu_file.name}", completed=True)
                    console.print(f"    报告: {report_path.name} ({report_path.stat().st_size // 1024} KB)")
                except Exception as exc:
                    progress.update(task, description=f"  {vtu_file.name}", completed=True)
                    err_console.print(f"    报告生成失败: {exc}")
        console.print()

    # ---- 启动服务器 ----
    try:
        server, url, files = start_server(
            results_dir,
            port=port,
            auto_convert=not no_convert,
            open_browser=not no_browser,
        )
    except FileNotFoundError as exc:
        err_console.print(f"\n  {exc}\n")
        raise typer.Exit(1)
    except RuntimeError as exc:
        err_console.print(f"\n  {exc}\n")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold green]可视化服务已启动[/bold green]\n\n"
        f"  URL : [bold cyan]{url}[/bold cyan]\n"
        f"  文件: {', '.join(f.name for f in files)}\n\n"
        f"  按 Ctrl+C 停止服务",
        border_style="green",
        expand=False,
    ))
    console.print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()
    console.print("\n  服务已停止\n")


@app.command()
def convert(
    frd_file: Optional[Path] = typer.Argument(
        None,
        help=".frd 结果文件路径",
        show_default=False,
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="输出目录（默认与 .frd 同目录）",
    ),
) -> None:
    """
    [bold]手动将 .frd 结果转换为 .vtu[/bold]（供 ParaView / `cae view` 使用）

    \b
    示例：
      cae convert results/bracket.frd
      cae convert results/bracket.frd --output ./vtk_out
    """
    from cae.viewer.vtk_export import frd_to_vtu

    console.print()

    if frd_file is None:
        raw = typer.prompt("  请输入 .frd 文件路径")
        frd_file = Path(raw.strip())

    if not frd_file.exists():
        err_console.print(f"\n  文件不存在: {frd_file}\n")
        raise typer.Exit(1)

    out_dir = output or frd_file.parent
    console.print(f"  转换: [cyan]{frd_file.name}[/cyan] -> [cyan]{out_dir}[/cyan]")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("  转换中...", total=None)
        result = frd_to_vtu(frd_file, out_dir)
        progress.update(task, completed=True)

    console.print()
    if result.success:
        console.print(f"  转换完成：{result.vtu_file}")
        console.print(f"     节点: {result.node_count}  单元: {result.element_count}")
        if result.fields:
            console.print(f"     字段: {', '.join(result.fields)}")
        console.print(f"\n  查看: [bold]`cae view {out_dir}`[/bold]\n")
    else:
        err_console.print(f"\n  转换失败: {result.error}\n")
        raise typer.Exit(1)


@app.command()
def install(
    solver_only: bool = typer.Option(False, "--solver-only", help="只安装 CalculiX"),
    model_only:  bool = typer.Option(False, "--model-only",  help="只安装默认 AI 模型"),
    model_name:  str  = typer.Option("deepseek-r1-7b", "--model", help="指定模型名称"),
) -> None:
    """
    [bold]下载并安装 CalculiX 求解器 + AI 模型[/bold]

    \b
    示例：
      cae install                        # 全部安装
      cae install --solver-only          # 只装求解器
      cae install --model deepseek-r1-14b
    """
    from cae.installer.solver_installer import SolverInstaller
    from cae.installer.model_installer import ModelInstaller

    console.print()
    console.print(Panel.fit("[bold cyan]cae install[/bold cyan] — 安装求解器与 AI 模型", border_style="cyan"))
    console.print()

    # ---- 安装 CalculiX ----
    solver_result = None
    solver_install_path = None
    if not model_only:
        console.print("  [bold]安装 CalculiX 求解器[/bold]")

        # 询问安装路径
        default_path = str(Path.home() / ".cae-cli" / "solvers" / "calculix" / "bin")
        raw_path = typer.prompt(
            "  安装路径",
            default=default_path,
            show_default=True,
        )
        install_path = Path(raw_path.strip())

        # 确保路径格式正确（如果是文件路径则取父目录）
        if install_path.name == "ccx.exe" or ".exe" in install_path.name:
            install_path = install_path.parent

        installer = SolverInstaller(install_dir=install_path)

        # 检查是否已安装
        if installer.is_installed():
            console.print(f"  CalculiX 已安装在: {installer.bin_dir}")
            reinstall = typer.prompt("  是否重新安装？", default="n", show_default=True)
            if reinstall.lower() != "y":
                console.print("  跳过安装\n")
            else:
                console.print()
                with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                              TimeElapsedColumn(), console=console) as progress:
                    task = progress.add_task("  正在安装...", total=None)

                    def _solver_progress(pct: float, msg: str) -> None:
                        progress.update(task, description=f"  {msg}")

                    solver_result = installer.install(progress_callback=_solver_progress, force=True)
        else:
            console.print()
            with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                          TimeElapsedColumn(), console=console) as progress:
                task = progress.add_task("  正在安装...", total=None)

                def _solver_progress(pct: float, msg: str) -> None:
                    progress.update(task, description=f"  {msg}")

                solver_result = installer.install(progress_callback=_solver_progress)

        if solver_result and solver_result.success:
            solver_install_path = solver_result.install_dir or installer.get_install_dir()
            console.print()
            console.print(f"  [green]CalculiX 安装成功[/green]")
            console.print(f"  路径: {solver_install_path}")
            console.print()
        elif solver_result:
            console.print()
            console.print(f"  [red]CalculiX 安装失败[/red]")
            console.print(f"  {solver_result.error_message}")
            console.print()
        else:
            console.print()

    # ---- 安装 AI 模型 ----
    if not solver_only and solver_result and solver_result.success:
        # 安装完求解器后询问是否安装 AI 模型
        console.print("  [bold]安装 AI 模型[/bold]")
        install_ai = typer.prompt("  是否安装 AI 模型？", default="n", show_default=True)

        if install_ai.lower() == "y":
            mi = ModelInstaller()

            if mi.is_installed(model_name):
                console.print(f"  模型已安装: {model_name}\n")
                mi.activate(model_name)
            else:
                from cae.installer.model_installer import KNOWN_MODELS
                meta = KNOWN_MODELS.get(model_name)
                if meta is None:
                    console.print(f"  [red]错误:[/red] 未知模型 '{model_name}'")
                    console.print(f"  可用模型: {', '.join(KNOWN_MODELS.keys())}\n")
                else:
                    size = meta.size_gb
                    console.print(f"  模型: [cyan]{model_name}[/cyan]  大小: ~{size} GB")
                    console.print("  这可能需要几分钟，取决于网络速度...\n")

                    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                                  TimeElapsedColumn(), console=console) as progress:
                        task = progress.add_task("  下载中...", total=None)

                        def _model_progress(pct: float, msg: str) -> None:
                            progress.update(task, description=f"  {msg}")

                        result = mi.install(model_name, progress_callback=_model_progress)

                    if result.success:
                        console.print()
                        console.print(f"  [green]AI 模型安装成功[/green]")
                    else:
                        console.print()
                        console.print(f"  [yellow]AI 模型安装失败[/yellow]")
                        console.print(f"  {result.error_message}")
                        console.print()
        else:
            console.print()

    console.print("  现在可以运行 [bold]`cae solve`[/bold] 开始仿真\n")


# ------------------------------------------------------------------ #
# cae download
# ------------------------------------------------------------------ #

@app.command(name="download")
def download_file(
    url: str = typer.Argument(..., help="下载链接（支持直链、网盘链接等）"),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="输出文件路径"),
    filename: Optional[str] = typer.Option(None, "-n", "--name", help="指定保存的文件名"),
) -> None:
    """
    [bold]下载文件（AI 模型等大文件）[/bold]

    支持从任意 URL 下载文件，自动命名，进度显示。

    \b
    示例：
      cae download "https://example.com/model.gguf"
      cae download "https://example.com/model.gguf" -o models/
      cae download "https://example.com/model.gguf" -n my_model.gguf
    """
    from cae.installer.model_installer import ModelInstaller

    mi = ModelInstaller()

    # 确定输出路径
    if output and output.is_dir():
        # 目录模式：结合 filename 生成最终路径
        name = filename or url.split("/")[-1].split("?")[0]
        dest = output / name
    elif output:
        # 指定具体文件路径
        dest = output
        if filename:
            console.print("[yellow]警告: -o 已指定文件路径，-n 参数将被忽略[/yellow]")
    else:
        # 默认保存到 models 目录
        name = filename or url.split("/")[-1].split("?")[0]
        dest = mi.models_dir / name

    # 确保目录存在
    dest.parent.mkdir(parents=True, exist_ok=True)

    console.print()
    console.print(f"  下载地址: [cyan]{url}[/cyan]")
    console.print(f"  保存位置: [cyan]{dest}[/cyan]")
    console.print()

    try:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                      TimeElapsedColumn(), console=console) as progress:
            task = progress.add_task("  连接中...", total=None)

            def _progress(pct: float, msg: str) -> None:
                progress.update(task, description=f"  {msg}", completed=pct * 100)

            result = mi.download_file(url, dest, progress_callback=_progress)

        if result.success:
            console.print()
            console.print(f"  [green]下载完成！[/green]  文件: {result.file_path}  大小: {result.file_size_mb:.1f} MB")
        else:
            console.print()
            console.print(f"  [red]下载失败: {result.error_message}[/red]")
            raise typer.Exit(code=1)
    except Exception as e:
        console.print()
        console.print(f"  [red]错误: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def explain(
    results_dir: Optional[Path] = typer.Argument(None, help="结果目录"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="流式输出"),
) -> None:
    """[bold]AI 解读仿真结果[/bold]"""
    from cae.ai.explain import explain_results
    from cae.ai.llm_client import LLMClient

    console.print()
    console.print(Panel.fit("[bold cyan]cae explain[/bold cyan] — AI 结果解读", border_style="cyan"))
    console.print()

    if results_dir is None:
        raw = typer.prompt("  请输入结果目录路径")
        results_dir = Path(raw.strip())

    client = LLMClient()
    if not client.is_running():
        console.print("  llama-server 未运行，尝试自动启动...")
        if not client.start_server():
            err_console.print(
                "\n  无法启动 AI 服务。请先运行 [bold]`cae install`[/bold] 安装模型。\n"
            )
            raise typer.Exit(1)

    console.print("  AI 正在分析，请稍候...\n")
    result = explain_results(results_dir, client, stream=stream)

    if not result.success:
        err_console.print(f"\n  {result.error}\n")
        raise typer.Exit(1)

    if not stream:
        console.print(Panel(result.summary, title="AI 解读", border_style="green"))
    console.print()


@app.command()
def suggest(
    results_dir: Optional[Path] = typer.Argument(None, help="结果目录"),
    no_ai: bool = typer.Option(False, "--no-ai", help="只做规则建议，不使用 AI"),
    stream: bool = typer.Option(True, "--stream/--no-stream", help="流式输出"),
) -> None:
    """[bold]AI 生成优化建议[/bold]"""
    from cae.ai.suggest import suggest_results
    from cae.ai.diagnose import diagnose_results
    from cae.ai.llm_client import LLMClient

    console.print()
    console.print(Panel.fit("[bold cyan]cae suggest[/bold cyan] — AI 优化建议", border_style="cyan"))
    console.print()

    if results_dir is None:
        raw = typer.prompt("  请输入结果目录路径")
        results_dir = Path(raw.strip())

    # 先做诊断
    client = None
    if not no_ai:
        client = LLMClient()
        if not client.is_running():
            console.print("  llama-server 未运行，仅生成规则建议\n")
            client = None

    # 执行诊断
    diagnose_result = diagnose_results(results_dir, client, stream=False)

    if not diagnose_result.success:
        err_console.print(f"\n  诊断失败: {diagnose_result.error}\n")
        raise typer.Exit(1)

    # 显示发现的问题
    if diagnose_result.issues:
        console.print(f"  发现 {diagnose_result.issue_count} 个问题：")
        for iss in diagnose_result.issues[:5]:
            icon = "[X]" if iss.severity == "error" else "[!]"
            console.print(f"  {icon} [{iss.category}] {iss.message[:80]}")
        console.print()

    # 生成建议
    console.print("  正在生成优化建议...\n")
    suggest_result = suggest_results(results_dir, diagnose_result, client, stream=stream)

    if not suggest_result.success:
        err_console.print(f"\n  建议生成失败: {suggest_result.error}\n")
        raise typer.Exit(1)

    # 显示建议
    if suggest_result.suggestions:
        console.print("  [bold]优化建议：[/bold]")
        for i, sug in enumerate(suggest_result.suggestions[:5], 1):
            priority_icon = "🔴" if sug.priority <= 2 else "🟡" if sug.priority <= 3 else "🟢"
            console.print(f"\n  {i}. {priority_icon} {sug.title}")
            console.print(f"     类别: {sug.category}  |  难度: {sug.implementation_difficulty}")
            console.print(f"     {sug.description}")
            console.print(f"     预期改进: {sug.expected_improvement}")
        console.print()

    console.print()


@app.command()
def diagnose(
    results_dir: Optional[Path] = typer.Argument(None, help="结果目录"),
    no_ai: bool = typer.Option(False, "--no-ai", help="只做规则检测，跳过 AI"),
    stream: bool = typer.Option(True, "--stream/--no-stream"),
) -> None:
    """[bold]AI 诊断仿真问题[/bold]"""
    from cae.ai.diagnose import diagnose_results
    from cae.ai.llm_client import LLMClient

    console.print()
    console.print(Panel.fit("[bold cyan]cae diagnose[/bold cyan] — AI 问题诊断", border_style="cyan"))
    console.print()

    if results_dir is None:
        raw = typer.prompt("  请输入结果目录路径")
        results_dir = Path(raw.strip())

    client = None
    if not no_ai:
        client = LLMClient()
        if not client.is_running():
            console.print("  llama-server 未运行，仅执行规则检测\n")
            client = None

    result = diagnose_results(results_dir, client, stream=stream)

    if not result.success:
        err_console.print(f"\n  {result.error}\n")
        raise typer.Exit(1)

    # 显示规则检测结果
    if result.issues:
        console.print(f"  规则检测：发现 {result.issue_count} 个问题")
        for iss in result.issues[:10]:
            icon = "X" if iss.severity == "error" else "!"
            console.print(f"  [{icon}] [{iss.category}] {iss.message[:80]}")
            if iss.suggestion:
                console.print(f"     -> {iss.suggestion}")
        console.print()
    else:
        console.print("  规则检测未发现明显问题\n")

    if result.ai_diagnosis and not stream:
        console.print(Panel(result.ai_diagnosis, title="AI 诊断", border_style="yellow"))

    console.print()


@app.command(name="report")
def generate_report(
    results_dir: Optional[Path] = typer.Argument(
        None,
        help="结果目录（含 .frd 文件）",
    ),
    output: Optional[Path] = typer.Option(
        None, "-o", "--output", help="输出 PDF 路径（默认 results/report_YYYYMMDD_HHMMSS.pdf）",
    ),
    inp_file: Optional[Path] = typer.Option(
        None, "-i", "--inp", help="INP 文件路径（读取材料属性）",
    ),
    yield_strength: Optional[float] = typer.Option(
        None, "-y", "--yield", help="手动指定屈服强度（MPa），覆盖 INP 值",
    ),
    job_name: Optional[str] = typer.Option(
        None, "-j", "--job", help="工况名称",
    ),
    scale: float = typer.Option(
        50.0, "-s", "--scale", help="变形放大倍数（云图）",
    ),
) -> None:
    """
    [bold]生成 PDF 仿真报告[/bold]

    包含最大位移、最大应力、安全系数、云图截图，
    一键发给导师或甲方。

    \b
    示例：
      cae report results/
      cae report results/ -o report.pdf -i model.inp
      cae report results/ -y 350 -j cantilever_beam
    """
    from cae.viewer.pdf_report import generate_pdf_report

    console.print()
    console.print(
        Panel.fit("[bold cyan]cae report[/bold cyan] — 生成 PDF 仿真报告", border_style="cyan"),
    )
    console.print()

    if results_dir is None:
        raw = typer.prompt("  请输入结果目录路径")
        results_dir = Path(raw.strip())

    results_dir = Path(results_dir)
    if not results_dir.exists():
        err_console.print(f"\n  结果目录不存在: {results_dir}\n")
        raise typer.Exit(1)

    frd_files = list(results_dir.glob("*.frd"))
    if not frd_files:
        err_console.print(f"\n  结果目录中未找到 .frd 文件: {results_dir}\n")
        raise typer.Exit(1)

    # 默认输出路径
    if output is None:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = results_dir / f"report_{timestamp}.pdf"

    console.print(f"  结果目录: [cyan]{results_dir}[/cyan]")
    console.print(f"  INP 文件: [cyan]{inp_file or '（未指定，使用默认材料）'}[/cyan]")
    console.print(f"  屈服强度: [cyan]{yield_strength or '（默认 250 MPa）'}[/cyan]")
    console.print(f"  输出路径: [cyan]{output}[/cyan]")
    console.print()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("  解析结果文件...", total=None)

            result_path = generate_pdf_report(
                results_dir=results_dir,
                output_path=output,
                inp_file=inp_file,
                job_name=job_name or "",
                yield_strength=yield_strength,
                scale_factor=scale,
            )

            progress.update(task, description="  生成报告中...", completed=50)

        import os
        size_mb = os.path.getsize(result_path) / (1024 * 1024)
        console.print()
        console.print(f"  [green]✓ PDF 报告已生成！[/green]  {result_path}  ({size_mb:.1f} MB)")
        console.print()

    except RuntimeError as exc:
        if "weasyprint" in str(exc):
            err_console.print(
                "\n  PDF 生成需要 weasyprint 依赖。\n"
                "  请运行以下命令安装：\n\n"
                "    [bold]pip install cae-cli[report][/bold]\n"
                "  或\n"
                "    [bold]pip install weasyprint>=60.0[/bold]\n",
            )
        else:
            err_console.print(f"\n  [red]错误: {exc}[/red]\n")
        raise typer.Exit(1)
    except Exception as exc:
        err_console.print(f"\n  [red]报告生成失败: {exc}[/red]\n")
        raise typer.Exit(1)


# ------------------------------------------------------------------ #
# 工具函数
# ------------------------------------------------------------------ #

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ------------------------------------------------------------------ #
# 入口
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    app()
