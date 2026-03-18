"""
第三周：mesh 模块单元测试
覆盖 gmsh_runner（含 mock gmsh）和 converter（含 mock meshio）。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
import numpy as np

import pytest

from cae.mesh.gmsh_runner import (
    MeshQuality,
    MeshResult,
    check_gmsh,
    get_gmsh_version,
    mesh_geometry,
    SUPPORTED_GEO_FORMATS,
)
from cae.mesh.converter import (
    ConvertResult,
    convert_mesh,
    msh_to_inp,
    inp_to_vtu,
    detect_format,
    READABLE_FORMATS,
    WRITABLE_FORMATS,
)


# ================================================================== #
# MeshQuality enum
# ================================================================== #

class TestMeshQuality:
    def test_lc_factor_order(self):
        assert MeshQuality.FINE.lc_factor < MeshQuality.MEDIUM.lc_factor
        assert MeshQuality.MEDIUM.lc_factor < MeshQuality.COARSE.lc_factor

    def test_values(self):
        assert MeshQuality("coarse") == MeshQuality.COARSE
        assert MeshQuality("fine")   == MeshQuality.FINE

    def test_label_cn(self):
        assert "粗" in MeshQuality.COARSE.label_cn
        assert "精" in MeshQuality.FINE.label_cn

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            MeshQuality("ultra")


# ================================================================== #
# check_gmsh / get_gmsh_version
# ================================================================== #

class TestGmshAvailability:
    def test_check_gmsh_true_when_importable(self):
        with patch.dict("sys.modules", {"gmsh": MagicMock(__version__="4.12.0")}):
            assert check_gmsh() is True

    def test_check_gmsh_false_when_missing(self):
        with patch.dict("sys.modules", {"gmsh": None}):
            # ImportError path
            with patch("builtins.__import__", side_effect=ImportError):
                assert check_gmsh() is False

    def test_version_returned(self):
        mock_gmsh = MagicMock()
        mock_gmsh.__version__ = "4.12.0"
        with patch.dict("sys.modules", {"gmsh": mock_gmsh}):
            v = get_gmsh_version()
            assert v == "4.12.0"

    def test_version_none_when_missing(self):
        with patch("cae.mesh.gmsh_runner.get_gmsh_version", return_value=None) as mock_fn:
            result = mock_fn()
            assert result is None


# ================================================================== #
# MeshResult helpers
# ================================================================== #

class TestMeshResult:
    def test_duration_str_seconds(self):
        r = MeshResult(success=True, duration_seconds=4.7)
        assert r.duration_str == "4.7s"

    def test_duration_str_minutes(self):
        r = MeshResult(success=True, duration_seconds=90.0)
        assert r.duration_str == "1m 30s"

    def test_defaults(self):
        r = MeshResult(success=False)
        assert r.mesh_file is None
        assert r.inp_file is None
        assert r.warnings == []


# ================================================================== #
# mesh_geometry (mock gmsh)
# ================================================================== #

class TestMeshGeometry:
    def _make_mock_gmsh(self, node_count=100, elem_count=50):
        g = MagicMock()
        # getNodes returns (node_tags, coords, param)
        g.model.mesh.getNodes.return_value = (list(range(1, node_count + 1)), [], [])
        # getEntities returns list of (dim, tag)
        g.model.getEntities.return_value = [(3, 1)]
        # getElements returns (types, tags_list, node_tags_list)
        g.model.mesh.getElements.return_value = (
            [4],                          # C3D4 type
            [list(range(1, elem_count + 1))],
            [[]],
        )
        # getBoundingBox returns (xmin,ymin,zmin,xmax,ymax,zmax)
        g.model.getBoundingBox.return_value = (0, 0, 0, 100, 20, 20)
        return g

    def test_missing_file_returns_error(self, tmp_path: Path):
        with patch.dict("sys.modules", {"gmsh": MagicMock()}):
            r = mesh_geometry(tmp_path / "no.step", tmp_path)
        assert r.success is False
        assert "不存在" in (r.error or "")

    def test_unsupported_format_returns_error(self, tmp_path: Path):
        f = tmp_path / "model.xyz"
        f.write_text("")
        with patch.dict("sys.modules", {"gmsh": MagicMock()}):
            r = mesh_geometry(f, tmp_path)
        assert r.success is False
        assert "不支持" in (r.error or "")

    def test_gmsh_missing_returns_error(self, tmp_path: Path):
        f = tmp_path / "model.step"
        f.write_text("")
        with patch("cae.mesh.gmsh_runner.check_gmsh", return_value=False):
            with patch("builtins.__import__", side_effect=ImportError("no gmsh")):
                r = mesh_geometry(f, tmp_path)
        assert r.success is False
        assert "gmsh" in (r.error or "").lower()

    def test_successful_mesh(self, tmp_path: Path):
        f = tmp_path / "model.step"
        f.write_text("")

        mock_gmsh = self._make_mock_gmsh(node_count=120, elem_count=60)

        with patch.dict("sys.modules", {"gmsh": mock_gmsh}):
            r = mesh_geometry(f, tmp_path, quality=MeshQuality.MEDIUM)

        assert r.success is True
        assert r.node_count == 120
        assert r.element_count == 60
        assert r.quality == MeshQuality.MEDIUM

    def test_gmsh_exception_returns_error(self, tmp_path: Path):
        f = tmp_path / "model.step"
        f.write_text("")

        mock_gmsh = MagicMock()
        mock_gmsh.model.occ.importShapes.side_effect = RuntimeError("bad geometry")

        with patch.dict("sys.modules", {"gmsh": mock_gmsh}):
            r = mesh_geometry(f, tmp_path)

        assert r.success is False
        assert "网格划分失败" in (r.error or "")

    def test_output_dir_created(self, tmp_path: Path):
        f = tmp_path / "model.step"
        f.write_text("")
        out = tmp_path / "deep" / "nested"

        mock_gmsh = self._make_mock_gmsh()
        with patch.dict("sys.modules", {"gmsh": mock_gmsh}):
            mesh_geometry(f, out)

        assert out.exists()

    def test_geo_file_uses_merge(self, tmp_path: Path):
        """Gmsh .geo script 走 gmsh.merge 路径而不是 occ.importShapes。"""
        f = tmp_path / "model.geo"
        f.write_text("Point(1) = {0,0,0,1};")

        mock_gmsh = self._make_mock_gmsh()
        with patch.dict("sys.modules", {"gmsh": mock_gmsh}):
            mesh_geometry(f, tmp_path)

        mock_gmsh.merge.assert_called_once()
        mock_gmsh.model.occ.importShapes.assert_not_called()


# ================================================================== #
# converter
# ================================================================== #

class TestDetectFormat:
    def test_known_formats(self):
        assert detect_format(Path("model.msh")) == "gmsh"
        assert detect_format(Path("model.inp")) == "abaqus"
        assert detect_format(Path("model.vtu")) == "vtu"

    def test_unknown_format(self):
        assert detect_format(Path("model.abc")) is None


class TestConvertMesh:
    def _mock_mesh(self, n_nodes=8, n_cells=1):
        import meshio
        points = np.zeros((n_nodes, 3))
        cells = [meshio.CellBlock("hexahedron", np.zeros((n_cells, 8), dtype=int))]
        return meshio.Mesh(points=points, cells=cells)

    def test_missing_source_returns_error(self, tmp_path: Path):
        r = convert_mesh(tmp_path / "no.msh", tmp_path / "out.inp")
        assert r.success is False
        assert "不存在" in (r.error or "")

    def test_unreadable_format_returns_error(self, tmp_path: Path):
        f = tmp_path / "model.xyz"
        f.write_text("")
        r = convert_mesh(f, tmp_path / "out.inp")
        assert r.success is False
        assert "不支持读取" in (r.error or "")

    def test_unwritable_format_returns_error(self, tmp_path: Path):
        f = tmp_path / "model.msh"
        f.write_text("")
        r = convert_mesh(f, tmp_path / "out.abc")
        assert r.success is False
        assert "不支持写出" in (r.error or "")

    def test_successful_conversion(self, tmp_path: Path):
        src = tmp_path / "model.msh"
        src.write_text("")
        dst = tmp_path / "model.inp"

        mock_mesh = self._mock_mesh(n_nodes=8, n_cells=2)
        mock_meshio = MagicMock()
        mock_meshio.read.return_value = mock_mesh

        with (
            patch("cae.mesh.converter._meshio", mock_meshio),
            patch("cae.mesh.converter._remove_orphaned_nodes", side_effect=lambda m: m),
        ):
            r = convert_mesh(src, dst)

        assert r.success is True
        assert r.output_file == dst
        assert r.node_count == 8
        assert r.element_count == 2

    def test_output_dir_created(self, tmp_path: Path):
        src = tmp_path / "model.msh"
        src.write_text("")
        dst = tmp_path / "sub" / "out.inp"

        mock_mesh = self._mock_mesh()
        mock_meshio = MagicMock()
        mock_meshio.read.return_value = mock_mesh

        with patch("cae.mesh.converter._meshio", mock_meshio):
            convert_mesh(src, dst)

        assert dst.parent.exists()

    def test_meshio_exception_returns_error(self, tmp_path: Path):
        src = tmp_path / "model.msh"
        src.write_text("")

        mock_meshio = MagicMock()
        mock_meshio.read.side_effect = Exception("corrupt file")

        with patch("cae.mesh.converter._meshio", mock_meshio):
            r = convert_mesh(src, tmp_path / "out.inp")

        assert r.success is False
        assert "corrupt file" in (r.error or "")

    def test_format_metadata_recorded(self, tmp_path: Path):
        src = tmp_path / "model.msh"
        src.write_text("")
        dst = tmp_path / "out.vtu"

        mock_mesh = self._mock_mesh()
        mock_meshio = MagicMock()
        mock_meshio.read.return_value = mock_mesh

        with patch("cae.mesh.converter._meshio", mock_meshio):
            r = convert_mesh(src, dst)

        assert r.source_format == ".msh"
        assert r.target_format == ".vtu"


class TestShortcuts:
    def _mock_mesh(self):
        import meshio
        return meshio.Mesh(
            points=np.zeros((4, 3)),
            cells=[meshio.CellBlock("tetra", np.zeros((1, 4), dtype=int))],
        )

    def test_msh_to_inp(self, tmp_path: Path):
        src = tmp_path / "job.msh"
        src.write_text("")
        mock_meshio = MagicMock()
        mock_meshio.read.return_value = self._mock_mesh()
        with patch("cae.mesh.converter._meshio", mock_meshio):
            r = msh_to_inp(src, tmp_path)
        assert r.success is True
        assert r.output_file == tmp_path / "job.inp"

    def test_inp_to_vtu(self, tmp_path: Path):
        src = tmp_path / "job.inp"
        src.write_text("")
        mock_meshio = MagicMock()
        mock_meshio.read.return_value = self._mock_mesh()
        with patch("cae.mesh.converter._meshio", mock_meshio):
            r = inp_to_vtu(src, tmp_path)
        assert r.success is True
        assert r.output_file == tmp_path / "job.vtu"

    def test_msh_to_inp_default_dir(self, tmp_path: Path):
        src = tmp_path / "job.msh"
        src.write_text("")
        mock_meshio = MagicMock()
        mock_meshio.read.return_value = self._mock_mesh()
        with patch("cae.mesh.converter._meshio", mock_meshio):
            r = msh_to_inp(src)
        assert r.output_file == tmp_path / "job.inp"


class TestOrphanedNodeRemoval:
    def test_removes_orphaned(self):
        """孤立节点（未被任何单元引用）应该被删除。"""
        import meshio
        # 节点 0..7 存在，但单元只引用 0..3
        points = np.zeros((8, 3))
        cells = [meshio.CellBlock("tetra", np.array([[0, 1, 2, 3]]))]
        mesh = meshio.Mesh(points=points, cells=cells)

        from cae.mesh.converter import _remove_orphaned_nodes
        cleaned = _remove_orphaned_nodes(mesh)

        assert len(cleaned.points) == 4   # 只剩4个被引用的节点

    def test_no_change_when_all_used(self):
        import meshio
        points = np.zeros((4, 3))
        cells = [meshio.CellBlock("tetra", np.array([[0, 1, 2, 3]]))]
        mesh = meshio.Mesh(points=points, cells=cells)

        from cae.mesh.converter import _remove_orphaned_nodes
        cleaned = _remove_orphaned_nodes(mesh)
        assert len(cleaned.points) == 4