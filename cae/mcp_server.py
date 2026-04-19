from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

from cae.ai.diagnose import diagnose_results, diagnosis_result_to_dict
from cae.config import settings
from cae.inp import InpParser, load_kw_list
from cae.solvers.base import SolveResult
from cae.solvers.registry import get_solver, list_solvers


def _ok(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _error(code: str, message: str, *, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "details": _safe_json_value(details or {}),
        },
    }


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {k: _safe_json_value(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, set):
        return sorted((_safe_json_value(v) for v in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(v) for v in value]
    return value


def _resolve_path(raw: str | Path, *, must_exist: bool = False, kind: str = "path") -> Path:
    if isinstance(raw, str) and not raw.strip():
        raise ValueError(f"{kind} must not be empty")
    p = Path(raw).expanduser().resolve()
    if must_exist and not p.exists():
        raise FileNotFoundError(f"{kind} not found: {p}")
    return p


def _path_error(exc: Exception, *, kind: str, raw: Any) -> dict[str, Any]:
    code = "not_found" if isinstance(exc, FileNotFoundError) else "invalid_input"
    return _error(code, str(exc), details={kind: raw})


def _default_output_dir(inp_file: Path) -> Path:
    if settings.workspace_output_dir:
        return (settings.workspace_output_dir / inp_file.stem).resolve()
    return (settings.default_output_dir / inp_file.stem).resolve()


def _solve_result_to_dict(result: SolveResult) -> dict[str, Any]:
    output_files = [str(p) for p in result.output_files]
    return {
        "success": result.success,
        "output_dir": str(result.output_dir),
        "output_files": output_files,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "returncode": result.returncode,
        "duration_seconds": result.duration_seconds,
        "duration": result.duration_str,
        "error_message": result.error_message,
        "warnings": list(result.warnings),
        "frd_file": str(result.frd_file) if result.frd_file else None,
        "dat_file": str(result.dat_file) if result.dat_file else None,
    }


def _clear_solver_cache(solver_instance: Any) -> None:
    finder = getattr(solver_instance, "_find_binary", None)
    cache_clear = getattr(finder, "cache_clear", None)
    if callable(cache_clear):
        try:
            cache_clear()
        except Exception:
            pass


@contextmanager
def _temporary_solver_path(solver_path: Path | None) -> Iterator[None]:
    if solver_path is None:
        yield
        return

    had_solver_path = "solver_path" in settings._data
    previous_solver_path = settings._data.get("solver_path")
    settings._data["solver_path"] = str(solver_path)
    try:
        yield
    finally:
        if had_solver_path:
            settings._data["solver_path"] = previous_solver_path
        else:
            settings._data.pop("solver_path", None)


def tool_health() -> dict[str, Any]:
    try:
        solver_info = list_solvers()
    except Exception as exc:
        return _error("solver_probe_failed", str(exc))

    default_solver = settings.default_solver
    installed_solver_names = [item["name"] for item in solver_info if item.get("installed")]
    return _ok(
        {
            "service": "cae-cli-mcp",
            "default_solver": default_solver,
            "installed_solvers": installed_solver_names,
            "solvers": solver_info,
        }
    )


def tool_solvers() -> dict[str, Any]:
    try:
        return _ok({"solvers": list_solvers()})
    except Exception as exc:
        return _error("solver_probe_failed", str(exc))


def tool_solve(
    *,
    inp_file: str,
    output_dir: str | None = None,
    solver: str | None = None,
    timeout: int = 3600,
    solver_path: str | None = None,
) -> dict[str, Any]:
    try:
        inp_path = _resolve_path(inp_file, must_exist=True, kind="inp_file")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return _path_error(exc, kind="inp_file", raw=inp_file)

    if not inp_path.is_file():
        return _error("invalid_input", "inp_file must be a file", details={"inp_file": str(inp_path)})
    if inp_path.suffix.lower() != ".inp":
        return _error("invalid_input", "inp_file must end with .inp", details={"inp_file": str(inp_path)})

    if timeout <= 0:
        return _error("invalid_input", "timeout must be > 0", details={"timeout": timeout})

    resolved_solver_path: Path | None = None
    if solver_path:
        try:
            resolved_solver_path = _resolve_path(solver_path, must_exist=True, kind="solver_path")
        except (FileNotFoundError, OSError, ValueError) as exc:
            return _path_error(exc, kind="solver_path", raw=solver_path)

    solver_name = solver or settings.default_solver
    try:
        solver_instance = get_solver(solver_name)
    except ValueError as exc:
        return _error("invalid_solver", str(exc), details={"solver": solver_name})

    if output_dir is None:
        out_path = _default_output_dir(inp_path)
    else:
        try:
            out_path = _resolve_path(output_dir, must_exist=False, kind="output_dir")
        except (OSError, ValueError) as exc:
            return _path_error(exc, kind="output_dir", raw=output_dir)

    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _error("output_error", str(exc), details={"output_dir": str(out_path)})

    try:
        with _temporary_solver_path(resolved_solver_path):
            _clear_solver_cache(solver_instance)
            result = solver_instance.solve(inp_path, out_path, timeout=timeout)
    except Exception as exc:
        return _error(
            "solve_failed",
            str(exc),
            details={
                "inp_file": str(inp_path),
                "output_dir": str(out_path),
                "solver": solver_name,
            },
        )
    finally:
        _clear_solver_cache(solver_instance)

    return _ok(_safe_json_value(_solve_result_to_dict(result)))


def tool_diagnose(
    *,
    results_dir: str,
    inp_file: str | None = None,
    ai: bool = False,
    guardrails_path: str | None = None,
    history_db_path: str | None = None,
    model_name: str = "deepseek-r1:1.5b",
) -> dict[str, Any]:
    try:
        resolved_results_dir = _resolve_path(results_dir, must_exist=True, kind="results_dir")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return _path_error(exc, kind="results_dir", raw=results_dir)

    if not resolved_results_dir.is_dir():
        return _error(
            "invalid_input",
            "results_dir must be a directory",
            details={"results_dir": str(resolved_results_dir)},
        )

    resolved_inp: Optional[Path] = None
    if inp_file:
        try:
            resolved_inp = _resolve_path(inp_file, must_exist=True, kind="inp_file")
        except (FileNotFoundError, OSError, ValueError) as exc:
            return _path_error(exc, kind="inp_file", raw=inp_file)

    resolved_guardrails: Optional[Path] = None
    if guardrails_path:
        try:
            resolved_guardrails = _resolve_path(guardrails_path, must_exist=True, kind="guardrails_path")
        except (FileNotFoundError, OSError, ValueError) as exc:
            return _path_error(exc, kind="guardrails_path", raw=guardrails_path)

    resolved_history_db: Optional[Path] = None
    if history_db_path:
        try:
            resolved_history_db = _resolve_path(history_db_path, must_exist=False, kind="history_db_path")
        except (OSError, ValueError) as exc:
            return _path_error(exc, kind="history_db_path", raw=history_db_path)

    client = None
    if ai:
        try:
            from cae.ai.llm_client import LLMClient, LLMConfig

            client = LLMClient(config=LLMConfig(use_ollama=True, model_name=model_name))
        except Exception as exc:
            return _error("ai_client_error", str(exc), details={"model_name": model_name})

    try:
        result = diagnose_results(
            resolved_results_dir,
            client=client,
            inp_file=resolved_inp,
            stream=False,
            guardrails_path=resolved_guardrails,
            history_db_path=resolved_history_db,
        )
        payload = diagnosis_result_to_dict(
            result,
            results_dir=resolved_results_dir,
            inp_file=resolved_inp,
            ai_enabled=ai,
        )
    except Exception as exc:
        return _error(
            "diagnose_failed",
            str(exc),
            details={"results_dir": str(resolved_results_dir)},
        )
    return _ok(_safe_json_value(payload))


def tool_inp_check(*, inp_file: str) -> dict[str, Any]:
    try:
        inp_path = _resolve_path(inp_file, must_exist=True, kind="inp_file")
    except (FileNotFoundError, OSError, ValueError) as exc:
        return _path_error(exc, kind="inp_file", raw=inp_file)

    if not inp_path.is_file():
        return _error("invalid_input", "inp_file must be a file", details={"inp_file": str(inp_path)})

    parser = InpParser()
    try:
        blocks = parser.parse(inp_path)
    except Exception as exc:
        return _error("parse_error", str(exc), details={"inp_file": str(inp_path)})

    kw_list = load_kw_list()
    unknown_keywords: list[str] = []
    missing_required: list[dict[str, str]] = []
    seen_missing: set[tuple[str, str]] = set()

    for block in blocks:
        kw_def = kw_list.get(block.keyword_name)
        if kw_def is None:
            if block.keyword_name not in unknown_keywords:
                unknown_keywords.append(block.keyword_name)
            continue

        for arg in kw_def.get("arguments", []):
            arg_name = str(arg.get("name", "")).strip()
            if not arg_name:
                continue
            if bool(arg.get("required")) and not block.get_param(arg_name):
                key = (block.keyword_name, arg_name)
                if key in seen_missing:
                    continue
                seen_missing.add(key)
                missing_required.append(
                    {
                        "keyword": block.keyword_name,
                        "argument": arg_name,
                        "reason": "required_argument_missing",
                    }
                )

    return _ok(
        {
            "valid": not unknown_keywords and not missing_required,
            "inp_file": str(inp_path),
            "block_count": len(blocks),
            "unknown_keywords": unknown_keywords,
            "missing_required": missing_required,
        }
    )


def create_mcp_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - import is environment-dependent
        raise RuntimeError(
            "mcp is not installed. Install with: pip install \"cae-cxx[mcp]\""
        ) from exc

    mcp = FastMCP("cae-cli", json_response=True)

    @mcp.tool()
    def cae_health() -> dict[str, Any]:
        """Return runtime health and solver availability."""
        return tool_health()

    @mcp.tool()
    def cae_solvers() -> dict[str, Any]:
        """List registered solvers and installation status."""
        return tool_solvers()

    @mcp.tool()
    def cae_solve(
        inp_file: str,
        output_dir: str | None = None,
        solver: str | None = None,
        timeout: int = 3600,
        solver_path: str | None = None,
    ) -> dict[str, Any]:
        """Run FEA solve for an .inp file and return structured output."""
        return tool_solve(
            inp_file=inp_file,
            output_dir=output_dir,
            solver=solver,
            timeout=timeout,
            solver_path=solver_path,
        )

    @mcp.tool()
    def cae_diagnose(
        results_dir: str,
        inp_file: str | None = None,
        ai: bool = False,
        guardrails_path: str | None = None,
        history_db_path: str | None = None,
        model_name: str = "deepseek-r1:1.5b",
    ) -> dict[str, Any]:
        """Run diagnosis and return structured evidence JSON."""
        return tool_diagnose(
            results_dir=results_dir,
            inp_file=inp_file,
            ai=ai,
            guardrails_path=guardrails_path,
            history_db_path=history_db_path,
            model_name=model_name,
        )

    @mcp.tool()
    def cae_inp_check(inp_file: str) -> dict[str, Any]:
        """Validate INP structure and required keyword arguments."""
        return tool_inp_check(inp_file=inp_file)

    return mcp


def main() -> None:  # pragma: no cover - exercised in real MCP runtime
    try:
        mcp = create_mcp_server()
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
