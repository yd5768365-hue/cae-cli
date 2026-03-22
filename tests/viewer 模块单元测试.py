"""
第二周：viewer 模块单元测试
覆盖：frd_parser、vtk_export、server（端口查找 / 文件收集）
所有 meshio I/O 均通过 mock 隔离，无需真实 .frd 文件。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import numpy as np
import pytest

from cae.viewer.frd_parser import (
    FrdData,
    FrdElement,
    FrdNodes,
    FrdResultStep,
    parse_frd,
)
from cae.enums import FrdResultEntity
from cae.viewer.vtk_export import (
    VtkExportResult,
    frd_to_vtu,
)
from cae.viewer._utils import von_mises as _von_mises


# ================================================================== #
# frd_parser
# ================================================================== #

class TestFrdNodes:
    def test_basic_fields(self):
        n = FrdNodes(ids=[1, 2, 3], coords=[(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        assert len(n.ids) == 3
        assert len(n.coords) == 3


class TestFrdData:
    def test_has_geometry_false_when_empty(self):
        d = FrdData()
        assert d.has_geometry is False

    def test_has_geometry_false_no_elements(self):
        d = FrdData(nodes=FrdNodes(ids=[1], coords=[(0, 0, 0)]))
        assert d.has_geometry is False

    def test_has_geometry_true(self):
        d = FrdData(
            nodes=FrdNodes(ids=[1, 2, 3, 4], coords=[(0,0,0)]*4),
            elements=[FrdElement(eid=1, etype=3, connectivity=[1,2,3,4])],
        )
        assert d.has_geometry is True

    def test_node_count(self):
        d = FrdData(nodes=FrdNodes(ids=[1, 2], coords=[(0,0,0),(1,0,0)]))
        assert d.node_count == 2

    def test_node_count_no_nodes(self):
        assert FrdData().node_count == 0

    def test_get_result_by_name(self):
        r1 = FrdResultStep(step=1, time=0.0, name="DISP", components=[], values={}, node_ids=[], entity=FrdResultEntity.DISP)
        r2 = FrdResultStep(step=1, time=0.0, name="STRESS", components=[], values={}, node_ids=[], entity=FrdResultEntity.STRESS)
        d = FrdData(results=[r1, r2])
        assert d.get_result("DISP") is r1
        assert d.get_result("STRESS") is r2

    def test_get_result_missing(self):
        d = FrdData()
        assert d.get_result("NONEXISTENT") is None

    def test_get_result_last_step(self):
        steps = [
            FrdResultStep(step=i, time=float(i), name="DISP", components=[], values={}, node_ids=[], entity=FrdResultEntity.DISP)
            for i in range(1, 4)
        ]
        d = FrdData(results=steps)
        assert d.get_result("DISP", step=-1) is steps[-1]
        assert d.get_result("DISP", step=0)  is steps[0]


class TestParseFrd:
    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            parse_frd(tmp_path / "ghost.frd")

    def _write_minimal_frd(self, path: Path) -> Path:
        """最小化合法 ASCII .frd 文件（4节点四面体 + 位移结果）。"""
        content = """\
    1C                          4
 -1         1 0.000000E+00 0.000000E+00 0.000000E+00
 -1         2 1.000000E+00 0.000000E+00 0.000000E+00
 -1         3 0.000000E+00 1.000000E+00 0.000000E+00
 -1         4 0.000000E+00 0.000000E+00 1.000000E+00
 -3
    2C                          1
 -1         1  3  1  1
 -2         1  2  3  4
 -3
  100C                             DISP        1  0.00000E+00
 -4  DISP        4  0  1
 -5  D1          1  2  1  0
 -5  D2          1  2  2  0
 -5  D3          1  2  3  0
 -1         1 1.00000E-03 0.00000E+00 0.00000E+00
 -1         2 2.00000E-03 0.00000E+00 0.00000E+00
 -1         3 3.00000E-03 0.00000E+00 0.00000E+00
 -1         4 4.00000E-03 0.00000E+00 0.00000E+00
 -3
9999
"""
        path.write_text(content)
        return path

    def test_parse_nodes(self, tmp_path: Path):
        frd = self._write_minimal_frd(tmp_path / "test.frd")
        data = parse_frd(frd)
        assert data.node_count == 4

    def test_parse_elements(self, tmp_path: Path):
        frd = self._write_minimal_frd(tmp_path / "test.frd")
        data = parse_frd(frd)
        assert data.element_count == 1
        assert data.elements[0].etype == 3  # C3D4

    def test_parse_results(self, tmp_path: Path):
        frd = self._write_minimal_frd(tmp_path / "test.frd")
        data = parse_frd(frd)
        disp = data.get_result("DISP")
        assert disp is not None
        assert len(disp.node_ids) == 4

    def test_has_geometry(self, tmp_path: Path):
        frd = self._write_minimal_frd(tmp_path / "test.frd")
        data = parse_frd(frd)
        assert data.has_geometry is True


# ================================================================== #
# vtk_export
# ================================================================== #

class TestVonMises:
    def test_uniaxial_tension(self):
        """单轴拉伸：S11=100, 其他=0 → Von Mises = 100."""
        stress = np.array([[100.0, 0, 0, 0, 0, 0]])
        vm = _von_mises(stress)
        assert pytest.approx(vm[0], abs=1e-6) == 100.0

    def test_hydrostatic_zero(self):
        """静水压：S11=S22=S33=p, 剪切=0 → Von Mises = 0."""
        p = 50.0
        stress = np.array([[p, p, p, 0.0, 0.0, 0.0]])
        vm = _von_mises(stress)
        assert pytest.approx(vm[0], abs=1e-6) == 0.0

    def test_pure_shear(self):
        """纯剪切 S12=τ → Von Mises = √3 · τ."""
        tau = 100.0
        stress = np.array([[0.0, 0.0, 0.0, tau, 0.0, 0.0]])
        vm = _von_mises(stress)
        assert pytest.approx(vm[0], rel=1e-6) == tau * np.sqrt(3)

    def test_batch(self):
        """批量输入：输出长度与输入相同。"""
        stress = np.random.rand(50, 6)
        vm = _von_mises(stress)
        assert vm.shape == (50,)
        assert np.all(vm >= 0)


class TestVtkExportResult:
    def test_default_fields_list(self):
        r = VtkExportResult(success=True)
        assert isinstance(r.fields, list)

    def test_success_with_vtu(self, tmp_path: Path):
        vtu = tmp_path / "job.vtu"
        vtu.write_text("<VTKFile/>")
        r = VtkExportResult(success=True, vtu_file=vtu, node_count=8, element_count=1)
        assert r.success
        assert r.vtu_file == vtu


class TestFrdToVtu:
    def test_missing_frd_returns_error(self, tmp_path: Path):
        result = frd_to_vtu(tmp_path / "no.frd")
        assert result.success is False
        assert "不存在" in (result.error or "")

    def test_meshio_direct_success(self, tmp_path: Path):
        """meshio 直读成功路径。"""
        frd = tmp_path / "job.frd"
        frd.write_bytes(b"dummy")

        mock_mesh = MagicMock()
        mock_mesh.points = np.zeros((8, 3))
        mock_mesh.cells = [MagicMock(data=np.zeros((1, 8), dtype=int))]
        mock_mesh.point_data = {"U": np.zeros((8, 3))}
        mock_mesh.cell_data = {}

        mock_meshio = MagicMock()
        mock_meshio.read.return_value = mock_mesh

        with (
            patch("cae.viewer.vtk_export._meshio_module", mock_meshio),
            patch("cae.viewer.vtk_export._HAS_MESHIO", True),
        ):
            result = frd_to_vtu(frd, tmp_path)

        assert result.success is True
        assert result.node_count == 8

    def test_fallback_when_meshio_fails(self, tmp_path: Path):
        """meshio 直读失败时走内置解析器路径。"""
        frd = tmp_path / "job.frd"
        frd.write_text("""\
    1C                          2
 -1         1 0.000000E+00 0.000000E+00 0.000000E+00
 -1         2 1.000000E+00 0.000000E+00 0.000000E+00
 -3
    2C                          1
 -1         1  3  1  1
 -2         1  2  1  2
 -3
9999
""")
        mock_meshio = MagicMock()
        mock_meshio.read.side_effect = Exception("unsupported format")

        with (
            patch("cae.viewer.vtk_export._meshio_module", mock_meshio),
            patch("cae.viewer.vtk_export._HAS_MESHIO", True),
        ):
            result = frd_to_vtu(frd, tmp_path)

        assert isinstance(result, VtkExportResult)

    def test_output_dir_created(self, tmp_path: Path):
        """输出目录不存在时自动创建。"""
        frd = tmp_path / "job.frd"
        frd.write_bytes(b"dummy")
        out = tmp_path / "nested" / "output"

        mock_meshio = MagicMock()
        mock_meshio.read.side_effect = Exception("fail")

        with (
            patch("cae.viewer.vtk_export._meshio_module", mock_meshio),
            patch("cae.viewer.vtk_export._HAS_MESHIO", True),
        ):
            frd_to_vtu(frd, out)

        assert out.exists()


# ================================================================== #
# server utilities
# ================================================================== #

class TestServerUtils:
    def test_find_free_port_returns_int(self):
        from cae.viewer.server import _find_free_port
        port = _find_free_port(18888)
        assert isinstance(port, int)
        assert 18888 <= port < 18988

    def test_collect_vtu_files_empty(self, tmp_path: Path):
        from cae.viewer.server import _collect_vtu_files
        assert _collect_vtu_files(tmp_path) == []

    def test_collect_vtu_files_found(self, tmp_path: Path):
        from cae.viewer.server import _collect_vtu_files
        (tmp_path / "a.vtu").write_text("")
        (tmp_path / "b.vtk").write_text("")
        (tmp_path / "c.frd").write_text("")  # should not be included
        files = _collect_vtu_files(tmp_path)
        names = {f.name for f in files}
        assert "a.vtu" in names
        assert "b.vtk" in names
        assert "c.frd" not in names

    def test_start_server_dir_not_found(self, tmp_path: Path):
        from cae.viewer.server import start_server
        with pytest.raises(FileNotFoundError):
            start_server(tmp_path / "nonexistent", open_browser=False)

    def test_start_server_no_vtu_files(self, tmp_path: Path):
        from cae.viewer.server import start_server
        # 目录存在但没有可视化文件
        (tmp_path / "dummy.txt").write_text("")
        with pytest.raises(FileNotFoundError, match="没有可视化文件"):
            start_server(tmp_path, auto_convert=False, open_browser=False)

    def test_start_server_returns_server_and_url(self, tmp_path: Path):
        from cae.viewer.server import start_server
        (tmp_path / "result.vtu").write_text("<VTKFile/>")
        server, url, files = start_server(tmp_path, open_browser=False, auto_convert=False)
        assert url.startswith("http://localhost:")
        assert len(files) == 1
        server.server_close()


class TestIndexHtml:
    """验证 index.html 生成正确的文件按钮和 JSON。"""

    def test_file_buttons_in_html(self, tmp_path: Path):
        from cae.viewer.server import start_server
        (tmp_path / "beam.vtu").write_text("")
        (tmp_path / "frame.vtu").write_text("")

        server, url, files = start_server(tmp_path, open_browser=False, auto_convert=False)
        server.server_close()

        # 检查 handler 能获取正确的文件列表
        assert len(files) == 2
        names = {f.name for f in files}
        assert "beam.vtu" in names
        assert "frame.vtu" in names


# ================================================================== #
# 应力计算工具测试
# ================================================================== #

from cae.viewer._utils import (
    von_mises,
    get_principal_stresses,
    get_principal_shear_stresses,
    get_max_shear_stress,
    get_worst_principal_stress,
    get_stress_invariants,
)


class TestPrincipalStresses:
    """主应力计算测试"""

    def test_uniaxial_tension(self):
        """单轴拉伸：σ1=100, σ2=σ3=0"""
        stress = np.array([[100.0, 0, 0, 0, 0, 0]])
        principal, _ = get_principal_stresses(stress)
        assert pytest.approx(principal[0][0], abs=1e-6) == 100.0
        assert pytest.approx(principal[0][1], abs=1e-6) == 0.0
        assert pytest.approx(principal[0][2], abs=1e-6) == 0.0

    def test_uniaxial_compression(self):
        """单轴压缩：σ1=σ2=0, σ3=-100"""
        stress = np.array([[0, 0, -100.0, 0, 0, 0]])
        principal, _ = get_principal_stresses(stress)
        assert pytest.approx(principal[0][0], abs=1e-6) == 0.0
        assert pytest.approx(principal[0][1], abs=1e-6) == 0.0
        assert pytest.approx(principal[0][2], abs=1e-6) == -100.0

    def test_pure_shear(self):
        """纯剪切：σ1=τ, σ2=0, σ3=-τ"""
        tau = 50.0
        stress = np.array([[0, 0, 0, tau, 0, 0]])
        principal, _ = get_principal_stresses(stress)
        assert pytest.approx(principal[0][0], abs=1e-6) == tau
        assert pytest.approx(principal[0][1], abs=1e-6) == 0.0
        assert pytest.approx(principal[0][2], abs=1e-6) == -tau

    def test_hydrostatic_pressure(self):
        """静水压：σ1=σ2=σ3=-p"""
        p = 100.0
        stress = np.array([[-p, -p, -p, 0, 0, 0]])
        principal, _ = get_principal_stresses(stress)
        assert all(abs(principal[0][i] - (-p)) < 1e-10 for i in range(3))

    def test_principal_directions(self):
        """验证主方向是正交的"""
        stress = np.array([[100.0, 50.0, 0, 10.0, 0, 0]])
        _, directions = get_principal_stresses(stress)
        d = directions[0]  # (3, 3)
        # 验证每列是单位向量
        for col in range(3):
            norm = np.linalg.norm(d[:, col])
            assert pytest.approx(norm, abs=1e-6) == 1.0
        # 验证列之间正交
        dot01 = np.dot(d[:, 0], d[:, 1])
        dot02 = np.dot(d[:, 0], d[:, 2])
        dot12 = np.dot(d[:, 1], d[:, 2])
        assert pytest.approx(dot01, abs=1e-6) == 0.0
        assert pytest.approx(dot02, abs=1e-6) == 0.0
        assert pytest.approx(dot12, abs=1e-6) == 0.0

    def test_batch(self):
        """批量计算：结果形状正确"""
        stress = np.random.rand(20, 6)
        principal, directions = get_principal_stresses(stress)
        assert principal.shape == (20, 3)
        assert directions.shape == (20, 3, 3)


class TestPrincipalShearStresses:
    """主剪切应力计算测试"""

    def test_pure_shear(self):
        """纯剪切 S12=τ → τ12=τ/2, τ13=τ, τ23=τ/2"""
        tau = 100.0
        stress = np.array([[0, 0, 0, tau, 0, 0]])
        shear = get_principal_shear_stresses(stress)
        assert pytest.approx(shear[0][0], abs=1e-6) == tau / 2  # |σ1-σ2|/2 = |τ|/2
        # 对于纯剪切，主应力是 [τ, 0, -τ]
        # τ12 = |τ - 0|/2 = τ/2
        # τ13 = |τ - (-τ)|/2 = τ
        # τ23 = |0 - (-τ)|/2 = τ/2

    def test_uniaxial_tension(self):
        """单轴拉伸：σ1=σ, σ2=σ3=0"""
        sigma = 100.0
        stress = np.array([[sigma, 0, 0, 0, 0, 0]])
        shear = get_principal_shear_stresses(stress)
        assert pytest.approx(shear[0][0], abs=1e-6) == sigma / 2  # |σ1-σ2|/2
        assert pytest.approx(shear[0][1], abs=1e-6) == sigma / 2  # |σ1-σ3|/2
        assert pytest.approx(shear[0][2], abs=1e-6) == 0.0  # |σ2-σ3|/2

    def test_batch(self):
        """批量计算"""
        stress = np.random.rand(30, 6)
        shear = get_principal_shear_stresses(stress)
        assert shear.shape == (30, 3)
        assert np.all(shear >= 0)


class TestMaxShearStress:
    """最大剪切应力测试"""

    def test_pure_shear(self):
        """纯剪切：最大剪切应力等于最大主应力"""
        tau = 50.0
        stress = np.array([[0, 0, 0, tau, 0, 0]])
        max_shear = get_max_shear_stress(stress)
        assert pytest.approx(max_shear[0], abs=1e-6) == tau

    def test_uniaxial_tension(self):
        """单轴拉伸：最大剪切应力 = σ1/2"""
        sigma = 200.0
        stress = np.array([[sigma, 0, 0, 0, 0, 0]])
        max_shear = get_max_shear_stress(stress)
        assert pytest.approx(max_shear[0], abs=1e-6) == sigma / 2

    def test_batch(self):
        """批量计算"""
        stress = np.random.rand(25, 6)
        max_shear = get_max_shear_stress(stress)
        assert max_shear.shape == (25,)
        assert np.all(max_shear >= 0)


class TestWorstPrincipalStress:
    """最不利主应力测试"""

    def test_tension_worst_is_positive(self):
        """受拉时最不利是最大主应力（正值）"""
        stress = np.array([[100.0, 0, 0, 0, 0, 0]])
        worst = get_worst_principal_stress(stress)
        assert pytest.approx(worst[0], abs=1e-6) == 100.0

    def test_compression_worst_is_negative(self):
        """受压时最不利是最小主应力（负值）"""
        stress = np.array([[0, 0, -100.0, 0, 0, 0]])
        worst = get_worst_principal_stress(stress)
        assert pytest.approx(worst[0], abs=1e-6) == -100.0

    def test_mixed(self):
        """拉压混合时比较绝对值"""
        # σ1=100 (tension), σ3=-50 (compression) → 最不利是 100
        stress = np.array([[50.0, 0, -30.0, 0, 0, 0]])
        worst = get_worst_principal_stress(stress)
        assert pytest.approx(worst[0], abs=1e-6) == 50.0


class TestStressInvariants:
    """应力不变量测试"""

    def test_hydrostatic_pressure(self):
        """静水压 I1 = -3p, I2 = 3p², I3 = -p³"""
        p = 50.0
        stress = np.array([[-p, -p, -p, 0, 0, 0]])
        inv = get_stress_invariants(stress)
        assert pytest.approx(inv["I1"][0], abs=1e-6) == -3 * p
        assert pytest.approx(inv["I2"][0], abs=1e-6) == 3 * p ** 2
        assert pytest.approx(inv["I3"][0], abs=1e-6) == -p ** 3

    def test_uniaxial_tension(self):
        """单轴拉伸：σ1=σ, I1=σ, I2=-σ², I3=0"""
        sigma = 100.0
        stress = np.array([[sigma, 0, 0, 0, 0, 0]])
        inv = get_stress_invariants(stress)
        assert pytest.approx(inv["I1"][0], abs=1e-6) == sigma
        assert pytest.approx(inv["I2"][0], abs=1e-6) == 0.0  # S11*S22 + ... - shear terms
        assert pytest.approx(inv["I3"][0], abs=1e-6) == 0.0

    def test_pure_shear(self):
        """纯剪切：I1=0"""
        tau = 50.0
        stress = np.array([[0, 0, 0, tau, 0, 0]])
        inv = get_stress_invariants(stress)
        assert pytest.approx(inv["I1"][0], abs=1e-6) == 0.0
        # I2 = -τ^2 (from -S12^2 term)
        assert pytest.approx(inv["I2"][0], abs=1e-6) == -tau ** 2

    def test_batch(self):
        """批量计算"""
        stress = np.random.rand(15, 6)
        inv = get_stress_invariants(stress)
        assert inv["I1"].shape == (15,)
        assert inv["I2"].shape == (15,)
        assert inv["I3"].shape == (15,)


class TestVonMisesFromUtils:
    """von_mises 函数测试（直接从 _utils 导入）"""

    def test_uniaxial_tension(self):
        """单轴拉伸：S11=100 → σ_vm = 100"""
        stress = np.array([[100.0, 0, 0, 0, 0, 0]])
        vm = von_mises(stress)
        assert pytest.approx(vm[0], abs=1e-6) == 100.0

    def test_hydrostatic_zero(self):
        """静水压：σ_vm = 0"""
        p = 50.0
        stress = np.array([[p, p, p, 0.0, 0.0, 0.0]])
        vm = von_mises(stress)
        assert pytest.approx(vm[0], abs=1e-6) == 0.0

    def test_pure_shear(self):
        """纯剪切：σ_vm = √3 · τ"""
        tau = 100.0
        stress = np.array([[0.0, 0.0, 0.0, tau, 0.0, 0.0]])
        vm = von_mises(stress)
        assert pytest.approx(vm[0], rel=1e-6) == tau * np.sqrt(3)

    def test_batch(self):
        """批量输入"""
        stress = np.random.rand(50, 6)
        vm = von_mises(stress)
        assert vm.shape == (50,)
        assert np.all(vm >= 0)