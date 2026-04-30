from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from cae.config import settings
from cae.docker import list_image_spec_dicts
from cae.inp import InpParser, load_kw_list
from cae.runtimes import DockerRuntime
from cae.solvers.registry import list_solvers


def build_gui_snapshot(project_root: Path, inp_file: Optional[Path] = None) -> dict[str, Any]:
    """构建桌面端使用的真实项目状态快照。"""
    root = project_root.resolve()
    files = _scan_files(root)
    input_files = _file_entries(root, files["input"])
    result_files = _file_entries(root, files["result"])
    log_files = _file_entries(root, files["log"])
    geometry_files = _file_entries(root, files["geometry"])

    active_input = _resolve_active_input(root, inp_file, files["input"])
    kw_list = load_kw_list()
    inp_payload = _build_inp_payload(root, active_input, kw_list)
    reference_case_count = _count_json_records(
        Path(__file__).parent / "ai" / "data" / "reference_cases.json"
    )

    docker_runtime = DockerRuntime()
    docker_info = asdict(docker_runtime.inspect())
    local_images = docker_runtime.list_images() if docker_info.get("available") else []
    local_image_sizes = (
        _docker_image_size_map(docker_runtime) if docker_info.get("available") else {}
    )
    docker_catalog = _docker_catalog(list_image_spec_dicts(), local_images, local_image_sizes)

    output_dir = settings.workspace_output_dir or settings.default_output_dir
    project_name = (
        active_input.stem
        if active_input
        else (input_files[0]["stem"] if input_files else root.name)
    )

    return {
        "success": True,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_root": str(root),
        "active_input": _relative_to_root(root, active_input) if active_input else None,
        "project": {
            "name": project_name,
            "input_file": _relative_to_root(root, active_input) if active_input else None,
            "output_dir": str(output_dir),
        },
        "config": {
            "config_dir": str(settings.config_dir),
            "data_dir": str(settings.data_dir),
            "solvers_dir": str(settings.solvers_dir),
            "models_dir": str(settings.models_dir),
            "workspace": str(settings.workspace_path) if settings.workspace_path else None,
            "default_solver": settings.default_solver,
            "default_output_dir": str(settings.default_output_dir),
            "solver_path": settings.solver_path,
            "active_model": settings.active_model,
            "evidence_guard": True,
        },
        "models": _build_model_payload(root),
        "assets": {
            "input_files": len(input_files),
            "result_files": len(result_files),
            "log_files": len(log_files),
            "geometry_files": len(geometry_files),
            "reference_cases": reference_case_count,
            "keywords": len(kw_list),
            "diagnosis_rules": _count_diagnostic_rules(),
        },
        "files": {
            "inputs": input_files,
            "results": result_files,
            "logs": log_files,
            "geometry": geometry_files,
        },
        "inp": inp_payload,
        "docker": {
            **docker_info,
            "local_images": local_images,
            "local_image_count": len(local_images),
            "catalog": docker_catalog,
        },
        "solvers": list_solvers(),
        "viewer": _build_viewer_payload(result_files, log_files, inp_payload),
        "solve_history": _build_solve_history(result_files, log_files),
    }


def _scan_files(root: Path) -> dict[str, list[Path]]:
    input_exts = {".inp", ".cfg", ".sif", ".comm", ".export"}
    result_exts = {".frd", ".dat", ".vtu", ".vtk", ".msh"}
    log_exts = {".log", ".out", ".err", ".sta", ".cvg", ".stderr", ".stdout"}
    geometry_exts = {".step", ".stp", ".iges", ".igs", ".brep", ".geo"}
    ignored_dirs = {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
        "target",
        "dist",
        "tests",
        "cae",
        "cae-gui",
        "scripts",
        "docs",
        "__pycache__",
    }
    buckets: dict[str, list[Path]] = {"input": [], "result": [], "log": [], "geometry": []}

    for current, dirs, names in os.walk(root, onerror=lambda _exc: None):
        dirs[:] = [
            name for name in dirs if name not in ignored_dirs and not name.startswith(".pytest-tmp")
        ]
        current_path = Path(current)
        for name in names:
            path = current_path / name
            suffix = path.suffix.lower()
            if suffix in input_exts:
                buckets["input"].append(path)
            elif suffix in result_exts:
                buckets["result"].append(path)
            elif suffix in log_exts:
                buckets["log"].append(path)
            elif suffix in geometry_exts:
                buckets["geometry"].append(path)

    for paths in buckets.values():
        paths.sort(key=lambda item: _relative_to_root(root, item).lower())
    return buckets


def _file_entries(root: Path, paths: list[Path], *, limit: int = 80) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in paths[:limit]:
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(
            {
                "name": path.name,
                "stem": path.stem,
                "path": _relative_to_root(root, path),
                "type": path.suffix.lower().lstrip(".").upper() or "FILE",
                "size": stat.st_size,
                "size_label": _fmt_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return entries


def _resolve_active_input(
    root: Path, inp_file: Optional[Path], input_files: list[Path]
) -> Optional[Path]:
    candidates: list[Path] = []
    if inp_file is not None:
        candidates.append(inp_file if inp_file.is_absolute() else root / inp_file)
    candidates.append(root / "examples" / "simple_beam.inp")
    candidates.extend(input_files)
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


def _build_inp_payload(
    root: Path, inp_file: Optional[Path], kw_list: dict[str, Any]
) -> dict[str, Any]:
    if inp_file is None:
        return _empty_inp_payload(file=None, error="未发现可用 INP 文件")

    try:
        blocks = InpParser().parse(inp_file)
    except Exception as exc:
        return _empty_inp_payload(file=_relative_to_root(root, inp_file), error=str(exc))

    keyword_count: dict[str, int] = {}
    unknown_keywords: list[str] = []
    block_payloads: list[dict[str, Any]] = []
    for block in blocks:
        keyword_count[block.keyword_name] = keyword_count.get(block.keyword_name, 0) + 1
        issues: list[dict[str, str]] = []
        if block.keyword_name not in kw_list:
            issues.append(
                {"code": "unknown_keyword", "message": f"未知关键词 {block.keyword_name}"}
            )
            if block.keyword_name not in unknown_keywords:
                unknown_keywords.append(block.keyword_name)
        block_payloads.append(
            {
                "keyword": block.keyword_name,
                "name": block.get_param("NAME"),
                "line_start": block.line_range[0] + 1,
                "line_end": block.line_range[1] + 1,
                "data_line_count": len([line for line in block.data_lines if line.strip()]),
                "status": "ok" if not issues else "needs_review",
                "issues": issues,
            }
        )

    def data_count(keyword: str) -> int:
        return sum(
            len([line for line in block.data_lines if line.strip()])
            for block in blocks
            if block.keyword_name == keyword
        )

    return {
        "available": True,
        "valid": not unknown_keywords,
        "file": _relative_to_root(root, inp_file),
        "error": None,
        "block_count": len(blocks),
        "keyword_count": keyword_count,
        "unknown_keywords": unknown_keywords,
        "blocks": block_payloads,
        "node_count": data_count("*NODE"),
        "element_count": data_count("*ELEMENT"),
        "material_count": keyword_count.get("*MATERIAL", 0),
        "step_count": keyword_count.get("*STEP", 0),
        "boundary_count": keyword_count.get("*BOUNDARY", 0),
    }


def _empty_inp_payload(file: Optional[str], error: str) -> dict[str, Any]:
    return {
        "available": False,
        "valid": False,
        "file": file,
        "error": error,
        "blocks": [],
        "keyword_count": {},
        "node_count": 0,
        "element_count": 0,
        "material_count": 0,
        "step_count": 0,
        "boundary_count": 0,
    }


def _docker_catalog(
    specs: list[dict[str, Any]],
    local_images: list[str],
    local_image_sizes: dict[str, str],
) -> list[dict[str, Any]]:
    local_set = set(local_images)
    catalog: list[dict[str, Any]] = []
    for spec in specs:
        image = str(spec.get("image") or "")
        catalog.append(
            {
                **spec,
                "status": "pulled" if image in local_set else "available",
                "size": local_image_sizes.get(image),
            }
        )
    return catalog


def _build_model_payload(root: Path) -> dict[str, Any]:
    """汇总 GUI 可切换的真实本地模型。"""
    active_model = settings.active_model
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()

    def is_active(name: str, value: str, path: Optional[Path] = None) -> bool:
        if not active_model:
            return False
        active = active_model.replace("\\", "/").lower()
        values = {name.lower(), value.replace("\\", "/").lower()}
        if path:
            values.add(str(path).replace("\\", "/").lower())
            values.add(path.name.lower())
        return active in values

    def add_entry(
        *,
        name: str,
        value: str,
        source: str,
        path: Optional[Path] = None,
        size_label: Optional[str] = None,
        modified: Optional[str] = None,
    ) -> None:
        if not name or not value:
            return
        key = value.replace("\\", "/").lower()
        if key in seen:
            return
        seen.add(key)
        entries.append(
            {
                "name": name,
                "value": value,
                "source": source,
                "path": str(path) if path else None,
                "size_label": size_label,
                "modified": modified,
                "active": is_active(name, value, path),
            }
        )

    for directory, source in _model_search_dirs(root):
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.gguf"), key=lambda item: item.name.lower()):
            try:
                stat = path.stat()
            except OSError:
                continue
            value = path.name if path.parent == settings.models_dir else str(path)
            add_entry(
                name=path.name,
                value=value,
                source=source,
                path=path,
                size_label=_fmt_size(stat.st_size),
                modified=datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            )

    for item in _list_ollama_models():
        add_entry(
            name=item["name"],
            value=item["name"],
            source="ollama",
            size_label=item.get("size"),
            modified=item.get("modified"),
        )

    if active_model and not any(item["active"] for item in entries):
        add_entry(name=active_model, value=active_model, source="config")
        if entries:
            entries[-1]["active"] = True

    entries.sort(key=lambda item: (not item["active"], item["source"], item["name"].lower()))
    return {"active": active_model, "available": entries}


def _model_search_dirs(root: Path) -> list[tuple[Path, str]]:
    """模型来源目录，兼容当前配置目录和早期 ~/.cae-cli/models。"""
    dirs = [
        (settings.models_dir, "models_dir"),
        (Path.home() / ".cae-cli" / "models", "legacy_models_dir"),
        (root / "models", "project_models"),
    ]
    unique: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path, source in dirs:
        key = str(path.resolve() if path.exists() else path).lower()
        if key not in seen:
            seen.add(key)
            unique.append((path, source))
    return unique


def _list_ollama_models() -> list[dict[str, str]]:
    """读取 Ollama 本地模型；不可用时静默返回空列表。"""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    models: list[dict[str, str]] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if not parts:
            continue
        models.append(
            {
                "name": parts[0],
                "size": parts[1] if len(parts) > 1 else "",
                "modified": " ".join(parts[2:]) if len(parts) > 2 else "",
            }
        )
    return models


def _docker_image_size_map(runtime: DockerRuntime) -> dict[str, str]:
    result = runtime.command(
        ["image", "ls", "--format", "{{.Repository}}:{{.Tag}}\t{{.Size}}"], timeout=30
    )
    if result.returncode != 0:
        return {}
    sizes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "\t" not in line:
            continue
        image, size = line.split("\t", 1)
        image = image.strip()
        if image and image != "<none>:<none>":
            sizes[image] = size.strip()
    return sizes


def _build_viewer_payload(
    result_files: list[dict[str, Any]],
    log_files: list[dict[str, Any]],
    inp_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "has_results": bool(result_files),
        "fields": [
            {
                "key": item["path"],
                "label": f"{item['type']} 文件",
                "unit": item["size_label"],
                "max": item["name"],
                "color": "#38d5ff",
            }
            for item in result_files[:4]
        ],
        "metrics": [
            {
                "label": "节点数",
                "value": inp_payload.get("node_count", 0),
                "unit": "个",
                "hint": "来自 INP",
            },
            {
                "label": "单元数",
                "value": inp_payload.get("element_count", 0),
                "unit": "个",
                "hint": "来自 INP",
            },
            {"label": "结果文件", "value": len(result_files), "unit": "个", "hint": "扫描项目目录"},
            {
                "label": "日志证据",
                "value": len(log_files),
                "unit": "个",
                "hint": "stderr/out/sta/cvg",
            },
        ],
    }


def _build_solve_history(
    result_files: list[dict[str, Any]],
    log_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for item in [*result_files, *log_files][:12]:
        history.append(
            {
                "name": item["stem"],
                "file": item["path"],
                "status": "有结果" if item in result_files else "有日志",
                "time": str(item["modified"])[11:16]
                if len(str(item["modified"])) >= 16
                else "--:--",
            }
        )
    return history


def _count_json_records(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return len(data)
    return 0


def _count_diagnostic_rules() -> int:
    try:
        text = (Path(__file__).parent / "ai" / "diagnose.py").read_text(encoding="utf-8")
    except OSError:
        return 0
    return text.count("DiagnosticIssue(")


def _relative_to_root(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _fmt_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"
