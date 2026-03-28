"""
cae-cli 在线诊断 Demo
部署到 Hugging Face Spaces：直接上传这个文件 + requirements.txt
"""

import gradio as gr
import re
from pathlib import Path


# ─── 规则层（从 cae-cli 提取的核心逻辑）────────────────────────────────────────

CONVERGENCE_PATTERNS = [
    (r"\*error", "求解器报错"),
    (r"not converged", "求解未收敛"),
    (r"increment size smaller", "增量步小于最小值"),
    (r"divergence", "求解发散"),
]

MATERIAL_PATTERNS = [
    (r"no elastic constants", "材料缺少弹性常数"),
    (r"no density", "材料缺少密度定义"),
    (r"no material", "未找到材料定义"),
]

ELEMENT_PATTERNS = [
    (r"negative jacobian", "单元翻转（负雅可比）"),
    (r"nonpositive jacobian", "单元质量问题（非正雅可比）"),
    (r"hourglassing", "沙漏模式（零能模式）"),
    (r"hourlim", "沙漏控制异常"),
]

SYNTAX_PATTERNS = [
    (r"card image cannot be interpreted", "无效的 INP 卡片"),
    (r"parameter not recognized", "参数名称错误"),
    (r"unknown keyword", "未知关键词"),
]

SUGGESTIONS = {
    "求解器报错": "检查 INP 文件格式，查看完整错误信息",
    "求解未收敛": "减小初始步长（*STATIC 首参数），检查边界条件",
    "增量步小于最小值": "减小初始步长，或增大最大增量数（INC 参数）",
    "求解发散": "检查载荷大小和边界条件，考虑分步加载",
    "材料缺少弹性常数": "在 *MATERIAL 中添加：\n*ELASTIC\n210000, 0.3",
    "材料缺少密度定义": "在 *MATERIAL 中添加：\n*DENSITY\n7.85e-9",
    "未找到材料定义": "检查 *MATERIAL 卡片是否正确定义",
    "单元翻转（负雅可比）": "改善网格质量，避免扭曲单元，尝试全积分单元",
    "单元质量问题（非正雅可比）": "检查网格划分，改善单元形状",
    "沙漏模式（零能模式）": "使用全积分单元替代减缩积分，或加密网格",
    "沙漏控制异常": "检查网格是否太粗，考虑换用全积分单元",
    "无效的 INP 卡片": "检查关键词拼写，确保与 CalculiX 支持的关键词一致",
    "参数名称错误": "检查参数名大小写，CalculiX 关键词全大写",
    "未知关键词": "该关键词可能是 Abaqus 专有，CalculiX 不支持",
}

SEVERITY = {
    "求解器报错": "❌",
    "求解未收敛": "❌",
    "增量步小于最小值": "⚠️",
    "求解发散": "❌",
    "材料缺少弹性常数": "❌",
    "材料缺少密度定义": "⚠️",
    "未找到材料定义": "❌",
    "单元翻转（负雅可比）": "❌",
    "单元质量问题（非正雅可比）": "⚠️",
    "沙漏模式（零能模式）": "⚠️",
    "沙漏控制异常": "⚠️",
    "无效的 INP 卡片": "⚠️",
    "参数名称错误": "⚠️",
    "未知关键词": "⚠️",
}


def check_patterns(text, patterns):
    issues = []
    text_lower = text.lower()
    for pattern, description in patterns:
        if re.search(pattern, text_lower):
            issues.append(description)
    return issues


def check_large_strain(text):
    """检测大变形"""
    issues = []
    strain_match = re.findall(r"e[xyz]{2}[:\s]+([\d.e+\-]+)", text.lower())
    for val in strain_match:
        try:
            if abs(float(val)) > 0.1:
                issues.append("检测到大变形（应变 > 10%）")
                break
        except ValueError:
            pass
    return issues


def check_displacement(text):
    """检测数值溢出"""
    issues = []
    disp_match = re.findall(r"[\d.]+[eE][+\-]?\d+", text)
    for val in disp_match:
        try:
            if abs(float(val)) > 1e10:
                issues.append("位移数值溢出（可能求解未收敛）")
                break
        except ValueError:
            pass
    return issues


def diagnose(file_obj, raw_text):
    """主诊断函数"""
    # 获取输入文本
    if file_obj is not None:
        try:
            content = Path(file_obj.name).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return f"文件读取失败：{e}"
    elif raw_text and raw_text.strip():
        content = raw_text
    else:
        return "⚠️ 请上传文件或粘贴求解器输出内容"

    # 运行所有规则
    all_issues = []
    all_issues.extend(check_patterns(content, CONVERGENCE_PATTERNS))
    all_issues.extend(check_patterns(content, MATERIAL_PATTERNS))
    all_issues.extend(check_patterns(content, ELEMENT_PATTERNS))
    all_issues.extend(check_patterns(content, SYNTAX_PATTERNS))
    all_issues.extend(check_large_strain(content))
    all_issues.extend(check_displacement(content))

    # 去重
    all_issues = list(dict.fromkeys(all_issues))

    # 生成报告
    if not all_issues:
        return "✅ 规则检测：未发现明显问题\n\n提示：如果求解结果仍然异常，可能是边界条件或载荷设置问题，需要人工检查。"

    lines = [f"规则检测：发现 {len(all_issues)} 个问题\n"]
    lines.append("─" * 50)

    for issue in all_issues:
        severity = SEVERITY.get(issue, "⚠️")
        suggestion = SUGGESTIONS.get(issue, "请检查相关设置")
        lines.append(f"\n{severity} {issue}")
        lines.append(f"   → {suggestion}")

    lines.append("\n" + "─" * 50)
    lines.append("\n💡 本诊断基于 CalculiX 源码硬编码规则，0 幻觉")
    lines.append("📦 完整功能：pip install cae-cxx")

    return "\n".join(lines)


# ─── Gradio 界面 ──────────────────────────────────────────────────────────────

with gr.Blocks(title="cae-cli 诊断 Demo") as demo:

    gr.Markdown("""
    # 🔍 cae-cli · CalculiX 智能诊断

    **上传 `.inp` / `.stderr` 文件，或直接粘贴求解器输出，自动检测问题根因**

    > 基于 527 个 CalculiX 源码硬编码规则 · 0 幻觉 · 本地版：`pip install cae-cxx`
    """)

    with gr.Row():
        with gr.Column():
            file_input = gr.File(
                label="上传文件（.inp / .stderr）",
                file_types=[".inp", ".stderr", ".txt", ".dat"],
            )
            text_input = gr.Textbox(
                label="或直接粘贴求解器输出",
                placeholder="粘贴 CalculiX 的 stderr 输出或 .sta 文件内容...",
                lines=8,
            )
            btn = gr.Button("🔍 开始诊断", variant="primary", size="lg")

        with gr.Column():
            output = gr.Textbox(
                label="诊断报告",
                lines=15,
                elem_classes=["result-box"],
            )

    btn.click(
        fn=diagnose,
        inputs=[file_input, text_input],
        outputs=output,
    )

    gr.Markdown("""
    ---
    ### 📋 支持检测的问题类型

    | 类别 | 检测内容 |
    |------|---------|
    | 收敛性 | 求解发散、增量步过小、未收敛 |
    | 材料定义 | 缺少弹性常数、密度、材料卡片 |
    | 单元质量 | 负雅可比、沙漏模式 |
    | 输入语法 | 无效卡片、参数名错误 |
    | 数值异常 | 位移溢出、大变形检测 |

    **GitHub**: [cae-cli](https://github.com/yd5768365-hue/cae-cli) ·
    **PyPI**: `pip install cae-cxx`
    """)


if __name__ == "__main__":
    demo.launch(
        theme=gr.themes.Base(
            primary_hue="slate",
            neutral_hue="zinc",
        ),
        css="""
        .header { text-align: center; padding: 20px 0; }
        .result-box { font-family: 'Courier New', monospace; }
        """
    )