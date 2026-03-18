"""
Report module - HTML report generation.
Re-exports from html_generator for backward compatibility.
"""
from cae.viewer.html_generator import (
    ReportConfig,
    ReportSection,
    generate_report,
    build_report_from_renders,
    _img_to_base64,
)

__all__ = [
    "ReportConfig",
    "ReportSection",
    "generate_report",
    "build_report_from_renders",
    "_img_to_base64",
]
