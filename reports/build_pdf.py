"""
Build reports/final_report.pdf from reports/final_report.md.

Run from the project root after:
    python reports/make_figures.py

The Markdown file remains the source of the report. This script converts it to HTML and then creates the PDF using an available Chromium-based browser.

Set the BROWSER environment variable only if a browser is not found automatically.

Markdown conversion uses the `markdown` package when available and falls back to `mistune`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "final_report.md"
TARGET = ROOT / "reports" / "final_report.pdf"

CSS = """
@page { size: A4; margin: 15mm 16mm 15mm 16mm; }
body { font-family: "Segoe UI", "DejaVu Sans", Arial, sans-serif; font-size: 9.3pt; line-height: 1.4; color: #17181a; }
h1 { font-size: 21pt; margin: 0 0 6pt; letter-spacing: -0.01em; }
h2 { font-size: 14pt; margin: 16pt 0 5pt; padding-top: 6pt; border-top: 1px solid #d8d6d0; break-after: avoid; }
h3 { font-size: 11pt; margin: 12pt 0 4pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
ul, ol { padding-left: 18pt; }
li { margin: 2pt 0; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9pt; break-inside: avoid; }
th { text-align: left; border-bottom: 1.5px solid #8b8983; padding: 4pt 6pt; }
td { border-bottom: 1px solid #e4e3df; padding: 3.5pt 6pt; vertical-align: top; }
img { display: block; max-width: 84%; max-height: 82mm; margin: 8pt auto 2pt; break-inside: avoid; }
p:has(> img) { break-inside: avoid; break-after: avoid; }
em { color: #3f3e3b; }
code { font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 8.6pt; background: #f3f2ee; padding: 0 2px; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3px solid #2a78d6; background: #f6f8fc; }
a { color: #1f5fae; text-decoration: none; }
.keep { break-inside: avoid; page-break-inside: avoid; }
/* A heading reserves space below itself, so it moves to the next page instead of ending a page alone. */
h2, h3 { break-inside: avoid; }
h2::after { content: ""; display: block; height: 45mm; margin-bottom: -45mm; }
h3::after { content: ""; display: block; height: 35mm; margin-bottom: -35mm; }
"""


def to_html(markdown_text: str) -> str:
    try:
        import markdown
        body = markdown.markdown(markdown_text, extensions=["tables"])
    except ImportError:
        import mistune
        body = mistune.create_markdown(plugins=["table"], escape=False)(markdown_text)
    body = keep_together(body)
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Final report</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")


def keep_together(body: str) -> str:
    """Layout only: keep blocks together that a reader expects on one page.

    A figure stays with its caption and the conclusion stays in one piece;
    headings keep space below them through the stylesheet. The text itself is
    not changed.
    """
    import re

    def wrap(match: "re.Match[str]") -> str:
        return f'<div class="keep">{match.group(0)}</div>'

    last = body.rfind("<h2>")
    if last != -1:
        body = body[:last] + '<div class="keep">' + body[last:] + "</div>"
        head, tail = body[:last], body[last:]
    else:
        head, tail = body, ""
    head = re.sub(r"<p><img[^>]*></p>\s*<p><em>.*?</em></p>", wrap, head, flags=re.S)
    # A table stays with the heading or short lead-in line that introduces it.
    head = re.sub(r"<h3>[^<]*</h3>\s*<p>(?:(?!</p>).)*</p>\s*(?:<!--.*?-->\s*)?<table>.*?</table>", wrap, head, flags=re.S)
    head = re.sub(r"<p><strong>[^<]*</strong></p>\s*<table>.*?</table>", wrap, head, flags=re.S)
    return head + tail


def find_browser() -> str:
    candidates = [os.environ.get("BROWSER", ""), "chrome", "google-chrome", "chromium", "chromium-browser", "msedge",
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                  "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"]
    for candidate in candidates:
        if candidate and (shutil.which(candidate) or Path(candidate).is_file()):
            return shutil.which(candidate) or candidate
    sys.exit("No Chromium-based browser found; set BROWSER to the path of Chrome or Edge.")


def main() -> None:
    html = to_html(SOURCE.read_text(encoding="utf-8"))
    # The HTML sits next to the Markdown so the relative image paths resolve.
    with tempfile.NamedTemporaryFile("w", suffix=".html", dir=SOURCE.parent, delete=False, encoding="utf-8") as page:
        page.write(html)
    try:
        subprocess.run([find_browser(), "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                        f"--print-to-pdf={TARGET}", Path(page.name).as_uri()], check=True, capture_output=True)
    finally:
        Path(page.name).unlink()
    print("wrote", TARGET.relative_to(ROOT))


if __name__ == "__main__":
    main()
