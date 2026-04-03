# diagnosis_visualizer.py
"""
诊断结果可视化

生成诊断推理链的因果图，帮助用户理解决策过程。
可选功能：需要 graphviz 和 networkx。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from .chain_reasoning import ChainReasoningResult

log = logging.getLogger(__name__)


def render_diagnosis_chain_graph(
    result: ChainReasoningResult,
    output_path: Optional[Path] = None,
) -> Optional[Path]:
    """
    渲染诊断推理链为因果图。

    Args:
        result: Chain 推理结果
        output_path: 输出路径（可选，默认在 results_dir 下生成）

    Returns:
        生成的图片路径，失败返回 None
    """
    try:
        import networkx as nx
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use('Agg')  # 非交互式后端
    except ImportError:
        log.warning("networkx 或 matplotlib 未安装，无法生成推理链图")
        return None

    if not result.success or not result.steps:
        return None

    # 创建有向图
    G = nx.DiGraph()

    # 节点样式
    node_colors = {
        "症状识别": "#ffcccc",  # 浅红
        "原因分析": "#ccffcc",  # 浅绿
        "验证推理": "#ccccff",  # 浅蓝
        "诊断结论": "#ffffcc",  # 浅黄
    }

    # 添加节点
    for i, step in enumerate(result.steps):
        node_id = f"step{i+1}"
        label = f"Step {i+1}\n{step.step_name}"
        G.add_node(node_id, label=label, step_name=step.step_name)

    # 添加边（串联所有步骤）
    for i in range(len(result.steps) - 1):
        G.add_edge(f"step{i+1}", f"step{i+2}")

    # 绘制图形
    plt.figure(figsize=(12, 8))
    pos = nx.spring_layout(G, k=2, iterations=50)

    # 绘制节点
    colors = [node_colors.get(G.nodes[n]["step_name"], "#ffffff") for n in G.nodes()]
    labels = {n: G.nodes[n]["label"] for n in G.nodes()}

    nx.draw(
        G, pos,
        with_labels=True,
        labels=labels,
        node_color=colors,
        node_size=3000,
        font_size=10,
        font_weight="bold",
        arrows=True,
        arrowsize=20,
        edge_color="gray",
        width=2,
    )

    plt.title("诊断推理链", fontsize=14, fontweight="bold")

    # 保存
    if output_path is None:
        output_path = Path("diagnosis_chain.png")

    try:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close()
        return output_path
    except Exception as exc:
        log.warning(f"保存推理链图失败: {exc}")
        return None


def render_diagnosis_html(
    result: ChainReasoningResult,
    output_path: Path,
) -> Path:
    """
    生成诊断结果的交互式 HTML 页面。

    Args:
        result: Chain 推理结果
        output_path: 输出 HTML 路径

    Returns:
        生成的 HTML 路径
    """
    # 构建 HTML 内容
    html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>诊断推理结果 - CAE-CLI</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
        }}
        .step {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .step-header {{
            display: flex;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        .step-number {{
            background: #667eea;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            margin-right: 15px;
        }}
        .step-title {{
            font-size: 1.3em;
            font-weight: bold;
            color: #333;
        }}
        .step-content {{
            white-space: pre-wrap;
            font-family: "SF Mono", Monaco, "Courier New", monospace;
            font-size: 0.9em;
            line-height: 1.6;
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }}
        .diagnosis {{
            background: #fffbeb;
            border: 2px solid #fbbf24;
        }}
        .footer {{
            text-align: center;
            color: #666;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 CAE-CLI 诊断推理结果</h1>
        <p>基于 Chain 多步推理的 FEA 问题诊断</p>
    </div>
"""

    for i, step in enumerate(result.steps):
        is_diagnosis = step.step_name == "诊断结论"
        step_class = "diagnosis" if is_diagnosis else "step"

        html_content += f"""
    <div class="{step_class}">
        <div class="step-header">
            <div class="step-number">{step.step_number}</div>
            <div class="step-title">{step.step_name}</div>
        </div>
        <div class="step-content">{step.content.strip()}</div>
    </div>
"""

    html_content += """
    <div class="footer">
        <p>由 CAE-CLI Chain 推理系统生成</p>
    </div>
</body>
</html>
"""

    output_path.write_text(html_content, encoding="utf-8")
    return output_path
