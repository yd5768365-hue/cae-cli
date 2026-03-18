"""
Viewer module - VTK visualization and result rendering.
Lazy loads heavy dependencies (pyvista, meshio) to avoid import errors
when those packages are not installed.
"""
from __future__ import annotations

__all__ = [
    # FRD parser (always available)
    "FrdData",
    "FrdNodes",
    "FrdElement",
    "FrdResultStep",
    "parse_frd",
    # PyVista renderer (lazy loaded)
    "MeshInfo",
    "RenderResult",
    "get_mesh_info",
    "load_result",
    "render_all",
    "render_animation",
    "render_displacement",
    "render_slice",
    "render_von_mises",
    # Server (always available)
    "ViewServer",
    "start_server",
    # VTK export (lazy loaded)
    "VtkExportResult",
    "frd_to_vtu",
    # Report (always available)
    "ReportConfig",
    "ReportSection",
    "generate_report",
    "build_report_from_renders",
]


def __getattr__(name: str):
    """Lazy load heavy modules on demand."""
    if name in (
        "MeshInfo",
        "RenderResult",
        "get_mesh_info",
        "load_result",
        "render_all",
        "render_animation",
        "render_displacement",
        "render_slice",
        "render_von_mises",
    ):
        from cae.viewer import pyvista_renderer

        return getattr(pyvista_renderer, name)
    if name in ("VtkExportResult", "frd_to_vtu"):
        from cae.viewer import vtk_export

        return getattr(vtk_export, name)
    if name in ("ViewServer", "start_server"):
        from cae.viewer import server

        return getattr(server, name)
    if name in ("ReportConfig", "ReportSection", "generate_report", "build_report_from_renders"):
        from cae.viewer import report

        return getattr(report, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# Always-available imports (no heavy dependencies)
from cae.viewer.frd_parser import FrdData, FrdNodes, FrdElement, FrdResultStep, parse_frd
