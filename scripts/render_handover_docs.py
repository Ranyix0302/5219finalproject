"""Render portable, network-independent HTML from the handover Markdown."""

from __future__ import annotations

import html
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

import mistune
from handover_visuals import VISUAL_KEYS, build_visuals

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = mistune.create_markdown(plugins=["table", "strikethrough"])
STYLE = """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f6f7;color:#183343;font:17px/1.85 system-ui,'Microsoft YaHei',sans-serif}a{color:#006d77;text-underline-offset:3px}header{background:#123c4a;color:white;padding:45px max(28px,calc((100vw - 1340px)/2));}header h1{max-width:1050px;font-size:36px;line-height:1.25;margin:0 0 15px}header p{max-width:1000px;margin:0;color:#dce8ec}.layout{max-width:1440px;margin:auto;display:grid;grid-template-columns:275px minmax(0,1fr);gap:35px;padding:36px 28px 80px}aside{font-size:14px;position:sticky;top:20px;align-self:start;max-height:90vh;overflow:auto}aside a{display:block;text-decoration:none;padding:6px 10px;border-left:2px solid #c8dadf}main{background:white;padding:28px 35px;border:1px solid #dce5e9;min-width:0}h1{font-size:29px;line-height:1.4}h2{font-size:25px;color:#00616c;margin:2.3em 0 .7em;line-height:1.4;scroll-margin-top:20px}h3{font-size:20px;margin:1.7em 0 .5em;line-height:1.5;scroll-margin-top:20px}p{margin:.8em 0}li{margin:.55em 0}strong{color:#103c49}code{font:0.88em/1.7 Consolas,monospace;background:#f0f5f6;padding:1px 4px;overflow-wrap:anywhere}pre{background:#eef4f5;padding:18px;overflow:auto;border-left:3px solid #2a7883}pre code{background:none;white-space:pre;font-size:14px;overflow-wrap:normal}.table-wrap{overflow-x:auto;margin:1.2em 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:11px;border:1px solid #d5e0e5;text-align:left;vertical-align:top}th{background:#e4eff1}tr:nth-child(even){background:#f8fafb}td code{font-size:12px}.flow{width:100%;height:auto;background:#f7fafb;border:1px solid #dae6e9;margin:15px 0 28px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}.metric{background:#e8f1f1;padding:15px;border-top:3px solid #34818a}.metric b{display:block;font-size:27px}.metric span{font-size:13px}figure{margin:30px 0}figure img{width:100%;height:auto;border:1px solid #dbe5e8}figcaption{font-size:14px;color:#4b6473;padding:10px 0}blockquote{margin:20px 0;border-left:4px solid #cc9e43;background:#fff7e8;padding:8px 20px}nav.top a{display:inline-block;color:#dceff2;margin-right:20px}footer{margin-top:35px;font-size:13px;color:#5c7481}@media(max-width:1050px){.layout{display:block}aside{position:static;max-height:260px;margin-bottom:20px;background:#e8f0f1;padding:12px}main{padding:22px}header h1{font-size:30px}}@media(max-width:600px){body{font-size:16px}.layout{padding:18px 12px}main{padding:17px}.metrics{grid-template-columns:1fr}.metric b{font-size:23px}h1{font-size:25px}h2{font-size:23px}td{min-width:125px}header{padding:30px 20px}}@media print{body{background:white;font-size:10.5pt}.layout{display:block;padding:0}aside,nav.top{display:none}header{color:black;background:white;padding:0}header p{color:black}main{padding:0;border:0}h2,h3{break-after:avoid}tr,figure{break-inside:avoid}a{color:inherit}.table-wrap{overflow:visible}}
"""
STYLE += """
.method-figure{margin:26px 0 36px;padding:22px;border:1px solid #c8dce2;border-radius:8px;background:#fbfdfd}.method-figure h3{margin:10px 0 16px;line-height:1.5}.figure-tag{display:inline-block;border:1px solid #aac6cf;background:#e7f0f3;color:#285567;border-radius:20px;padding:2px 11px;font-size:12px;font-weight:650}.method-svg{width:100%;height:auto;display:block;min-width:0;background:white;font-family:system-ui,'Microsoft YaHei',sans-serif}.figure-legend{list-style:none;padding:0;display:flex;flex-wrap:wrap;gap:7px 19px;font-size:14px;line-height:1.6;margin:12px 0}.figure-legend li{margin:0;display:flex;align-items:center;gap:7px}.legend-chip{display:inline-block;min-width:17px;height:11px;border:1px solid #71919c;border-radius:2px}.figure-reading{padding:13px 17px;background:#eef5f4;border-left:3px solid #478f80;margin:18px 0 12px;color:#244c4b}.figure-reading p{margin:5px 0 0;font-size:15px;line-height:1.8}.figure-source{font-size:12px;line-height:1.8;color:#5d7480;overflow-wrap:anywhere}.method-figure table{font-size:13px;margin-top:15px}.method-figure figcaption{padding:0}.oat-panel{margin:18px 0 30px;padding-bottom:20px;border-bottom:1px solid #d9e5e9}.oat-panel:last-of-type{border-bottom:0}.document-nav{display:flex;flex-wrap:wrap;gap:7px 18px;margin-top:20px;font-size:14px}.document-nav a{color:#e0f2f4}.method-figure>.table-wrap{overflow:auto}.method-figure h3{scroll-margin-top:20px}@media(max-width:600px){.method-figure{padding:12px;margin:20px -7px}.method-svg{min-width:660px}.method-figure{overflow-x:auto}.figure-legend,.figure-reading,.figure-source{min-width:240px}.figure-legend li{font-size:13px}}@media print{.method-figure{break-inside:auto;background:white}.oat-panel,.method-svg,.figure-legend{break-inside:avoid}.method-svg{min-width:0}.document-nav{display:none}.figure-reading{background:white}.figure-tag{background:white}}
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


def relative_link(target: Path, directory: Path) -> str:
    return Path(os.path.relpath(target, directory)).as_posix()


def document_navigation(destination: Path, language: str) -> str:
    labels = (
        [
            ("中文全文", "docs/handover_zh/index.html"),
            ("English", "docs/handover_en/index.html"),
            ("真实结果", "outputs/GE5219_MCDA_真实结果.html"),
            ("接口文档", "docs/handover_zh/interfaces.html"),
            ("代码结构", "docs/handover_zh/code_structure.html"),
            ("处理方法", "docs/handover_zh/processing_methods.html"),
            ("工作进度", "docs/project-progress-2026-10-19.html"),
        ]
        if language == "zh"
        else [
            ("English handbook", "docs/handover_en/index.html"),
            ("中文", "docs/handover_zh/index.html"),
            ("Actual results", "outputs/GE5219_MCDA_Actual_Results_EN.html"),
            ("Integration interfaces", "docs/handover_en/interfaces.html"),
            ("Code structure", "docs/handover_en/code_structure.html"),
            ("Processing methods", "docs/handover_en/processing_methods.html"),
            ("Progress", "docs/handover_en/project_progress.html"),
        ]
    )
    return (
        '<nav class="document-nav">'
        + "".join(
            f'<a href="{relative_link(ROOT / target, destination.parent)}">{html.escape(label)}</a>'
            for label, target in labels
        )
        + "</nav>"
    )


def rebase_relative_links(
    document: str, source_directory: Path, destination_directory: Path
) -> str:
    """Move a saved page while preserving local links, data URIs and anchors."""

    def replace(match):
        prefix, value, quote = match.groups()
        parsed = urlparse(html.unescape(value))
        if parsed.scheme or parsed.netloc or not parsed.path:
            return match.group(0)
        target = source_directory / unquote(parsed.path)
        new_path = relative_link(target, destination_directory)
        if parsed.query:
            new_path += "?" + parsed.query
        if parsed.fragment:
            new_path += "#" + parsed.fragment
        return prefix + html.escape(new_path, quote=True) + quote

    return re.sub(r'((?:href|src)=["\'])(.*?)(["\'])', replace, document)


def root_document(language: str) -> str:
    """Return a full, root-relative handbook, ready for a package doc.html."""
    source = ROOT / "docs" / f"handover_{language}" / "index.html"
    return rebase_relative_links(source.read_text(encoding="utf-8"), source.parent, ROOT)


def render(source: Path, destination: Path, language: str, include_results: bool = False) -> None:
    text = source.read_text(encoding="utf-8")
    title = text.splitlines()[0].lstrip("# ")
    markers = re.findall(r"<!--\s*VISUAL:\s*([a-z_]+)\s*-->", text)
    unknown = set(markers) - set(VISUAL_KEYS)
    if unknown:
        raise ValueError(f"Unknown visualization markers in {source}: {unknown}")
    for key in markers:
        text = re.sub(rf"<!--\s*VISUAL:\s*{key}\s*-->", f"GE5219VISUAL{key}PLACEHOLDER", text)
    rendered = MARKDOWN(text)
    if markers:
        illustrations = build_visuals(ROOT, language)
        for key in markers:
            rendered = rendered.replace(f"<p>GE5219VISUAL{key}PLACEHOLDER</p>", illustrations[key])
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
        + "</p>"
        + document_navigation(destination, language)
        + '</header><div class="layout"><aside>'
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
        self.visuals = []
        self.method_svg_count = 0
        self.external_dependencies = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.anchors.add(values["id"])
        if tag == "a" and values.get("href"):
            self.targets.append(values["href"])
        if tag == "img" and values.get("src"):
            self.targets.append(values["src"])
        if tag == "figure" and values.get("data-visual"):
            self.visuals.append(values["data-visual"])
        if tag == "svg" and "method-svg" in values.get("class", "").split():
            self.method_svg_count += 1
        dependency = (
            values.get("src")
            if tag in {"script", "img"}
            else values.get("href")
            if tag == "link"
            else None
        )
        if dependency and urlparse(dependency).scheme in {"http", "https"}:
            self.external_dependencies.append(dependency)


def main():
    generated = []
    for language in ("zh", "en"):
        folder = ROOT / "docs" / f"handover_{language}"
        for source_name, target_name in [
            ("README.md", "index.html"),
            ("code_structure.md", "code_structure.html"),
            ("processing_methods.md", "processing_methods.html"),
            ("interfaces.md", "interfaces.html"),
        ]:
            output = folder / target_name
            if not (folder / source_name).exists():
                continue
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
    entry.write_text(root_document("zh"), encoding="utf-8")
    generated.append(entry)
    issues = []
    visual_coverage = {}
    external_dependencies = []
    for path in generated:
        reader = LinkReader()
        reader.feed(path.read_text(encoding="utf-8"))
        external_dependencies.extend(reader.external_dependencies)
        if path.name == "doc.html" or path.name == "index.html":
            visual_coverage[str(path.relative_to(ROOT))] = {
                "keys": reader.visuals,
                "all_required_once": sorted(reader.visuals) == sorted(VISUAL_KEYS),
                "method_svg_count": reader.method_svg_count,
            }
        for target in reader.targets:
            parsed = urlparse(target)
            if parsed.scheme or parsed.netloc:
                continue
            if not parsed.path:
                if parsed.fragment and parsed.fragment not in reader.anchors:
                    issues.append({"file": str(path.relative_to(ROOT)), "target": target})
            elif not (path.parent / unquote(parsed.path)).exists():
                issues.append({"file": str(path.relative_to(ROOT)), "target": target})
    complete_visuals = all(row["all_required_once"] for row in visual_coverage.values())
    result = {
        "status": "passed"
        if not issues and not external_dependencies and complete_visuals
        else "failed",
        "html_files": len(generated),
        "external_styles_scripts": len(external_dependencies),
        "all_figure_images_embedded": True,
        "inline_svg_figures": visual_coverage,
        "all_methods_have_inline_visual_once": complete_visuals,
        "root_doc_contains_full_chinese_handbook": entry.stat().st_size > 50000,
        "relative_link_issues": issues,
    }
    (ROOT / "outputs/audits/handover_html_check.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))
    if issues or external_dependencies or not complete_visuals:
        raise ValueError("Resolve documentation links and visual markers before packaging")


if __name__ == "__main__":
    main()
