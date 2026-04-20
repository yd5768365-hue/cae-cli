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

import json
import os
import sys
# 确保子进程使用 UTF-8 编码（避免 Windows GBK 编码问题）
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
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
    console.print("  [green][OK][/green] 解析成功")
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
        console.print("  已在浏览器中打开\n")


# ------------------------------------------------------------------ #
# inp 命令组
# ------------------------------------------------------------------ #

inp_app = typer.Typer(help="[bold]INP 文件解析与修改[/bold] — 解析、检查、修改 Abaqus/CalculiX .inp 文件")


@inp_app.command(name="info")
def inp_info(
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
        from cae.ai.llm_client import LLMConfig
        config = LLMConfig(use_ollama=True, model_name="deepseek-r1:1.5b")
        client = LLMClient(config=config)
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
            console.print("  可用模板: cantilever_beam, flat_plate")
            console.print("  使用 --list 查看所有模板")
            return

        # 写入文件
        out_path = output or Path(f"{name}.inp")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

        console.print(f"  [green]生成成功: {out_path}[/green]")
        console.print("  使用 --params 查看所有参数")

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
# cae model - Ollama 本地模型管理
# ------------------------------------------------------------------ #

model_app = typer.Typer(
    name="model",
    help="[bold]Ollama 本地模型管理[/bold] — 切换、管理本地 LLM 模型",
    no_args_is_help=True,
)


@model_app.callback()
def model_callback():
    """Ollama 本地模型管理命令组"""
    pass


def _run_ollama(args: list[str]) -> tuple[int, str, str]:
    """运行 ollama 命令并返回 (返回码, stdout, stderr)"""
    import subprocess
    try:
        result = subprocess.run(
            ["ollama"] + args,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", "ollama 命令未找到，请先安装 Ollama: https://ollama.com"


@model_app.command(name="list")
def model_list() -> None:
    """
    [bold]列出本地模型[/bold]

    显示所有已下载的 Ollama 模型
    """
    console.print()
    console.print(Panel.fit("[bold cyan]本地模型列表[/bold cyan]", border_style="cyan"))
    console.print()

    returncode, stdout, stderr = _run_ollama(["list"])

    if returncode != 0:
        console.print(f"  [red]错误:[/red] {stderr or 'ollama 未运行'}")
        console.print()
        console.print("  请确保已安装并启动 Ollama: https://ollama.com")
        return

    if stdout.strip():
        # 格式化输出
        lines = stdout.strip().split("\n")
        for i, line in enumerate(lines):
            if i == 0:
                # 表头
                console.print(f"  [bold cyan]{line}[/bold cyan]")
            else:
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0]
                    size = parts[1]
                    modified = " ".join(parts[2:])
                    console.print(f"  [green]{name:<40}[/green] [dim]{size:>10}[/dim]  [dim]{modified}[/dim]")
                else:
                    console.print(f"  {line}")
    else:
        console.print("  [yellow]暂无已下载的模型[/yellow]")

    console.print()


@model_app.command(name="pull")
def model_pull(
    model_name: str = typer.Argument(..., help="模型名称（如 deepseek-r1:1.5b, llama3:latest）"),
) -> None:
    """
    [bold]拉取模型[/bold]

    从 Ollama 仓库下载模型

    \b
    示例：
      cae model pull deepseek-r1:1.5b
      cae model pull llama3:latest
    """
    console.print()
    console.print(f"  [bold cyan]正在拉取模型:[/bold cyan] {model_name}")
    console.print("  这可能需要几分钟，取决于网络速度...")
    console.print()

    returncode, stdout, stderr = _run_ollama(["pull", model_name])

    if returncode != 0:
        console.print()
        console.print(f"  [red]拉取失败:[/red] {stderr}")
        raise typer.Exit(code=1)

    console.print()
    console.print("  [green]模型拉取成功！[/green]")


@model_app.command(name="show")
def model_show(
    model_name: str = typer.Argument(..., help="模型名称"),
) -> None:
    """
    [bold]显示模型信息[/bold]

    查看模型的详细信息（参数、尺寸等）
    """
    console.print()
    console.print(f"  [bold cyan]模型信息:[/bold cyan] {model_name}")
    console.print()

    returncode, stdout, stderr = _run_ollama(["show", model_name])

    if returncode != 0:
        console.print(f"  [red]错误:[/red] {stderr}")
        raise typer.Exit(code=1)

    # 格式化输出
    for line in stdout.strip().split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            console.print(f"  [bold]{key}:[/bold] [dim]{value.strip()}[/dim]")
        else:
            console.print(f"  {line}")

    console.print()


@model_app.command(name="delete")
def model_delete(
    model_name: str = typer.Argument(..., help="模型名称"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
) -> None:
    """
    [bold]删除模型[/bold]

    从本地删除指定的 Ollama 模型
    """
    # 确认
    if not force:
        console.print()
        confirm = console.input(f"  [bold]确认删除模型 {model_name}？[/bold] [y/N]: ")
        if confirm.lower() != "y":
            console.print("  已取消")
            return

    returncode, stdout, stderr = _run_ollama(["rm", model_name])

    if returncode != 0:
        console.print()
        console.print(f"  [red]删除失败:[/red] {stderr}")
        raise typer.Exit(code=1)

    console.print()
    console.print(f"  [green]模型已删除: {model_name}[/green]")


@model_app.command(name="set")
def model_set(
    model_name: str = typer.Argument(..., help="模型名称（如 deepseek-r1:1.5b）"),
) -> None:
    """
    [bold]设为默认模型[/bold]

    将指定模型设为 cae-cli 的默认使用模型

    \b
    示例：
      cae model set deepseek-r1:1.5b
    """
    from cae.config import settings

    # 检查模型是否存在
    returncode, stdout, stderr = _run_ollama(["list"])
    if returncode == 0:
        models = [line.split()[0] for line in stdout.strip().split("\n")[1:] if line.strip()]
        if model_name not in models:
            console.print()
            console.print(f"  [yellow]警告:[/yellow] 模型 '{model_name}' 未在本地找到")
            console.print("  请先使用 [cyan]cae model pull[/cyan] 下载")
            console.print()

    # 保存到配置
    settings.active_model = model_name
    settings.save()

    console.print()
    console.print(f"  [green]默认模型已设为:[/green] {model_name}")
    console.print()
    console.print(f"  配置路径: {settings.config_file}")


app.add_typer(model_app, name="model")

# Windows MSYS 环境：强制 stdout/stderr 使用 UTF-8
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

console = Console(legacy_windows=False, force_terminal=True)
err_console = Console(stderr=True, style="bold red", legacy_windows=False)

# ------------------------------------------------------------------ #
# cae docker - standalone Docker features
# ------------------------------------------------------------------ #

docker_app = typer.Typer(
    name="docker",
    help="[bold]Docker container tools[/bold] - check Docker and run containerized solvers",
    no_args_is_help=True,
)


@docker_app.command(name="status")
def docker_status(
    json_output: bool = typer.Option(False, "--json", help="Output Docker status as JSON."),
) -> None:
    """Check Docker availability, including Docker installed inside Windows WSL."""
    from dataclasses import asdict

    from cae.runtimes import DockerRuntime

    info = DockerRuntime().inspect()
    payload = asdict(info)
    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        console.print()
        console.print(Panel.fit("[bold cyan]cae docker status[/bold cyan]", border_style="cyan"))
        console.print()
        if info.available:
            console.print("  [green][OK][/green] Docker is available")
            console.print(f"  backend: [cyan]{info.backend}[/cyan]")
            console.print(f"  version: [cyan]{info.version}[/cyan]")
            console.print(f"  command: [cyan]{' '.join(info.command)}[/cyan]")
            console.print(f"  WSL path mode: [cyan]{info.use_wsl_paths}[/cyan]")
        else:
            console.print("  [red][X][/red] Docker is not available")
            console.print(f"  {info.error}")
        console.print()

    if not info.available:
        raise typer.Exit(1)


@docker_app.command(name="path")
def docker_path(
    path: Path = typer.Argument(..., help="Host path to convert for WSL Docker mounts."),
) -> None:
    """Convert a Windows path to the path form expected by Docker running inside WSL."""
    from cae.runtimes import DockerRuntime

    console.print(DockerRuntime.windows_path_to_wsl(path))


@docker_app.command(name="catalog")
def docker_catalog(
    solver: Optional[str] = typer.Option(None, "--solver", help="Filter by solver family."),
    capability: Optional[str] = typer.Option(None, "--capability", help="Filter by capability tag."),
    include_experimental: bool = typer.Option(
        True,
        "--experimental/--no-experimental",
        help="Include experimental image entries.",
    ),
    runnable_only: bool = typer.Option(
        False,
        "--runnable-only",
        help="Only show images that expose a direct solver command.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output image catalog as JSON."),
) -> None:
    """List built-in Docker image aliases for solver containers."""
    from cae.docker import list_image_spec_dicts

    items = list_image_spec_dicts(
        solver=solver,
        capability=capability,
        include_experimental=include_experimental,
        runnable_only=runnable_only,
    )
    if json_output:
        typer.echo(json.dumps({"images": items}, ensure_ascii=False, indent=2))
        return

    table = Table(title="Docker image catalog", box=box.SIMPLE)
    table.add_column("Alias", style="cyan")
    table.add_column("Image", style="green")
    table.add_column("Solver")
    table.add_column("Maturity")
    table.add_column("Runnable")
    table.add_column("Capabilities")
    table.add_column("Description")
    for item in items:
        table.add_row(
            item["alias"],
            item["image"],
            item["solver"],
            item["maturity"],
            "yes" if item["runnable"] else "no",
            ", ".join(item["capabilities"][:4]),
            item["description"],
        )
    console.print()
    console.print(table)
    console.print()


@docker_app.command(name="images")
def docker_images(
    json_output: bool = typer.Option(False, "--json", help="Output local images as JSON."),
) -> None:
    """List local Docker images visible to the configured Docker backend."""
    from cae.runtimes import DockerRuntime

    images = DockerRuntime().list_images()
    if json_output:
        typer.echo(json.dumps({"images": images}, ensure_ascii=False, indent=2))
        return

    console.print()
    console.print(Panel.fit("[bold cyan]cae docker images[/bold cyan]", border_style="cyan"))
    if images:
        for image in images:
            console.print(f"  - [green]{image}[/green]")
    else:
        console.print("  [yellow]No local Docker images found or Docker is unavailable.[/yellow]")
    console.print()


@docker_app.command(name="pull")
def docker_pull(
    image_ref: str = typer.Argument(
        "calculix",
        help="Image alias from `cae docker catalog` or a direct Docker image reference.",
    ),
    timeout: int = typer.Option(3600, "--timeout", help="Docker pull timeout in seconds."),
    set_default: bool = typer.Option(
        False,
        "--set-default",
        help="Save the pulled image as the default image for its solver family.",
    ),
    use_docker_config: bool = typer.Option(
        False,
        "--use-docker-config",
        help="Use the existing Docker config and credential helper instead of an isolated public-pull config.",
    ),
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Contact the remote registry even if the image already exists locally.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output pull result as JSON."),
) -> None:
    """Pull a Docker image through the configured Docker backend."""
    from cae.docker import get_image_spec, resolve_image_reference, solver_config_key
    from cae.runtimes import DockerRuntime

    image = resolve_image_reference(image_ref)
    spec = get_image_spec(image_ref)
    runtime = DockerRuntime()
    already_present = runtime.image_exists(image)
    skipped_pull = already_present and not refresh
    result = None
    if not skipped_pull:
        result = runtime.pull_image(
            image,
            timeout=timeout,
            use_default_config=use_docker_config,
        )
    image_present = skipped_pull or (result.returncode == 0 if result else False) or runtime.image_exists(image)
    payload = {
        "requested": image_ref,
        "image": image,
        "alias": spec.alias if spec else None,
        "success": image_present,
        "returncode": 0 if result is None else result.returncode,
        "image_present": image_present,
        "skipped_pull": skipped_pull,
        "stdout": "" if result is None else result.stdout,
        "stderr": "" if result is None else result.stderr,
        "command": [] if result is None else result.command,
    }
    if image_present and set_default:
        default_key = solver_config_key(spec.solver if spec else "solver")
        settings.set(default_key, image)
        payload["default_saved"] = True
        payload["default_key"] = default_key
    else:
        payload["default_saved"] = False
        payload["default_key"] = None

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        console.print()
        console.print(Panel.fit("[bold cyan]cae docker pull[/bold cyan]", border_style="cyan"))
        console.print(f"  image: [cyan]{image}[/cyan]")
        if skipped_pull:
            console.print("  [green][OK][/green] Image already exists locally")
        if result and result.stdout.strip():
            console.print(result.stdout.strip())
        if result and result.stderr.strip():
            console.print(result.stderr.strip())
        if result and result.returncode == 0:
            console.print("  [green][OK][/green] Image pulled successfully")
            if set_default:
                console.print(f"  [green][OK][/green] Saved default image: {image}")
        elif not result and set_default:
            console.print(f"  [green][OK][/green] Saved default image: {image}")
        elif result and image_present:
            console.print("  [yellow][!][/yellow] Pull failed, but the image already exists locally")
            if set_default:
                console.print(f"  [green][OK][/green] Saved default image: {image}")
        else:
            console.print(f"  [red][X][/red] Docker pull failed with code {result.returncode}")
        console.print()

    if not image_present:
        raise typer.Exit(1)


@docker_app.command(name="recommend")
def docker_recommend(
    query: str = typer.Argument(..., help="Problem description, e.g. 'steady CFD' or 'nonlinear structure'."),
    limit: int = typer.Option(5, "--limit", help="Maximum number of candidates to return."),
    json_output: bool = typer.Option(False, "--json", help="Output recommendations as JSON."),
) -> None:
    """Recommend open-source solver containers from the built-in catalog."""
    from dataclasses import asdict

    from cae.docker import recommend_image_specs

    items = [asdict(spec) for spec in recommend_image_specs(query, limit=limit)]
    if json_output:
        typer.echo(json.dumps({"query": query, "recommendations": items}, ensure_ascii=False, indent=2))
        return

    console.print()
    console.print(Panel.fit("[bold cyan]cae docker recommend[/bold cyan]", border_style="cyan"))
    console.print(f"  query: [cyan]{query}[/cyan]")
    if not items:
        console.print("  [yellow]No matching solver image found in the local catalog.[/yellow]")
        console.print()
        return

    table = Table(title="Recommended solver containers", box=box.SIMPLE)
    table.add_column("Alias", style="cyan")
    table.add_column("Solver")
    table.add_column("Maturity")
    table.add_column("Capabilities")
    table.add_column("Image", style="green")
    for item in items:
        table.add_row(
            item["alias"],
            item["solver"],
            item["maturity"],
            ", ".join(item["capabilities"][:5]),
            item["image"],
        )
    console.print(table)
    console.print()


@docker_app.command(name="build-su2-runtime")
def docker_build_su2_runtime(
    tag: str = typer.Option(
        "local/su2-runtime:8.3.0",
        "--tag",
        help="Local Docker image tag to create.",
    ),
    su2_version: str = typer.Option(
        "8.3.0",
        "--su2-version",
        help="SU2 version to install from conda-forge.",
    ),
    base_image: str = typer.Option(
        "mambaorg/micromamba:1.5.10",
        "--base-image",
        help="Micromamba base image used to build the runtime image.",
    ),
    timeout: int = typer.Option(3600, "--timeout", help="Docker build timeout in seconds."),
    pull_base: bool = typer.Option(
        True,
        "--pull-base/--no-pull-base",
        help="Ask Docker to refresh the base image during build.",
    ),
    set_default: bool = typer.Option(
        True,
        "--set-default/--no-set-default",
        help="Save the built image as docker_su2_image.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output build result as JSON."),
) -> None:
    """Build a local SU2 runtime image that exposes SU2_CFD."""
    from cae.runtimes import DockerRuntime

    dockerfile = Path(__file__).resolve().parent / "docker" / "assets" / "su2-runtime-conda.Dockerfile"
    result = DockerRuntime().build_image(
        context_dir=dockerfile.parent,
        dockerfile=dockerfile,
        tag=tag,
        build_args={
            "SU2_VERSION": su2_version,
            "MICROMAMBA_IMAGE": base_image,
        },
        timeout=timeout,
        pull=pull_base,
    )
    success = result.returncode == 0
    payload = {
        "tag": tag,
        "su2_version": su2_version,
        "base_image": base_image,
        "success": success,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": result.command,
        "default_saved": False,
    }
    if success and set_default:
        settings.set("docker_su2_image", tag)
        payload["default_saved"] = True

    if json_output:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        console.print()
        console.print(Panel.fit("[bold cyan]cae docker build-su2-runtime[/bold cyan]", border_style="cyan"))
        console.print(f"  tag:     [cyan]{tag}[/cyan]")
        console.print(f"  version: [cyan]{su2_version}[/cyan]")
        if result.stdout.strip():
            console.print(result.stdout.strip())
        if result.stderr.strip():
            console.print(result.stderr.strip())
        if success:
            console.print("  [green][OK][/green] SU2 runtime image built")
            if set_default:
                console.print(f"  [green][OK][/green] Saved docker_su2_image: {tag}")
        else:
            console.print(f"  [red][X][/red] SU2 runtime image build failed with code {result.returncode}")
        console.print()

    if not success:
        raise typer.Exit(1)


@docker_app.command(name="run")
def docker_run_solver(
    image_ref: str = typer.Argument(
        ...,
        help="Image alias from `cae docker catalog` or a direct Docker image reference.",
    ),
    input_path: Path = typer.Argument(..., help="Solver input file or case directory."),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory. Defaults to results/docker-<input_name>.",
    ),
    command: Optional[str] = typer.Option(
        None,
        "--cmd",
        help="Override catalog command, e.g. --cmd 'SU2_CFD config.cfg'.",
    ),
    timeout: int = typer.Option(3600, "--timeout", help="Container run timeout in seconds."),
    cpus: Optional[str] = typer.Option(None, "--cpus", help="Docker --cpus limit, e.g. 2."),
    memory: Optional[str] = typer.Option(None, "--memory", help="Docker --memory limit, e.g. 4g."),
    network: str = typer.Option("none", "--network", help="Docker network mode for the container."),
) -> None:
    """Run any cataloged solver container with a generic file or case-directory workflow."""
    from cae.docker import DockerSolverRunner, resolve_image_reference

    if not input_path.exists():
        err_console.print(f"\n  input path not found: {input_path}\n")
        raise typer.Exit(1)

    output_dir = output or Path("results") / f"docker-{input_path.stem if input_path.is_file() else input_path.name}"
    resolved_image = resolve_image_reference(image_ref)

    console.print()
    console.print(Panel.fit("[bold cyan]cae docker run[/bold cyan]", border_style="cyan"))
    console.print(f"  input:   [cyan]{input_path}[/cyan]")
    console.print(f"  output:  [cyan]{output_dir}[/cyan]")
    console.print(f"  image:   [cyan]{resolved_image}[/cyan]")
    if command:
        console.print(f"  command: [cyan]{command}[/cyan]")
    console.print()

    result = DockerSolverRunner().run(
        image_ref,
        input_path.resolve(),
        output_dir.resolve(),
        command=command,
        timeout=timeout,
        cpus=cpus,
        memory=memory,
        network=network,
    )

    if result.success:
        console.print(f"  [green][OK][/green] Solver finished in {result.duration_seconds:.1f}s")
    else:
        console.print(f"  [red][X][/red] Solver failed with code {result.returncode}")
        if result.error_message:
            console.print(result.error_message)
    console.print(f"  solver:  [cyan]{result.solver}[/cyan]")
    console.print(f"  command: [cyan]{' '.join(result.command)}[/cyan]")
    console.print(f"  output:  [cyan]{result.output_dir}[/cyan]")
    console.print()

    if not result.success:
        raise typer.Exit(1)


@docker_app.command(name="calculix")
def docker_calculix(
    inp_file: Path = typer.Argument(..., help=".inp input file to solve in a Docker container."),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory. Defaults to results/<job_name>.",
    ),
    image: Optional[str] = typer.Option(
        None,
        "--image",
        help="CalculiX Docker image. Also supports CAE_CALCULIX_DOCKER_IMAGE.",
    ),
    timeout: int = typer.Option(3600, "--timeout", help="Container run timeout in seconds."),
    cpus: Optional[str] = typer.Option(None, "--cpus", help="Docker --cpus limit, e.g. 2."),
    memory: Optional[str] = typer.Option(None, "--memory", help="Docker --memory limit, e.g. 4g."),
) -> None:
    """Run CalculiX through the standalone Docker feature."""
    from cae.docker import CalculixDockerRunner, resolve_image_reference

    if not inp_file.exists():
        err_console.print(f"\n  file not found: {inp_file}\n")
        raise typer.Exit(1)

    resolved_image = resolve_image_reference(image) if image else None
    output_dir = output or Path("results") / inp_file.stem
    console.print()
    console.print(Panel.fit("[bold cyan]cae docker calculix[/bold cyan]", border_style="cyan"))
    console.print(f"  input:  [cyan]{inp_file}[/cyan]")
    console.print(f"  output: [cyan]{output_dir}[/cyan]")
    if resolved_image:
        console.print(f"  image:  [cyan]{resolved_image}[/cyan]")
    console.print()

    result = CalculixDockerRunner().run(
        inp_file.resolve(),
        output_dir.resolve(),
        image=resolved_image,
        timeout=timeout,
        cpus=cpus,
        memory=memory,
    )
    _print_solve_result(result, inp_file)
    if not result.success:
        raise typer.Exit(1)


app.add_typer(docker_app, name="docker")

# ------------------------------------------------------------------ #
# cae config
# ------------------------------------------------------------------ #

def _configure_workspace(workspace: Optional[Path]) -> None:
    """配置工作目录与派生路径。"""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]cae config[/bold cyan] — 工作目录设置",
        border_style="cyan",
    ))
    console.print()

    if workspace is None:
        current = settings.workspace_path
        default_path = str(current.resolve()) if current else str(Path.cwd())
        raw = typer.prompt(
            "  请输入工作目录",
            default=default_path,
            show_default=True,
        )
        workspace = Path(raw.strip())

    if not workspace.exists():
        try:
            workspace.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            err_console.print(f"\n  无法创建目录: {workspace}\n  {exc}\n")
            raise typer.Exit(1)

    settings.setup_workspace(workspace)

    console.print(f"  [green]OK[/green] 已创建 [cyan]{workspace}/output/[/cyan]")
    console.print(f"  [green]OK[/green] 已创建 [cyan]{workspace}/solvers/[/cyan]")
    console.print("  [green]OK[/green] 配置已保存")
    console.print()

    console.print(f"  工作目录: [cyan]{workspace}[/cyan]")
    console.print(f"  输出目录: [cyan]{settings.workspace_output_dir}[/cyan]")
    console.print(f"  求解器:   [cyan]{settings.workspace_solver_path}[/cyan]")
    console.print()


@app.command(name="config")
def config(
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="工作目录路径",
        show_default=False,
    ),
) -> None:
    """配置工作目录。"""
    _configure_workspace(workspace)


@app.command(name="setting", hidden=True)
def setting_legacy(
    workspace: Optional[Path] = typer.Option(
        None,
        "--workspace", "-w",
        help="工作目录路径",
        show_default=False,
    ),
) -> None:
    """兼容旧命令别名：请使用 `cae config`。"""
    _configure_workspace(workspace)


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
    solver_path: Optional[Path] = typer.Option(
        None,
        "--solver-path",
        help="求解器路径（覆盖已保存的路径）",
        show_default=False,
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
        # 优先使用工作目录下的 output/，否则使用配置的 default_output_dir
        if settings.workspace_output_dir:
            default_out = settings.workspace_output_dir / inp_file.stem
        else:
            default_out = settings.default_output_dir / inp_file.stem
        raw_out = typer.prompt(
            "  输出目录",
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

    if binary is None or solver_path is not None:
        # 如果传入了 --solver-path，或者未找到求解器，提示用户输入
        if binary is None:
            err_console.print("  [yellow]未找到求解器，请指定 CalculiX 路径[/yellow]")
            err_console.print()

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

        # 如果用户通过参数指定了路径，使用它；否则提示输入
        if solver_path is not None:
            user_provided_path = solver_path
        else:
            raw_path = typer.prompt(
                "  求解器路径 (ccx.exe)",
                default=default_path,
                show_default=True,
            )
            user_provided_path = Path(raw_path.strip())

        # 如果用户输入的是目录，取其中的 ccx.exe
        if user_provided_path.is_dir():
            for ccx_name in ["ccx.exe", "ccx"]:
                ccx_in_dir = user_provided_path / ccx_name
                if ccx_in_dir.is_file():
                    user_provided_path = ccx_in_dir
                    break

        # 保存路径到配置
        settings.solver_path = str(user_provided_path.resolve())

        # 清除求解器缓存
        if hasattr(solver_instance, '_find_binary'):
            solver_instance._find_binary.cache_clear()

        # 重新查找
        binary = solver_instance._find_binary()

    # ---- 检查安装状态 ----
    if binary is None or not solver_instance.check_installation():
        console.print(
            "  [bold red]未找到有效的求解器[/bold red]\n"
            "  请检查路径是否正确。\n"
        )
        raise typer.Exit(1)

    version = solver_instance.get_version()
    console.print(f"  使用求解器: [green]{solver}[/green]"
                  + (f"  [dim]({version})[/dim]" if version else ""))
    console.print(f"  输入文件:   [cyan]{inp_file}[/cyan]")
    console.print(f"  输出目录:   [cyan]{output}[/cyan]")
    console.print()

    # ---- 执行求解（带重试循环）----
    while True:
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

        # 成功则退出，失败则询问是否重试
        if result.success:
            break

        console.print()
        retry = typer.prompt(
            "  求解失败，是否重新输入求解器路径？",
            default="y",
            show_default=True,
        )
        if retry.lower() != "y":
            break

        # 清除缓存并重新输入路径
        if hasattr(solver_instance, '_find_binary'):
            solver_instance._find_binary.cache_clear()

        err_console.print("  [yellow]请指定 CalculiX 路径[/yellow]")
        err_console.print()

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
        new_solver_path = Path(raw_path.strip())

        if new_solver_path.is_dir():
            for ccx_name in ["ccx.exe", "ccx"]:
                ccx_in_dir = new_solver_path / ccx_name
                if ccx_in_dir.is_file():
                    new_solver_path = ccx_in_dir
                    break

        settings.solver_path = str(new_solver_path.resolve())
        solver_instance._find_binary.cache_clear()

        # 更新显示的路径
        binary = solver_instance._find_binary()
        if binary:
            version = solver_instance.get_version()
            console.print(f"  使用求解器: [green]{solver}[/green]"
                          + (f"  [dim]({version})[/dim]" if version else ""))
            console.print(f"  求解器路径: [cyan]{binary}[/cyan]")
            console.print(f"  输入文件:   [cyan]{inp_file}[/cyan]")
            console.print(f"  输出目录:   [cyan]{output}[/cyan]")
            console.print()



def _print_solve_result(result, inp_file: Path) -> None:
    """渲染求解结果摘要。"""

    if result.success:
        has_warnings = bool(result.warnings)
        status_title = "[bold yellow]求解完成（含警告）[/bold yellow]" if has_warnings else "[bold green]求解完成！[/bold green]"
        status_border = "yellow" if has_warnings else "green"
        console.print(Panel(
            f"{status_title}  耗时 {result.duration_str}",
            border_style=status_border,
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
                f"\n  [yellow]结果已生成，但检测到 {len(result.warnings)} 条警告[/yellow]"
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
# ------------------------------------------------------------------ #
# cae run - 全流程一键运行（网格 → 求解 → 可视化）
# ------------------------------------------------------------------ #

@app.command(name="run", hidden=True)
def run(
    model_file: Optional[Path] = typer.Argument(None, help="模型文件路径"),
) -> None:
    """
    [bold]全流程一键运行[/bold] — 网格 → 求解 → 可视化

    暂未实现，敬请期待。

    \b
    示例：
      cae run bracket.step
    """
    console.print()
    console.print(Panel.fit(
        "[bold yellow]cae run[/bold yellow] — 全流程仿真",
        border_style="yellow",
    ))
    console.print()
    console.print("  [yellow]此功能暂未实现，敬请期待！[/yellow]\n")
    console.print("  目前可以分步执行：")
    console.print("    [cyan]cae mesh gen[/cyan]  — 网格划分")
    console.print("    [cyan]cae solve[/cyan]    — 执行求解")
    console.print("    [cyan]cae view[/cyan]     — 查看结果\n")


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
            "[bold red]网格划分失败[/bold red]",
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
) -> None:
    """
    [bold]安装 CalculiX 求解器[/bold]

    \b
    示例：
      cae install
    """
    from cae.installer.solver_installer import SolverInstaller

    console.print()
    console.print(Panel.fit("[bold cyan]cae install[/bold cyan] — 安装 CalculiX 求解器", border_style="cyan"))
    console.print()

    # ---- 安装 CalculiX ----
    solver_result = None
    solver_install_path = None
    console.print("  [bold]安装 CalculiX 求解器[/bold]")

    # 如果设置了工作目录，默认使用工作目录下的 solvers 目录
    # 否则使用全局默认路径
    if settings.workspace_solvers_dir:
        default_path = str(settings.workspace_solvers_dir)
        install_path = Path(default_path)
        console.print(f"  使用工作目录: [cyan]{default_path}[/cyan]")
    else:
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
        console.print("  [green]CalculiX 安装成功[/green]")
        console.print(f"  路径: {solver_install_path}")
        console.print()
    elif solver_result:
        console.print()
        console.print("  [red]CalculiX 安装失败[/red]")
        console.print(f"  {solver_result.error_message}")
        console.print()
    else:
        console.print()

    console.print("  现在可以运行 [bold]`cae solve`[/bold] 开始仿真\n")


@app.command()
def diagnose(
    results_dir: Optional[Path] = typer.Argument(None, help="结果目录"),
    inp_file: Optional[Path] = typer.Option(None, "-i", "--inp", help="INP 文件（用于规则检测和参考案例匹配）"),
    ai: bool = typer.Option(False, "--ai", help="启用 AI 深度诊断（需要 Ollama）"),
    guardrails: Optional[Path] = typer.Option(
        None,
        "--guardrails",
        help="???????? JSON ????????????",
    ),
    history_db: Optional[Path] = typer.Option(
        None,
        "--history-db",
        help="???????? SQLite ???, ???????? issue ???????",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="以结构化 JSON 输出到标准输出",
    ),
    json_out: Optional[Path] = typer.Option(
        None,
        "--json-out",
        help="导出结构化诊断 JSON 到指定路径",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Apply safe whitelist auto-fixes without prompting.",
    ),
    no_fix: bool = typer.Option(
        False,
        "--no-fix",
        help="Skip safe auto-fixes without prompting.",
    ),
    fix_output_dir: Optional[Path] = typer.Option(
        None,
        "--fix-output-dir",
        help="Directory for generated backup and fixed INP files.",
    ),
) -> None:
    """
    [bold]诊断仿真问题[/bold]

    基于规则层检测仿真结果中的常见问题：
    1. 规则检测（Level 1）：扫描 stderr/结果文件中的 527 个源码硬编码模式
    2. INP 文件检查：检测被注释的关键卡片、缺少必要关键字等
    3. 参考案例对比（Level 2）：638 个官方测试集

    使用 [bold]--ai[/bold] 启用 AI 深度诊断。
    """
    from cae.ai.diagnose import (
        build_diagnosis_summary,
        diagnosis_result_to_dict,
        diagnose_results,
        issue_to_dict,
    )

    if fix and no_fix:
        err_console.print("\n  [red]错误: --fix and --no-fix cannot be used together.[/red]\n")
        raise typer.Exit(2)

    if not json_output:
        console.print()
        console.print(Panel.fit("[bold cyan]cae diagnose[/bold cyan] — 诊断仿真问题", border_style="cyan"))
        console.print()

    if results_dir is None:
        raw = typer.prompt("  请输入结果目录路径")
        results_dir = Path(raw.strip())

    # 如果传入的是文件（通常是 INP 文件），自动提取目录和文件路径
    if results_dir.is_file():
        inp_file = results_dir
        results_dir = results_dir.parent
        if not json_output:
            console.print(f"  检测到 INP 文件，自动使用其目录作为结果目录: [cyan]{results_dir}[/cyan]")
    elif inp_file is None and not any(results_dir.glob("*.frd")):
        # 如果没有指定 INP 文件，且 results_dir 下没有 .frd 文件
        # 尝试在 results_dir 下找 INP 文件
        inp_files = list(results_dir.glob("*.inp"))
        if inp_files:
            inp_file = inp_files[0]
            if not json_output:
                console.print(f"  自动检测到 INP 文件: [cyan]{inp_file}[/cyan]")

    # ========== Level 1 + 2: 规则检测 + 参考案例 ==========
    client = None
    if ai:
        from cae.ai.llm_client import LLMConfig, LLMClient
        config = LLMConfig(use_ollama=True, model_name="deepseek-r1:1.5b")
        client = LLMClient(config=config)
        if not json_output:
            console.print("  [yellow]AI 深度诊断已启用[/yellow]\n")
    else:
        if not json_output:
            console.print("  [dim]使用 --ai 启用 AI 深度诊断[/dim]\n")

    result = diagnose_results(
        results_dir,
        client,
        inp_file=inp_file,
        stream=False,
        guardrails_path=guardrails,
        history_db_path=history_db,
    )

    payload = None
    if json_out is not None or json_output:
        payload = diagnosis_result_to_dict(
            result,
            results_dir=results_dir,
            inp_file=inp_file,
            ai_enabled=ai,
        )

    if json_out is not None and payload is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not json_output:
            console.print(f"  [green]结构化诊断已导出:[/green] [cyan]{json_out}[/cyan]")

    if json_output and payload is not None:
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        if not result.success:
            raise typer.Exit(1)
        return

    if not result.success:
        err_console.print(f"\n  诊断失败: {result.error}\n")
        raise typer.Exit(1)

    # 显示规则检测结果
    if result.issues:
        summary = build_diagnosis_summary(result.issues)
        top_issue = summary["top_issue"]
        console.print(f"  [bold red]发现 {summary['total']} 个问题[/bold red]")
        console.print(f"  严重问题: [red]{summary['error_count']}[/red]  警告: [yellow]{summary['warning_count']}[/yellow]")
        console.print(f"  风险评分: [bold]{summary.get('risk_score', 0)}/100[/bold]")
        console.print(
            "  诊断分层: "
            f"blocking={summary.get('blocking_count', 0)}, "
            f"review={summary.get('needs_review_count', 0)}, "
            f"risk={summary.get('risk_level', 'low')}"
        )
        confidence_summary = ", ".join(
            f"{k}:{v}" for k, v in sorted(summary.get("confidence_counts", {}).items())
        )
        if confidence_summary:
            console.print(f"  证据置信度: {confidence_summary}")
        category_summary = ", ".join(
            f"{k}:{v}" for k, v in sorted(summary.get("by_category", {}).items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        )
        if category_summary:
            console.print(f"  主要问题分布: {category_summary}")
        if top_issue is not None:
            console.print(f"  最优先问题: [bold]{top_issue.title}[/bold]")
            console.print(f"  首步操作: {summary['first_action'] or '先按最高优先级问题检查输入与约束'}")
        for idx, action in enumerate(summary.get("action_items", []), 1):
            console.print(f"  建议动作 {idx}: {action}")
        for iss in result.issues[:15]:
            issue_payload = issue_to_dict(iss)
            icon = "[red]X[/red]" if iss.severity == "error" else "[yellow]![/yellow]"
            priority_text = f"P{iss.priority}" if iss.priority is not None else "P?"
            console.print(f"  {icon} [{priority_text}] [{iss.category}] {iss.cause[:80]}")
            evidence_items: list[str] = []
            evidence_line = issue_payload.get("evidence_line")
            if evidence_line:
                evidence_items.append(f"line={evidence_line}")
            evidence_score = issue_payload.get("evidence_score")
            if evidence_score is not None:
                evidence_items.append(f"score={float(evidence_score):.2f}")
            support_count = issue_payload.get("evidence_support_count")
            if support_count is not None:
                evidence_items.append(f"support={int(support_count)}")
            source_trust = issue_payload.get("evidence_source_trust")
            if source_trust is not None:
                evidence_items.append(f"trust={float(source_trust):.2f}")
            history_hits = issue_payload.get("history_hits")
            if history_hits is not None and int(history_hits) > 0:
                evidence_items.append(f"hist={int(history_hits)}")
            history_similarity = issue_payload.get("history_similarity")
            if history_similarity is not None and float(history_similarity) > 0:
                evidence_items.append(f"h-sim={float(history_similarity):.2f}")
            if evidence_items:
                console.print("     [dim]evidence: " + " | ".join(evidence_items) + "[/dim]")
            evidence_conflict = issue_payload.get("evidence_conflict")
            if evidence_conflict:
                console.print(f"     [dim]evidence_conflict: {evidence_conflict}[/dim]")
            if iss.action:
                console.print(f"     -> {iss.action}")
        console.print()
    else:
        console.print("  [green]✓ 规则检测未发现明显问题[/green]\n")

    # 显示相似案例
    if result.similar_cases:
        console.print(f"  [bold]参考案例匹配[/bold]：找到 {len(result.similar_cases)} 个相似案例")
        for case in result.similar_cases[:3]:
            console.print(f"  - {case['name']} (相似度 {case['similarity_score']}%)")
            if case.get('expected_disp_max'):
                console.print(f"    预期位移: {case['expected_disp_max']:.3e}")
        console.print()

    # ========== AI 诊断结果 ==========
    if result.level3_diagnosis:
        console.print(Panel(result.level3_diagnosis, title="AI 诊断", border_style="yellow"))
        console.print()

    # ========== 自动修复（仅安全白名单）==========
    if result.issues and inp_file and inp_file.exists():
        from cae.ai.fix_rules import fix_inp, get_safe_autofixable_issues

        safe_fixable_issues = get_safe_autofixable_issues(result.issues)
        if safe_fixable_issues:
            if fix:
                user_input = "y"
            elif no_fix:
                user_input = "n"
            else:
                console.print(
                    f"  [bold yellow]是否执行安全自动修复？[/bold yellow] "
                    f"[dim](仅白名单问题，当前可修复 {len(safe_fixable_issues)} 项)[/dim] [bold yellow][y/N]:[/bold yellow] ",
                    end="",
                )
                user_input = input().strip().lower()
            if user_input == "y":
                fix_result = fix_inp(
                    inp_file,
                    result.issues,
                    results_dir,
                    output_dir=fix_output_dir,
                )
                if fix_result.success:
                    console.print(f"  [green]✓ 原文件已保留: {fix_result.backup_path}[/green]")
                    console.print(f"  [green]✓ 修复文件已生成: {fix_result.fixed_path}[/green]")
                    console.print(f"  [dim]修复内容: {fix_result.changes_summary}[/dim]")
                    status_label = {
                        "passed": "[green]passed[/green]",
                        "failed": "[red]failed[/red]",
                        "skipped": "[yellow]skipped[/yellow]",
                    }.get(fix_result.verification_status, f"[yellow]{fix_result.verification_status}[/yellow]")
                    console.print(f"  [dim]修复后验证状态: {status_label}[/dim]")
                    if fix_result.verification_notes:
                        console.print(f"  [dim]验证说明: {fix_result.verification_notes}[/dim]")
                else:
                    console.print(f"  [red]✗ {fix_result.error}[/red]")
            else:
                console.print("  已跳过安全自动修复")
        else:
            console.print("  [dim]未发现白名单内可自动修复的问题[/dim]")

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
