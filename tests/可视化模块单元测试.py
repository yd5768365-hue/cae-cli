"""
可视化模块单元测试
覆盖 pyvista_renderer 和 report，PyVista 调用全部 mock 隔离。
"""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from cae.viewer.pyvista_renderer import (
    RenderResult,
    MeshInfo,
    _find_field,
    _von_mises_from_tensor,
    get_mesh_info,
)
from cae.viewer.report import (
    ReportConfig,
    ReportSection,
    generate_report,
    build_report_from_renders,
    _img_to_base64,
)


# ================================================================== #
# 工具函数
# ================================================================== #

class TestFindField:
    def _mock_mesh(self, keys: list[str]):
        m = MagicMock()
        m.point_data.keys.return_value = keys
        # make 'in' work for point_data
        m.point_data.__contains__ = lambda self, k: k in keys
        # allow indexing
        data = {k: np.zeros((4, 3)) for k in keys}
        m.point_data.__getitem__ = lambda self, k: data[k]
        return m

    def test_finds_disp(self):
        m = self._mock_mesh(["DISP_step1", "STRESS_step1"])
        assert _find_field(m, ["DISP", "U"]) == "DISP_step1"

    def test_finds_vonmises(self):
        m = self._mock_mesh(["VonMises_step1", "DISP_step1"])
        assert _find_field(m, ["VonMises"]) == "VonMises_step1"

    def test_case_insensitive(self):
        m = self._mock_mesh(["vonmises_step1"])
        assert _find_field(m, ["VONMISES"]) == "vonmises_step1"

    def test_returns_first_when_no_match(self):
        m = self._mock_mesh(["SomeField"])
        assert _find_field(m, ["NOTEXIST"]) == "SomeField"

    def test_returns_none_when_empty(self):
        m = self._mock_mesh([])
        assert _find_field(m, ["DISP"]) is None


class TestVonMisesFromTensor:
    def test_uniaxial(self):
        s = np.array([[100.0, 0, 0, 0, 0, 0]])
        assert pytest.approx(_von_mises_from_tensor(s)[0], abs=1e-4) == 100.0

    def test_hydrostatic_zero(self):
        s = np.array([[50.0, 50.0, 50.0, 0, 0, 0]])
        assert pytest.approx(_von_mises_from_tensor(s)[0], abs=1e-6) == 0.0

    def test_pure_shear(self):
        tau = 100.0
        s = np.array([[0, 0, 0, tau, 0, 0]])
        assert pytest.approx(_von_mises_from_tensor(s)[0], rel=1e-5) == tau * np.sqrt(3)

    def test_batch_shape(self):
        s = np.random.rand(20, 6) * 200
        vm = _von_mises_from_tensor(s)
        assert vm.shape == (20,)
        assert np.all(vm >= 0)


class TestGetMeshInfo:
    def _make_mesh(self, n_pts=100, n_cells=50, fields=None):
        m = MagicMock()
        m.n_points = n_pts
        m.n_cells  = n_cells
        m.bounds   = (0, 100, 0, 20, 0, 20)
        keys = fields or ["DISP_step1", "VonMises_step1"]
        m.point_data.keys.return_value = keys
        m.cell_data.keys.return_value  = []
        return m

    def test_basic_counts(self):
        info = get_mesh_info(self._make_mesh(n_pts=80, n_cells=30))
        assert info.n_points == 80
        assert info.n_cells  == 30

    def test_has_displacement_detected(self):
        info = get_mesh_info(self._make_mesh(fields=["DISP_step1"]))
        assert info.has_displacement is True

    def test_has_stress_detected(self):
        info = get_mesh_info(self._make_mesh(fields=["VonMises_step1"]))
        assert info.has_stress is True

    def test_scalar_fields_listed(self):
        info = get_mesh_info(self._make_mesh(fields=["A", "B"]))
        assert "A" in info.scalar_fields
        assert "B" in info.scalar_fields


# ================================================================== #
# RenderResult
# ================================================================== #

class TestRenderResult:
    def test_first_returns_first_file(self, tmp_path: Path):
        f1 = tmp_path / "a.png"
        f2 = tmp_path / "b.png"
        r = RenderResult(success=True, files=[f1, f2])
        assert r.first() == f1

    def test_first_none_when_empty(self):
        r = RenderResult(success=False)
        assert r.first() is None


# ================================================================== #
# render_displacement / render_von_mises / render_slice （mock pyvista）
# ================================================================== #

def _make_mock_pyvista(n_pts=8, fields=None):
    """构造 mock PyVista mesh，模拟 load_result 的返回值。"""
    if fields is None:
        fields = {
            "DISP_step1":     np.random.rand(n_pts, 3) * 0.01,
            "VonMises_step1": np.random.rand(n_pts) * 300,
        }
    m = MagicMock()
    m.n_points = n_pts
    m.n_cells  = 4
    m.bounds   = (0.0, 100.0, 0.0, 20.0, 0.0, 20.0)
    m.point_data.keys.return_value = list(fields.keys())
    m.point_data.__getitem__ = lambda self, k: fields[k]
    m.point_data.__contains__ = lambda self, k: k in fields
    m.copy.return_value = m
    return m


class TestRenderDisplacement:
    def test_missing_file(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_displacement
        r = render_displacement(tmp_path / "no.vtu", tmp_path / "out.png")
        assert r.success is False

    def test_success_path(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_displacement
        vtu = tmp_path / "job.vtu"; vtu.write_text("")
        mock_mesh = _make_mock_pyvista()
        mock_plotter = MagicMock()

        with (
            patch("cae.viewer.pyvista_renderer.load_result", return_value=mock_mesh),
            patch("cae.viewer.pyvista_renderer.pv.Plotter", return_value=mock_plotter),
        ):
            r = render_displacement(vtu, tmp_path / "disp.png")

        assert r.success is True
        assert r.first() == tmp_path / "disp.png"
        mock_plotter.screenshot.assert_called_once()

    def test_no_disp_field(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_displacement
        vtu = tmp_path / "job.vtu"; vtu.write_text("")
        mock_mesh = _make_mock_pyvista(fields={"STRESS": np.zeros((8, 6))})

        with patch("cae.viewer.pyvista_renderer.load_result", return_value=mock_mesh):
            r = render_displacement(vtu, tmp_path / "disp.png")

        assert r.success is False
        assert "位移" in (r.error or "")


class TestRenderVonMises:
    def test_missing_file(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_von_mises
        r = render_von_mises(tmp_path / "no.vtu", tmp_path / "out.png")
        assert r.success is False

    def test_success_path(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_von_mises
        vtu = tmp_path / "job.vtu"; vtu.write_text("")
        mock_mesh = _make_mock_pyvista()
        mock_plotter = MagicMock()

        with (
            patch("cae.viewer.pyvista_renderer.load_result", return_value=mock_mesh),
            patch("cae.viewer.pyvista_renderer.pv.Plotter", return_value=mock_plotter),
        ):
            r = render_von_mises(vtu, tmp_path / "vm.png")

        assert r.success is True
        mock_plotter.screenshot.assert_called_once()

    def test_computes_vm_from_stress_tensor(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_von_mises
        vtu = tmp_path / "job.vtu"; vtu.write_text("")
        # 6分量应力字段，没有现成的 VonMises 字段
        stress_data = np.random.rand(8, 6) * 200
        mock_mesh = _make_mock_pyvista(fields={"STRESS_step1": stress_data})
        mock_plotter = MagicMock()

        with (
            patch("cae.viewer.pyvista_renderer.load_result", return_value=mock_mesh),
            patch("cae.viewer.pyvista_renderer.pv.Plotter", return_value=mock_plotter),
        ):
            r = render_von_mises(vtu, tmp_path / "vm.png")

        assert r.success is True


class TestRenderSlice:
    def test_success_path(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_slice
        vtu = tmp_path / "job.vtu"; vtu.write_text("")
        mock_mesh = _make_mock_pyvista()

        sliced = MagicMock()
        sliced.n_points = 20
        sliced.point_data.keys.return_value = ["VonMises_step1"]
        sliced.point_data.__contains__ = lambda self, k: k == "VonMises_step1"
        mock_mesh.slice.return_value = sliced
        mock_plotter = MagicMock()

        with (
            patch("cae.viewer.pyvista_renderer.load_result", return_value=mock_mesh),
            patch("cae.viewer.pyvista_renderer.pv.Plotter", return_value=mock_plotter),
        ):
            r = render_slice(vtu, tmp_path / "slice.png", normal="z")

        assert r.success is True

    def test_empty_slice_returns_error(self, tmp_path: Path):
        from cae.viewer.pyvista_renderer import render_slice
        vtu = tmp_path / "job.vtu"; vtu.write_text("")
        mock_mesh = _make_mock_pyvista()
        sliced = MagicMock(); sliced.n_points = 0
        mock_mesh.slice.return_value = sliced

        with patch("cae.viewer.pyvista_renderer.load_result", return_value=mock_mesh):
            r = render_slice(vtu, tmp_path / "slice.png")

        assert r.success is False
        assert "空" in (r.error or "")


# ================================================================== #
# report
# ================================================================== #

class TestGenerateReport:
    def test_creates_html_file(self, tmp_path: Path):
        config = ReportConfig(title="测试报告", job_name="bracket", sections=[])
        out = tmp_path / "report.html"
        result = generate_report(config, out)
        assert result == out
        assert out.exists()
        html = out.read_text(encoding="utf-8")
        assert "测试报告" in html
        assert "bracket" in html

    def test_image_embedded_as_base64(self, tmp_path: Path):
        img = tmp_path / "disp.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        section = ReportSection(
            title="变形云图",
            image_path=img,
            caption="测试图像",
        )
        config = ReportConfig(sections=[section])
        out = tmp_path / "report.html"
        generate_report(config, out)
        html = out.read_text(encoding="utf-8")
        assert "data:image/png;base64," in html

    def test_data_table_rendered(self, tmp_path: Path):
        section = ReportSection(
            title="摘要",
            data_table={"节点数": "1000", "求解器": "CalculiX"},
        )
        config = ReportConfig(sections=[section])
        out = tmp_path / "report.html"
        generate_report(config, out)
        html = out.read_text(encoding="utf-8")
        assert "节点数" in html
        assert "CalculiX" in html

    def test_stat_cards_populated(self, tmp_path: Path):
        config = ReportConfig(
            node_count=1500,
            element_count=800,
            solve_time="3.2s",
        )
        out = tmp_path / "report.html"
        generate_report(config, out)
        html = out.read_text(encoding="utf-8")
        assert "1,500" in html
        assert "800" in html
        assert "3.2s" in html

    def test_output_dir_created(self, tmp_path: Path):
        config = ReportConfig()
        out = tmp_path / "nested" / "deep" / "report.html"
        generate_report(config, out)
        assert out.exists()


class TestImgToBase64:
    def test_roundtrip(self, tmp_path: Path):
        img = tmp_path / "test.png"
        original = b"\x89PNG test bytes"
        img.write_bytes(original)
        b64 = _img_to_base64(img)
        decoded = base64.b64decode(b64)
        assert decoded == original


class TestBuildReportFromRenders:
    def test_creates_report_html(self, tmp_path: Path):
        renders = {
            "displacement": RenderResult(success=False, error="no field"),
            "von_mises":    RenderResult(success=False, error="no field"),
        }
        report = build_report_from_renders(renders, tmp_path, job_name="test")
        assert report.name == "report.html"
        assert report.exists()

    def test_successful_renders_embedded(self, tmp_path: Path):
        img = tmp_path / "disp.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        renders = {
            "displacement": RenderResult(success=True, files=[img]),
            "von_mises":    RenderResult(success=False, error="missing"),
        }
        report = build_report_from_renders(renders, tmp_path)
        html = report.read_text(encoding="utf-8")
        assert "data:image/png;base64," in html

    def test_mesh_info_included(self, tmp_path: Path):
        info = MeshInfo(n_points=250, n_cells=120, bounds=(0,1,0,1,0,1))
        renders = {}
        report = build_report_from_renders(renders, tmp_path, mesh_info=info)
        html = report.read_text(encoding="utf-8")
        assert "250" in html
        assert "120" in html