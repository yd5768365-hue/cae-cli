"""
HTTP server for browsing VTK/FEM result files in the browser.
Uses ParaView Glance for WebGL-based 3D visualization.
"""
from __future__ import annotations

import logging
import mimetypes
import socket
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Default port range for finding an available port
DEFAULT_PORT = 8888


def _collect_vtu_files(root_dir: Path) -> list[Path]:
    """Collect all VTK files (.vtu, .vtk) from a directory."""
    return list(root_dir.glob("*.vtu")) + list(root_dir.glob("*.vtk"))


def _find_available_port(start_port: int = DEFAULT_PORT) -> int:
    """Find an available port starting from start_port."""
    port = start_port
    max_attempts = 100
    for _ in range(max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except OSError:
            port += 1
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")


# Alias for backward compatibility (defined after _find_available_port)
_find_free_port = _find_available_port


class ViewServer:
    """
    Simple HTTP server that serves VTK files for browser-based visualization.

    Args:
        root_dir: Directory containing .vtu/.vtk/.frd files to serve
        port: Port number (auto-selected if not available)
    """

    def __init__(self, root_dir: Path, port: int = DEFAULT_PORT):
        self.root_dir = root_dir.resolve()
        self.port = _find_available_port(port)
        self._server = None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"

    def start(self) -> None:
        """Start the HTTP server (blocking)."""
        import http.server
        import socketserver

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(self._server.root_dir), **kwargs)

            def log_message(self, format, *args):
                log.debug(format, *args)

        Handler._server = self  # type: ignore

        # 使用 ThreadingTCPServer 以便 Ctrl+C 能立即中断
        self._server = socketserver.ThreadingTCPServer(("", self.port), Handler)
        log.info(f"Server started at {self.url}")
        self._server.serve_forever()

    def shutdown(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server = None

    def server_close(self) -> None:
        """Alias for shutdown() - for compatibility with standard library."""
        self.shutdown()

    def serve_forever(self) -> None:
        """Start the server and run indefinitely (blocking)."""
        self.start()


def start_server(
    root_dir: Path,
    port: int = DEFAULT_PORT,
    auto_convert: bool = True,
    open_browser: bool = False,
) -> tuple[ViewServer, str, list[Path]]:
    """
    Start an HTTP server for browsing simulation results.

    Args:
        root_dir: Directory containing result files
        port: Port to serve on
        auto_convert: If True, automatically convert .frd to .vtu
        open_browser: If True, open the default browser

    Returns:
        Tuple of (server, url, files)

    Raises:
        FileNotFoundError: If no result files found and auto_convert is False
        RuntimeError: If no valid files can be served
    """
    root_dir = root_dir.resolve()

    if not root_dir.exists():
        raise FileNotFoundError(f"Directory not found: {root_dir}")

    # Collect VTK files
    vtu_files = list(root_dir.glob("*.vtu")) + list(root_dir.glob("*.vtk"))

    # Auto-convert .frd files if requested
    frd_files = list(root_dir.glob("*.frd"))
    if auto_convert and frd_files and not vtu_files:
        from .vtk_export import frd_to_vtu

        log.info(f"Auto-converting {len(frd_files)} .frd files to .vtu")
        for frd_file in frd_files:
            result = frd_to_vtu(frd_file, root_dir)
            if result.success:
                vtu_files.extend(root_dir.glob("*.vtu"))
            else:
                log.warning(f"Failed to convert {frd_file}: {result.error}")

    if not vtu_files:
        raise FileNotFoundError(
            f"没有可视化文件 (.vtu/.vtk) 在目录: {root_dir}\n"
            "请先运行 'cae solve' 或使用 'cae convert' 转换 .frd 文件。"
        )

    # Deduplicate
    vtu_files = list(set(vtu_files))

    server = ViewServer(root_dir, port)

    if open_browser:
        import webbrowser
        webbrowser.open(server.url)

    return server, server.url, vtu_files
