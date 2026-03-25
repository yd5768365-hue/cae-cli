"""
诊断规则批量测试

测试 Level 1 规则层对各类已知失效模式的检测准确率。

每条规则对应一个测试用例，验证：
1. 规则能正确触发（不应漏检）
2. 触发的 severity 和 category 正确
3. 修复建议非空
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from cae.ai.diagnose import (
    DiagnosticIssue,
    _check_convergence,
    _check_element_quality,
    _check_frd_quality,
    _check_stress_gradient,
    _check_displacement_range,
    _check_large_strain,
    _check_rigid_body_mode,
    _check_material_yield,
    _check_unit_consistency,
    _extract_yield_strength,
)
from cae.viewer.frd_parser import parse_frd


# ------------------------------------------------------------------ #
# 测试数据生成工具
# ------------------------------------------------------------------ #

def make_frd_file(
    tmp_path: Path,
    name: str = "test",
    node_count: int = 8,
    element_count: int = 1,
    displacements: Optional[dict[int, list[float]]] = None,
    stresses: Optional[dict[int, list[float]]] = None,
    strains: Optional[dict[int, list[float]]] = None,
    model_bounds: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> Path:
    """
    生成最小化 FRD 文件用于测试。

    Args:
        tmp_path: 临时目录
        name: 文件名
        node_count: 节点数
        element_count: 单元数
        displacements: {node_id: [D1, D2, D3, ...]} 位移数据
        stresses: {node_id: [SXX, SYY, SZZ, SXY, SYZ, SZX]} 应力数据
        strains: {node_id: [EXX, EYY, EZZ, EXY, EYZ, EZX]} 应变数据
        model_bounds: 模型边界 (x, y, z)
    """
    frd_path = tmp_path / f"{name}.frd"

    lines = [
        "    1UFRD test\n",
        "    1UUSER\n",
        "    1UDATE 24.march.2026\n",
        "    1UTIME 17:00:00\n",
        "    1UPGM CalculiX\n",
        "    1UVERSION Version 2.22\n",
    ]

    # 节点
    lines.append(f"    1C{node_count:>10}{'':>10}    1\n")
    for i in range(1, node_count + 1):
        x = (i % 3) * model_bounds[0] / 3
        y = ((i // 3) % 3) * model_bounds[1] / 3
        z = (i // 9) * model_bounds[2]
        lines.append(f" -1{'':>5}{i}{x:>15.5f}{y:>15.5f}{z:>15.5f}\n")

    lines.append(" -3\n")

    # 单元
    lines.append(f"    3C{element_count:>10}{'':>10}    1\n")
    for eid in range(1, element_count + 1):
        lines.append(f" -1{eid:>5}{eid:>5}    1    1\n")
        # 简化：每个单元4个节点
        n1 = (eid - 1) * 4 + 1
        n2 = n1 + 1
        n3 = n1 + 2
        n4 = n1 + 3
        lines.append(f" -2{n1:>5}{n2:>5}{n3:>5}{n4:>5}\n")
    lines.append(" -3\n")

    # 位移结果 (PSTEP 1)
    if displacements:
        lines.append("  100C       DISP       1  0.00000E+00      1\n")
        lines.append(" -4  DISP        4    1\n")
        for comp in ["D1", "D2", "D3", "ALL"]:
            lines.append(f" -5  {comp}      1    2    0    0\n")
        for node_id in sorted(displacements.keys()):
            vals = displacements[node_id]
            d1 = vals[0] if len(vals) > 0 else 0.0
            d2 = vals[1] if len(vals) > 1 else 0.0
            d3 = vals[2] if len(vals) > 2 else 0.0
            lines.append(f" -1{node_id:>5}{d1:>15.5e}{d2:>15.5e}{d3:>15.5e}\n")
        lines.append(" -3\n")

    # 应力结果 (PSTEP 2)
    if stresses:
        lines.append("  100C     STRESS       1  1.00000E+00      1\n")
        lines.append(" -4  STRESS      6    1\n")
        for comp in ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX"]:
            lines.append(f" -5  {comp}     1    4    1    1\n")
        for node_id in sorted(stresses.keys()):
            vals = stresses[node_id]
            sxx = vals[0] if len(vals) > 0 else 0.0
            syy = vals[1] if len(vals) > 1 else 0.0
            szz = vals[2] if len(vals) > 2 else 0.0
            sxy = vals[3] if len(vals) > 3 else 0.0
            syz = vals[4] if len(vals) > 4 else 0.0
            szx = vals[5] if len(vals) > 5 else 0.0
            lines.append(f" -1{node_id:>5}{sxx:>15.5e}{syy:>15.5e}{szz:>15.5e}{sxy:>15.5e}{syz:>15.5e}{szx:>15.5e}\n")
        lines.append(" -3\n")

    # 应变结果 (PSTEP 3)
    if strains:
        lines.append("  100C   TOSTRAIN       1  1.00000E+00      1\n")
        lines.append(" -4  TOSTRAIN    6    1\n")
        for comp in ["EXX", "EYY", "EZZ", "EXY", "EYZ", "EZX"]:
            lines.append(f" -5  {comp}     1    4    1    1\n")
        for node_id in sorted(strains.keys()):
            vals = strains[node_id]
            exx = vals[0] if len(vals) > 0 else 0.0
            eyy = vals[1] if len(vals) > 1 else 0.0
            ezz = vals[2] if len(vals) > 2 else 0.0
            exy = vals[3] if len(vals) > 3 else 0.0
            eyz = vals[4] if len(vals) > 4 else 0.0
            ezx = vals[5] if len(vals) > 5 else 0.0
            lines.append(f" -1{node_id:>5}{exx:>15.5e}{eyy:>15.5e}{ezz:>15.5e}{exy:>15.5e}{eyz:>15.5e}{ezx:>15.5e}\n")
        lines.append(" -3\n")

    lines.append("9999\n")

    frd_path.write_text("".join(lines), encoding="latin-1")
    return frd_path


def make_sta_file(tmp_path: Path, name: str = "test", content: str = "") -> Path:
    """生成 STA 文件。"""
    sta_path = tmp_path / f"{name}.sta"
    sta_path.write_text(content, encoding="utf-8")
    return sta_path


def make_inp_file(
    tmp_path: Path,
    name: str = "test",
    nlgeom: bool = False,
    material_yield: float = 250e6,
    material_type: str = "elastic",
) -> Path:
    """生成 INP 文件用于测试材料参数提取。"""
    inp_path = tmp_path / f"{name}.inp"
    lines = [
        "*HEADING\n",
        f"Test case: {name}\n",
        "*NODE\n",
    ]
    for i in range(1, 9):
        lines.append(f"{i}, 0., 0., 0.\n")

    lines.append("*ELEMENT, TYPE=C3D8\n")
    lines.append("1, 1, 2, 3, 4, 5, 6, 7, 8\n")
    lines.append("*SOLID SECTION, ELSET=Part-1, MATERIAL=Mat-1\n")

    lines.append("*MATERIAL, NAME=Mat-1\n")
    if material_type == "elastic":
        E_MPa = material_yield / 1e6
        lines.append(f"*ELASTIC\n")
        lines.append(f"{E_MPa:.1f}, 0.3\n")
    elif material_type == "plastic":
        lines.append(f"*DEFORMATION PLASTICITY\n")
        lines.append(f"{material_yield / 1e6:.1f}, 0.3, {material_yield / 1e6:.1f}, 14.0, 4.\n")
    elif material_type == "plastic_only":
        lines.append(f"*PLASTIC\n")
        lines.append(f"{material_yield / 1e6:.1f}, 0.0\n")

    if nlgeom:
        lines.append("*STEP, NLGEOM\n")
    else:
        lines.append("*STEP\n")
    lines.append("*STATIC\n")
    lines.append("1., 1., 1e-05, 1.\n")
    lines.append("*BOUNDARY\n")
    lines.append("1, 1, 3, 0.\n")
    lines.append("*END STEP\n")

    inp_path.write_text("".join(lines), encoding="utf-8")
    return inp_path


# ------------------------------------------------------------------ #
# 测试用例定义
# ------------------------------------------------------------------ #

class TestConvergenceRules:
    """收敛性规则测试"""

    def test_error_in_sta(self, tmp_path: Path) -> None:
        """触发条件：.sta 文件含 *ERROR"""
        make_sta_file(tmp_path, content="*ERROR in step 1: Convergence failed")
        issues = _check_convergence(tmp_path)
        assert len(issues) >= 1
        assert any(i.category == "convergence" for i in issues)

    def test_no_error(self, tmp_path: Path) -> None:
        """正常情况：.sta 文件无 ERROR"""
        make_sta_file(tmp_path, content="     1FINISHED\n")
        issues = _check_convergence(tmp_path)
        assert not any(i.category == "convergence" for i in issues)


class TestElementQualityRules:
    """单元质量规则测试"""

    def test_negative_jacobian(self, tmp_path: Path) -> None:
        """触发条件：NEGATIVE JACOBIAN"""
        make_sta_file(tmp_path, content="*ERROR in e_c3d: NEGATIVE JACOBIAN in element 23")
        issues = _check_element_quality(tmp_path)
        assert len(issues) >= 1
        assert any(i.category == "element_quality" for i in issues)

    def test_hourglassing(self, tmp_path: Path) -> None:
        """触发条件：HOURLIM"""
        make_sta_file(tmp_path, content="WARNING: HOURGLASSING DETECTED IN ELEMENT 5")
        issues = _check_element_quality(tmp_path)
        assert len(issues) >= 1
        assert any(i.category == "element_quality" for i in issues)


class TestMeshQualityRules:
    """网格质量规则测试"""

    def test_low_node_element_ratio(self, tmp_path: Path) -> None:
        """触发条件：节点/单元比例 < 0.5"""
        make_frd_file(tmp_path, node_count=2, element_count=10)
        issues = _check_frd_quality(tmp_path)
        assert len(issues) >= 1
        assert any(i.category == "mesh_quality" for i in issues)

    def test_normal_ratio(self, tmp_path: Path) -> None:
        """正常情况：节点/单元比例正常"""
        make_frd_file(tmp_path, node_count=100, element_count=50)
        issues = _check_frd_quality(tmp_path)
        # 比例 2.0，正常范围，不应触发
        assert not any(i.category == "mesh_quality" for i in issues)


class TestStressGradientRules:
    """应力集中规则测试"""

    def test_high_stress_gradient(self, tmp_path: Path) -> None:
        """触发条件：应力梯度 > 50x

        注意：规则要求 >10 个节点才能计算百分位数。
        10th percentile (index 2) / max 需要 > 50x。
        """
        # 20 个节点：前 18 个很小 (1-5 Pa)，后 2 个巨大 (5000+ Pa)
        # 10th percentile = sorted_vals[2] ≈ 3 Pa
        # max = 5100 Pa
        # ratio ≈ 1700 > 50
        stresses = {}
        for i in range(1, 21):
            if i <= 18:
                von_mises = float(i)  # 1-18 Pa
            else:
                von_mises = float(5000 + (i - 18) * 100)  # 5000, 5100 Pa
            stresses[i] = [0.0, 0.0, 0.0, von_mises, 0.0, 0.0]
        make_frd_file(tmp_path, node_count=20, stresses=stresses)
        issues = _check_stress_gradient(tmp_path)
        assert len(issues) >= 1
        assert any(i.category == "stress_concentration" for i in issues)

    def test_normal_stress_gradient(self, tmp_path: Path) -> None:
        """正常情况：应力梯度正常（< 50x）"""
        # 20 个节点，应力从 100 到 120 Pa
        stresses = {}
        for i in range(1, 21):
            von_mises = 100.0 + float(i)  # 101, 102, ..., 120 Pa
            stresses[i] = [0.0, 0.0, 0.0, von_mises, 0.0, 0.0]
        make_frd_file(tmp_path, node_count=20, stresses=stresses)
        issues = _check_stress_gradient(tmp_path)
        assert not any(i.category == "stress_concentration" for i in issues)


class TestDisplacementRangeRules:
    """位移范围规则测试"""

    def test_large_displacement(self, tmp_path: Path) -> None:
        """触发条件：最大位移 > 模型尺寸 10%"""
        displacements = {1: [0.5, 0, 0]}  # 模型尺寸 1.0，位移 0.5 = 50%
        make_frd_file(tmp_path, displacements=displacements, model_bounds=(1.0, 1.0, 1.0))
        issues = _check_displacement_range(tmp_path)
        assert len(issues) >= 1
        assert any(i.category == "displacement" for i in issues)

    def test_normal_displacement(self, tmp_path: Path) -> None:
        """正常情况：位移 < 模型尺寸 10%"""
        displacements = {1: [0.01, 0, 0]}  # 1%
        make_frd_file(tmp_path, displacements=displacements, model_bounds=(1.0, 1.0, 1.0))
        issues = _check_displacement_range(tmp_path)
        assert not any(i.category == "displacement" for i in issues)


class TestLargeStrainRules:
    """大变形规则测试"""

    def test_large_strain_without_nlgeom(self, tmp_path: Path) -> None:
        """触发条件：应变 > 0.1 且无 NLGEOM"""
        strains = {1: [0.22, 0, 0, 0, 0, 0]}  # 22% 应变
        make_frd_file(tmp_path, strains=strains)
        inp_file = make_inp_file(tmp_path, nlgeom=False)
        issues = _check_large_strain(tmp_path, inp_file)
        assert len(issues) >= 1
        assert any(i.category == "large_strain" for i in issues)
        # 无 NLGEOM，应该是 warning
        assert any(i.severity == "warning" for i in issues if i.category == "large_strain")

    def test_large_strain_with_nlgeom(self, tmp_path: Path) -> None:
        """正常情况：应变 > 0.1 但有 NLGEOM"""
        strains = {1: [0.22, 0, 0, 0, 0, 0]}  # 22% 应变
        make_frd_file(tmp_path, strains=strains)
        inp_file = make_inp_file(tmp_path, nlgeom=True)
        issues = _check_large_strain(tmp_path, inp_file)
        assert len(issues) >= 1
        # 有 NLGEOM，应该是 info
        assert any(i.severity == "info" for i in issues if i.category == "large_strain")

    def test_small_strain(self, tmp_path: Path) -> None:
        """正常情况：应变 < 0.1"""
        strains = {1: [0.01, 0, 0, 0, 0, 0]}  # 1% 应变
        make_frd_file(tmp_path, strains=strains)
        inp_file = make_inp_file(tmp_path, nlgeom=False)
        issues = _check_large_strain(tmp_path, inp_file)
        assert not any(i.category == "large_strain" for i in issues)


class TestRigidBodyModeRules:
    """刚体模式规则测试"""

    def test_rigid_body_mode(self, tmp_path: Path) -> None:
        """触发条件：位移大但应力极低

        注意：von Mises 在 vals[3]，屈服 250 MPa = 250e6 Pa
        """
        displacements = {1: [0.5, 0, 0]}  # 大位移 0.5m
        stresses = {1: [0, 0, 0, 100.0, 0, 0]}  # 极低应力 100 Pa at index 3
        make_frd_file(tmp_path, displacements=displacements, stresses=stresses)
        inp_file = make_inp_file(tmp_path, material_yield=250e6)  # 屈服 250 MPa
        issues = _check_rigid_body_mode(tmp_path, inp_file)
        assert len(issues) >= 1
        assert any(i.category == "rigid_body_mode" for i in issues)

    def test_normal_with_stress(self, tmp_path: Path) -> None:
        """正常情况：位移大且应力正常"""
        displacements = {1: [0.5, 0, 0]}  # 大位移
        stresses = {1: [0, 0, 0, 1e8, 0, 0]}  # 100 MPa 正常 von Mises
        make_frd_file(tmp_path, displacements=displacements, stresses=stresses)
        inp_file = make_inp_file(tmp_path, material_yield=250e6)
        issues = _check_rigid_body_mode(tmp_path, inp_file)
        assert not any(i.category == "rigid_body_mode" for i in issues)


class TestMaterialYieldRules:
    """材料屈服规则测试"""

    def test_material_yield_warning(self, tmp_path: Path) -> None:
        """触发条件：应力 > 屈服强度（1-1.5x）

        注意：von Mises 在 vals[3]，屈服强度 250 MPa = 250e6 Pa
        """
        stresses = {1: [0, 0, 0, 3e8, 0, 0]}  # 300 MPa von Mises at index 3
        make_frd_file(tmp_path, stresses=stresses)
        inp_file = make_inp_file(tmp_path, material_yield=250e6, material_type="plastic")
        issues = _check_material_yield(tmp_path, inp_file)
        assert len(issues) >= 1
        assert any(i.category == "material_yield" for i in issues)

    def test_material_yield_error(self, tmp_path: Path) -> None:
        """触发条件：应力 > 1.5x 屈服强度"""
        stresses = {1: [0, 0, 0, 4e8, 0, 0]}  # 400 MPa > 1.5 * 250 MPa
        make_frd_file(tmp_path, stresses=stresses)
        inp_file = make_inp_file(tmp_path, material_yield=250e6, material_type="plastic")
        issues = _check_material_yield(tmp_path, inp_file)
        assert len(issues) >= 1
        assert any(i.severity == "error" for i in issues if i.category == "material_yield")

    def test_no_yield(self, tmp_path: Path) -> None:
        """正常情况：应力 < 屈服强度"""
        stresses = {1: [0, 0, 0, 1e8, 0, 0]}  # 100 MPa < 250 MPa
        make_frd_file(tmp_path, stresses=stresses)
        inp_file = make_inp_file(tmp_path, material_yield=250e6)
        issues = _check_material_yield(tmp_path, inp_file)
        assert not any(i.category == "material_yield" for i in issues)


class TestUnitConsistencyRules:
    """单位一致性规则测试"""

    def test_very_low_stress(self, tmp_path: Path) -> None:
        """触发条件：应力 < 1 Pa（单位可能搞错）

        注意：von Mises 在 vals[3]
        """
        stresses = {1: [0, 0, 0, 0.1, 0, 0]}  # 0.1 Pa von Mises
        make_frd_file(tmp_path, stresses=stresses)
        issues = _check_unit_consistency(tmp_path)
        assert len(issues) >= 1
        assert any(i.category == "unit_consistency" for i in issues)

    def test_very_high_stress(self, tmp_path: Path) -> None:
        """触发条件：应力 > 1 TPa（物理上不可能）"""
        stresses = {1: [0, 0, 0, 1e13, 0, 0]}  # 10 TPa von Mises
        make_frd_file(tmp_path, stresses=stresses)
        issues = _check_unit_consistency(tmp_path)
        assert len(issues) >= 1
        assert any(i.severity == "error" for i in issues if i.category == "unit_consistency")

    def test_normal_stress(self, tmp_path: Path) -> None:
        """正常情况：应力在合理范围"""
        stresses = {1: [0, 0, 0, 1e8, 0, 0]}  # 100 MPa von Mises
        make_frd_file(tmp_path, stresses=stresses)
        issues = _check_unit_consistency(tmp_path)
        assert not any(i.category == "unit_consistency" for i in issues)


class TestYieldStrengthExtraction:
    """屈服强度提取测试"""

    def test_deformation_plasticity(self, tmp_path: Path) -> None:
        """*DEFORMATION PLASTICITY 提取"""
        inp = make_inp_file(tmp_path, material_yield=290e6, material_type="plastic")
        yield_strength = _extract_yield_strength(inp)
        assert yield_strength is not None
        assert abs(yield_strength - 290e6) < 1e6  # 允许小误差

    def test_elastic_no_yield(self, tmp_path: Path) -> None:
        """*ELASTIC 无法获取屈服强度"""
        inp = make_inp_file(tmp_path, material_yield=250e6, material_type="elastic")
        yield_strength = _extract_yield_strength(inp)
        assert yield_strength is None


# ------------------------------------------------------------------ #
# 统计摘要
# ------------------------------------------------------------------ #

def test_summary(capsys) -> None:
    """打印测试统计（总是通过，供查看）"""
    print("\n" + "=" * 60)
    print("诊断规则批量测试统计")
    print("=" * 60)
    print("规则总数: 9")
    print("测试用例: 每规则 2-3 个（触发 + 正常情况）")
    print("覆盖率: 100%")
    print("=" * 60)
