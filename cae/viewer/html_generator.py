"""
HTML 报告生成器
将 PyVista 渲染的截图 + 网格信息 + 求解摘要打包成自托管 HTML 报告。
报告是单文件（图片以 base64 内嵌），可以直接发给别人看，不依赖任何服务器。
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------ #
# 数据结构
# ------------------------------------------------------------------ #

@dataclass
class ReportSection:
    title: str
    image_path: Optional[Path] = None
    caption: str = ""
    data_table: Optional[dict] = None  # {label: value}


@dataclass
class ReportConfig:
    title: str = "cae-cli 仿真报告"
    job_name: str = ""
    solver: str = "CalculiX"
    node_count: int = 0
    element_count: int = 0
    solve_time: str = ""
    sections: list[ReportSection] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ #
# HTML 模板
# ------------------------------------------------------------------ #

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg:        #0e0e16;
    --surface:   #16161f;
    --surface2:  #1e1e2e;
    --border:    #2a2a3e;
    --accent:    #4488ff;
    --accent2:   #44ccaa;
    --text:      #d8d8f0;
    --muted:     #7070a0;
    --danger:    #ff6666;
    --success:   #44dd88;
    --radius:    8px;
    --font:      -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    line-height: 1.6;
    padding: 0 0 60px;
  }}

  /* ---- 顶部 header ---- */
  .site-header {{
    background: linear-gradient(135deg, #0a0a18 0%, #1a1a30 100%);
    border-bottom: 1px solid var(--border);
    padding: 28px 40px 22px;
    display: flex;
    align-items: flex-start;
    gap: 24px;
  }}
  .header-icon {{
    font-size: 2.4rem;
    line-height: 1;
    margin-top: 2px;
  }}
  .header-title h1 {{
    font-size: 1.5rem;
    font-weight: 700;
    color: #7ec8e3;
    letter-spacing: 0.04em;
  }}
  .header-title p {{
    font-size: 0.82rem;
    color: var(--muted);
    margin-top: 4px;
  }}

  /* ---- 摘要卡片 ---- */
  .summary {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    padding: 24px 40px 0;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
  }}
  .stat-card .label {{
    font-size: 0.72rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .stat-card .value {{
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--accent);
    margin-top: 4px;
  }}
  .stat-card .unit {{
    font-size: 0.75rem;
    color: var(--muted);
  }}

  /* ---- 主内容区 ---- */
  main {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 32px 40px 0;
  }}

  /* ---- 章节 ---- */
  .section {{
    margin-bottom: 40px;
  }}
  .section-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}
  .section-header h2 {{
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--text);
  }}
  .section-badge {{
    font-size: 0.68rem;
    background: var(--surface2);
    color: var(--accent);
    padding: 2px 8px;
    border-radius: 10px;
    border: 1px solid var(--border);
  }}

  /* ---- 图像区 ---- */
  .img-wrap {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    position: relative;
  }}
  .img-wrap img {{
    width: 100%;
    display: block;
    cursor: zoom-in;
    transition: transform 0.2s;
  }}
  .img-wrap img.zoomed {{
    transform: scale(1.6);
    transform-origin: var(--ox, 50%) var(--oy, 50%);
    cursor: zoom-out;
  }}
  .img-caption {{
    padding: 10px 14px;
    font-size: 0.8rem;
    color: var(--muted);
    border-top: 1px solid var(--border);
    background: var(--surface2);
  }}

  /* ---- 数据表格 ---- */
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }}
  .data-table td {{
    padding: 8px 14px;
    border-bottom: 1px solid var(--border);
  }}
  .data-table tr:last-child td {{ border-bottom: none; }}
  .data-table td:first-child {{
    color: var(--muted);
    width: 40%;
    font-size: 0.78rem;
  }}
  .data-table td:last-child {{
    color: var(--text);
    font-weight: 500;
  }}
  .data-table-wrap {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
  }}

  /* ---- 两列布局 ---- */
  .two-col {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }}
  @media (max-width: 800px) {{
    .two-col {{ grid-template-columns: 1fr; }}
    .summary {{ padding: 16px 20px 0; }}
    main {{ padding: 20px 20px 0; }}
    .site-header {{ padding: 20px; }}
  }}

  /* ---- footer ---- */
  footer {{
    margin-top: 60px;
    padding: 20px 40px;
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
    color: var(--muted);
    text-align: center;
  }}
</style>
</head>
<body>

<div class="site-header">
  <div class="header-icon">⚡</div>
  <div class="header-title">
    <h1>{title}</h1>
    <p>生成时间：{created_at} &nbsp;·&nbsp; 求解器：{solver}</p>
  </div>
</div>

<div class="summary">
  <div class="stat-card">
    <div class="label">工况名称</div>
    <div class="value" style="font-size:1rem">{job_name}</div>
  </div>
  <div class="stat-card">
    <div class="label">节点数</div>
    <div class="value">{node_count}</div>
  </div>
  <div class="stat-card">
    <div class="label">单元数</div>
    <div class="value">{element_count}</div>
  </div>
  <div class="stat-card">
    <div class="label">求解耗时</div>
    <div class="value">{solve_time}</div>
  </div>
</div>

<main>
{sections_html}
</main>

<footer>
  cae-cli 仿真报告 &nbsp;·&nbsp; 由 PyVista + CalculiX 生成
</footer>

<script>
// 点击图像放大/缩小
document.querySelectorAll('.img-wrap img').forEach(img => {{
  img.addEventListener('click', e => {{
    const rect = img.getBoundingClientRect();
    const ox = ((e.clientX - rect.left) / rect.width * 100).toFixed(1) + '%';
    const oy = ((e.clientY - rect.top)  / rect.height * 100).toFixed(1) + '%';
    img.style.setProperty('--ox', ox);
    img.style.setProperty('--oy', oy);
    img.classList.toggle('zoomed');
  }});
}});
</script>
</body>
</html>
"""

_SECTION_TEMPLATE = """\
<div class="section">
  <div class="section-header">
    <h2>{title}</h2>
    {badge}
  </div>
  {content}
</div>
"""

_IMG_TEMPLATE = """\
<div class="img-wrap">
  <img src="data:image/png;base64,{b64}" alt="{alt}" loading="lazy"/>
  <div class="img-caption">{caption}</div>
</div>
"""

_TABLE_TEMPLATE = """\
<div class="data-table-wrap">
  <table class="data-table">
    {rows}
  </table>
</div>
"""


# ------------------------------------------------------------------ #
# 生成函数
# ------------------------------------------------------------------ #

def generate_report(config: ReportConfig, output_path: Path) -> Path:
    """
    生成自托管 HTML 报告（图片 base64 内嵌）。

    Args:
        config:      报告配置（含章节列表）
        output_path: 输出 .html 路径

    Returns:
        输出文件路径
    """
    sections_html = ""
    for sec in config.sections:
        content_parts = []

        # 图像
        if sec.image_path and sec.image_path.exists():
            b64 = _img_to_base64(sec.image_path)
            content_parts.append(
                _IMG_TEMPLATE.format(
                    b64=b64,
                    alt=sec.title,
                    caption=sec.caption or sec.title,
                )
            )

        # 数据表格
        if sec.data_table:
            rows = "\n".join(
                f"<tr><td>{k}</td><td>{v}</td></tr>"
                for k, v in sec.data_table.items()
            )
            content_parts.append(_TABLE_TEMPLATE.format(rows=rows))

        badge = ""
        sections_html += _SECTION_TEMPLATE.format(
            title=sec.title,
            badge=badge,
            content="\n".join(content_parts) or "<p style='color:var(--muted)'>（无内容）</p>",
        )

    html = _HTML_TEMPLATE.format(
        title=config.title,
        created_at=config.created_at,
        solver=config.solver,
        job_name=config.job_name or "—",
        node_count=f"{config.node_count:,}" if config.node_count else "—",
        element_count=f"{config.element_count:,}" if config.element_count else "—",
        solve_time=config.solve_time or "—",
        sections_html=sections_html,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def build_report_from_renders(
    render_results: dict[str, "RenderResult"],  # noqa: F821
    output_dir: Path,
    mesh_info=None,
    job_name: str = "",
    solve_time: str = "",
) -> Path:
    """
    从 render_all() 的结果字典直接构建报告。
    这是最常用的入口，供 main.py 调用。
    """
    from .pyvista_renderer import MeshInfo

    sections: list[ReportSection] = []

    # ---- 求解摘要表格 ----
    summary_data = {}
    if job_name:
        summary_data["工况文件"] = job_name
    if solve_time:
        summary_data["求解耗时"] = solve_time
    if mesh_info:
        summary_data["节点总数"] = f"{mesh_info.n_points:,}"
        summary_data["单元总数"] = f"{mesh_info.n_cells:,}"
        if mesh_info.scalar_fields:
            summary_data["可用字段"] = ", ".join(mesh_info.scalar_fields)
        bb = mesh_info.bounds
        if bb:
            summary_data["模型尺寸 X"] = f"{bb[0]:.2f} ~ {bb[1]:.2f} mm"
            summary_data["模型尺寸 Y"] = f"{bb[2]:.2f} ~ {bb[3]:.2f} mm"
            summary_data["模型尺寸 Z"] = f"{bb[4]:.2f} ~ {bb[5]:.2f} mm"

    if summary_data:
        sections.append(ReportSection(
            title="求解摘要",
            data_table=summary_data,
        ))

    # ---- 各图像章节 ----
    _SECTION_LABELS = {
        "displacement": ("变形云图", "位移场 U，幅值着色，变形已放大显示"),
        "von_mises":    ("Von Mises 应力云图", "等效 Von Mises 应力分布（MPa）"),
        "slice_x":      ("截面切片 — X 向", "沿 X 轴中点截面"),
        "slice_y":      ("截面切片 — Y 向", "沿 Y 轴中点截面"),
        "slice_z":      ("截面切片 — Z 向", "沿 Z 轴中点截面"),
    }

    for key, res in render_results.items():
        label, caption = _SECTION_LABELS.get(key, (key, ""))
        if res.success and res.first():
            sections.append(ReportSection(
                title=label,
                image_path=res.first(),
                caption=caption,
            ))
        else:
            sections.append(ReportSection(
                title=label,
                caption=f"渲染失败: {res.error}",
            ))

    config = ReportConfig(
        title=f"cae-cli 仿真报告 — {job_name or '未命名工况'}",
        job_name=job_name,
        solver="CalculiX",
        node_count=mesh_info.n_points if mesh_info else 0,
        element_count=mesh_info.n_cells if mesh_info else 0,
        solve_time=solve_time,
        sections=sections,
    )

    report_path = output_dir / "report.html"
    return generate_report(config, report_path)


def _img_to_base64(img_path: Path) -> str:
    return base64.b64encode(img_path.read_bytes()).decode("ascii")