"""Render portable, network-independent HTML from the handover Markdown."""

from __future__ import annotations

import base64
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import mistune

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = mistune.create_markdown(plugins=["table", "strikethrough"])
STYLE = """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f6f7;color:#183343;font:17px/1.85 system-ui,'Microsoft YaHei',sans-serif}a{color:#006d77;text-underline-offset:3px}header{background:#123c4a;color:white;padding:45px max(28px,calc((100vw - 1340px)/2));}header h1{max-width:1050px;font-size:36px;line-height:1.25;margin:0 0 15px}header p{max-width:1000px;margin:0;color:#dce8ec}.layout{max-width:1440px;margin:auto;display:grid;grid-template-columns:275px minmax(0,1fr);gap:35px;padding:36px 28px 80px}aside{font-size:14px;position:sticky;top:20px;align-self:start;max-height:90vh;overflow:auto}aside a{display:block;text-decoration:none;padding:6px 10px;border-left:2px solid #c8dadf}main{background:white;padding:28px 35px;border:1px solid #dce5e9;min-width:0}h1{font-size:29px;line-height:1.4}h2{font-size:25px;color:#00616c;margin:2.3em 0 .7em;line-height:1.4;scroll-margin-top:20px}h3{font-size:20px;margin:1.7em 0 .5em;line-height:1.5;scroll-margin-top:20px}p{margin:.8em 0}li{margin:.55em 0}strong{color:#103c49}code{font:0.88em/1.7 Consolas,monospace;background:#f0f5f6;padding:1px 4px;overflow-wrap:anywhere}pre{background:#eef4f5;padding:18px;overflow:auto;border-left:3px solid #2a7883}pre code{background:none;white-space:pre;font-size:14px;overflow-wrap:normal}.table-wrap{overflow-x:auto;margin:1.2em 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:11px;border:1px solid #d5e0e5;text-align:left;vertical-align:top}th{background:#e4eff1}tr:nth-child(even){background:#f8fafb}td code{font-size:12px}.flow{width:100%;height:auto;background:#f7fafb;border:1px solid #dae6e9;margin:15px 0 28px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}.metric{background:#e8f1f1;padding:15px;border-top:3px solid #34818a}.metric b{display:block;font-size:27px}.metric span{font-size:13px}figure{margin:30px 0}figure img{width:100%;height:auto;border:1px solid #dbe5e8}figcaption{font-size:14px;color:#4b6473;padding:10px 0}blockquote{margin:20px 0;border-left:4px solid #cc9e43;background:#fff7e8;padding:8px 20px}nav.top a{display:inline-block;color:#dceff2;margin-right:20px}footer{margin-top:35px;font-size:13px;color:#5c7481}@media(max-width:1050px){.layout{display:block}aside{position:static;max-height:260px;margin-bottom:20px;background:#e8f0f1;padding:12px}main{padding:22px}header h1{font-size:30px}}@media(max-width:600px){body{font-size:16px}.layout{padding:18px 12px}main{padding:17px}.metrics{grid-template-columns:1fr}.metric b{font-size:23px}h1{font-size:25px}h2{font-size:23px}td{min-width:125px}header{padding:30px 20px}}@media print{body{background:white;font-size:10.5pt}.layout{display:block;padding:0}aside,nav.top{display:none}header{color:black;background:white;padding:0}header p{color:black}main{padding:0;border:0}h2,h3{break-after:avoid}tr,figure{break-inside:avoid}a{color:inherit}.table-wrap{overflow:visible}}
"""


def flow(language: str) -> str:
    labels = (
        ["原始数据", "真实住宅采样", "七维指标", "标准化与约束", "贡献与汇总", "Top 5 与检验"]
        if language == "zh"
        else [
            "Source data",
            "Real-home samples",
            "7 indicators",
            "Scale + constraints",
            "Score + aggregate",
            "Top 5 + checks",
        ]
    )
    boxes = []
    for i, label in enumerate(labels):
        x = 10 + i * 164
        boxes.append(
            f'<rect x="{x}" y="24" width="148" height="64" rx="5" fill="#e4f0f1" stroke="#91b9c0"/><text x="{x + 74}" y="63" text-anchor="middle" font-size="15" fill="#123c4a">{html.escape(label)}</text>'
        )
        if i < 5:
            boxes.append(f'<path d="M{x + 149} 56h12m-5-5 5 5-5 5" stroke="#397b85" fill="none"/>')
    return (
        '<svg class="flow" role="img" aria-label="MCDA workflow" viewBox="0 0 1000 112" xmlns="http://www.w3.org/2000/svg">'
        + "".join(boxes)
        + "</svg>"
    )


def figures(language: str) -> str:
    captions = (
        [
            (
                "indicator_correlation.png",
                "七指标的相关性：同向变化不自动等于概念重复，也不能靠标准化消除。",
            ),
            ("scenario_top5.png", "四种偏好的已计算 Top 5；每种偏好使用相同数据与标准化。"),
            (
                "monte_carlo_frequency.png",
                "1,000 次权重扰动入选频率：条件于当前 Dirichlet 分布，非客观适合概率。",
            ),
            ("oat_ranks.png", "单因素权重与排名：其余权重按比例缩放；切换发生在测试区间内。"),
        ]
        if language == "zh"
        else [
            (
                "indicator_correlation.png",
                "Indicator correlation does not alone establish conceptual redundancy, and normalization does not remove it.",
            ),
            (
                "scenario_top5.png",
                "Saved Top 5 under four illustrative preferences, using unchanged data and normalization.",
            ),
            (
                "monte_carlo_frequency.png",
                "Top-5 frequency across 1,000 weight draws, conditional on the declared Dirichlet distribution; not objective suitability probability.",
            ),
            (
                "oat_ranks.png",
                "One-at-a-time rank trajectories: other weights are proportionally rescaled; switches are located within tested intervals.",
            ),
        ]
    )
    result = []
    for filename, caption in captions:
        data = base64.b64encode((ROOT / "outputs/experiments" / filename).read_bytes()).decode()
        result.append(
            f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(caption)}" loading="lazy"><figcaption>{html.escape(caption)}</figcaption></figure>'
        )
    return "".join(result)


def render(source: Path, destination: Path, language: str, include_results: bool = False) -> None:
    text = source.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ")
    rendered = MARKDOWN(text)
    headings = []

    def add_heading(match):
        level, content = match.groups()
        anchor = f"section-{len(headings) + 1}"
        headings.append((anchor, re.sub(r"<[^>]+>", "", content)))
        return f'<h{level} id="{anchor}">{content}</h{level}>'

    rendered = re.sub(r"<h([23])>(.*?)</h\1>", add_heading, rendered)
    rendered = rendered.replace("<table>", '<div class="table-wrap"><table>').replace(
        "</table>", "</table></div>"
    )
    toc = "".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in headings)
    intro = (
        "来源、公式、计算结果与待讨论问题，按真实实现逐步解释。原始来源文件保留原语言。"
        if language == "zh"
        else "Source evidence, formulas, computed results and open decisions, explained step by step. Original source files retain their source language."
    )
    supplement = ""
    if include_results:
        metrics = (
            [
                ("2,176 / 2,196", "基线 A / 补样 B"),
                ("1,000 / 84", "MC 扰动 / OAT 设置"),
                ("4 / 5", "正式 Top 5 中低样本区域"),
            ]
            if language == "zh"
            else [
                ("2,176 / 2,196", "Baseline A / supplemented B"),
                ("1,000 / 84", "MC draws / OAT settings"),
                ("4 / 5", "Baseline Top 5 with sparse support"),
            ]
        )
        supplement = (
            flow(language)
            + '<div class="metrics">'
            + "".join(f'<div class="metric"><b>{a}</b><span>{b}</span></div>' for a, b in metrics)
            + "</div>"
        )
        rendered += (
            '<h2 id="real-figures">'
            + (
                "真实实验图与读法"
                if language == "zh"
                else "Real experiment figures and how to read them"
            )
            + "</h2>"
            + figures(language)
        )
        toc += (
            '<a href="#real-figures">'
            + ("真实实验图" if language == "zh" else "Experiment figures")
            + "</a>"
        )
    destination.write_text(
        '<!doctype html><html lang="'
        + language
        + '"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + html.escape(title)
        + "</title><style>"
        + STYLE
        + "</style><header><h1>"
        + html.escape(title)
        + "</h1><p>"
        + intro
        + '</p></header><div class="layout"><aside>'
        + toc
        + "</aside><main>"
        + supplement
        + rendered
        + "<footer>GE5219 · 2026-10-19 · frozen computations: 2026-10-17 · routing scene: 2026-10-19 08:00 +08:00</footer></main></div></html>",
        encoding="utf-8",
    )


class LinkReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []
        self.anchors = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.anchors.add(values["id"])
        if tag == "a" and values.get("href"):
            self.targets.append(values["href"])
        if tag == "img" and values.get("src"):
            self.targets.append(values["src"])


def main():
    generated = []
    for language in ("zh", "en"):
        folder = ROOT / "docs" / f"handover_{language}"
        for source_name, target_name in [
            ("README.md", "index.html"),
            ("code_structure.md", "code_structure.html"),
            ("processing_methods.md", "processing_methods.html"),
        ]:
            output = folder / target_name
            render(folder / source_name, output, language, source_name == "README.md")
            generated.append(output)
    for source, target, language in [
        (
            ROOT / "docs/project-progress-2026-10-19.md",
            ROOT / "docs/project-progress-2026-10-19.html",
            "zh",
        ),
        (
            ROOT / "docs/handover_en/project_progress.md",
            ROOT / "docs/handover_en/project_progress.html",
            "en",
        ),
    ]:
        render(source, target, language)
        generated.append(target)
    combined = ROOT / "docs/processing_methods.md"
    combined.write_text(
        "# Processing methods / 处理方法\n\n"
        + (ROOT / "docs/handover_en/processing_methods.md")
        .read_text(encoding="utf-8")
        .replace("# Processing methods:", "# English:")
        + "\n\n"
        + (ROOT / "docs/handover_zh/processing_methods.md")
        .read_text(encoding="utf-8")
        .replace("# 处理方法：", "# 中文："),
        encoding="utf-8",
    )
    render(combined, ROOT / "docs/processing_methods.html", "en")
    generated.append(ROOT / "docs/processing_methods.html")
    entry = ROOT / "doc.html"
    entry.write_text(
        '<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GE5219 · Handover / 交接</title><style>'
        + STYLE
        + '</style><header><h1>GE5219 MCDA · Handover / 交接</h1><p>2026-10-19 · Source, methods, real results and next steps</p></header><main style="max-width:1000px;margin:35px auto;padding:35px"><h2>选择阅读语言 / Choose a language</h2><p><a href="docs/handover_zh/index.html">中文完整交接说明与结果解释</a></p><p><a href="docs/handover_en/index.html">Complete English handbook and result interpretation</a></p><p><a href="docs/processing_methods.html">Processing methods / 处理方法</a></p><p><a href="docs/handover_en/code_structure.html">Code structure</a> · <a href="docs/handover_zh/code_structure.html">代码结构</a></p><p><a href="notebooks/GE5219_Full_Workflow_zh.ipynb">中文 Notebook</a> · <a href="notebooks/GE5219_Full_Workflow_en.ipynb">English notebook</a></p><p><a href="docs/project-progress-2026-10-19.html">工作进度与后续计划</a> · <a href="docs/handover_en/project_progress.html">Progress and next tasks</a></p><blockquote>完整 ZIP 含 raw_data、路线缓存和结果；GitHub 单独源码不包含这些数据。原始交付和历史结果页保持原语言。<br>The complete ZIP includes raw_data, route cache and outputs. A GitHub clone alone does not. Original sources and archived result pages retain their source language.</blockquote></main></html>',
        encoding="utf-8",
    )
    generated.append(entry)
    issues = []
    for path in generated:
        reader = LinkReader()
        reader.feed(path.read_text(encoding="utf-8"))
        for target in reader.targets:
            parsed = urlparse(target)
            if parsed.scheme or parsed.netloc:
                continue
            if not parsed.path:
                if parsed.fragment and parsed.fragment not in reader.anchors:
                    issues.append({"file": str(path.relative_to(ROOT)), "target": target})
            elif not (path.parent / unquote(parsed.path)).exists():
                issues.append({"file": str(path.relative_to(ROOT)), "target": target})
    result = {
        "status": "passed" if not issues else "failed",
        "html_files": len(generated),
        "external_styles_scripts": 0,
        "all_figure_images_embedded": True,
        "relative_link_issues": issues,
    }
    (ROOT / "outputs/audits/handover_html_check.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))
    if issues:
        raise ValueError("Resolve documentation links before packaging")


if __name__ == "__main__":
    main()
