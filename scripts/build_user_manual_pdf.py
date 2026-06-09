"""Build a polished PDF from the user manual markdown using WeasyPrint."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import markdown
from weasyprint import HTML, CSS

ROOT = Path(__file__).resolve().parent.parent.parent  # workspace root
MD_PATH = ROOT / "docs" / "MANUAL_DO_USUARIO.md"
PDF_PATH = ROOT / "docs" / "MANUAL_DO_USUARIO.pdf"


CSS_STYLE = """
@page {
    size: A4;
    margin: 22mm 18mm 22mm 18mm;
    @top-left {
        content: "Konis Automação — Manual do Usuário";
        font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
        font-size: 9pt;
        color: #6b7280;
    }
    @top-right {
        content: "v1.0 · Maio/2026";
        font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
        font-size: 9pt;
        color: #6b7280;
    }
    @bottom-center {
        content: "Página " counter(page) " de " counter(pages);
        font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
        font-size: 9pt;
        color: #6b7280;
    }
}

@page :first {
    margin: 0;
    @top-left { content: none; }
    @top-right { content: none; }
    @bottom-center { content: none; }
}

@page toc {
    @top-left { content: "Sumário"; }
    @top-right { content: "Konis Automação"; }
}

* { box-sizing: border-box; }

html { font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; font-size: 10.5pt; color: #1f2937; line-height: 1.55; }
body { margin: 0; padding: 0; }

/* ============ COVER ============ */
.cover {
    page: cover;
    page-break-after: always;
    height: 297mm;
    width: 210mm;
    background: linear-gradient(135deg, #0b3a82 0%, #1e3a8a 45%, #312e81 100%);
    color: #ffffff;
    padding: 38mm 24mm 28mm 24mm;
    position: relative;
    overflow: hidden;
}
.cover::after {
    content: "";
    position: absolute; bottom: -120mm; left: -60mm; width: 240mm; height: 240mm;
    background: radial-gradient(circle, rgba(59,130,246,0.25), transparent 65%);
    pointer-events: none;
}
.cover-top { position: relative; z-index: 1; }
.cover-brand { font-size: 13pt; letter-spacing: 7px; text-transform: uppercase; color: #93c5fd; font-weight: 700; margin-bottom: 24mm; }
.cover-title { font-size: 46pt; font-weight: 800; line-height: 1.0; margin: 0 0 6mm 0; letter-spacing: -1.5px; color: #ffffff; }
.cover-rule { width: 60mm; height: 4px; background: #f59e0b; border: none; margin: 8mm 0 12mm 0; }
.cover-subtitle { font-size: 15pt; font-weight: 300; color: #e0e7ff; max-width: 145mm; line-height: 1.45; margin: 0; }
.cover-modules { margin-top: 18mm; position: relative; z-index: 1; }
.cover-modules .badge {
    display: inline-block;
    background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.3);
    padding: 8px 18px; border-radius: 999px; font-size: 11pt; font-weight: 500;
    margin-right: 6mm;
}
.cover-footer {
    position: absolute; bottom: 28mm; left: 24mm; right: 24mm;
    color: #c7d2fe; font-size: 10pt; z-index: 1;
}
.cover-footer-row { display: flex; justify-content: space-between; align-items: flex-end; }
.cover-version { text-align: right; }
.cover-version strong { display: block; font-size: 16pt; color: #ffffff; font-weight: 700; }

/* ============ TYPOGRAPHY ============ */
h1, h2, h3, h4 { font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; color: #0b3a82; font-weight: 700; line-height: 1.25; }
h1 { font-size: 24pt; margin-top: 0; padding-bottom: 8px; border-bottom: 3px solid #0b3a82; page-break-before: always; page-break-after: avoid; }
h1:first-of-type { page-break-before: auto; }
h2 { font-size: 16pt; margin-top: 22px; margin-bottom: 10px; padding-bottom: 4px; border-bottom: 1px solid #e5e7eb; color: #1e3a8a; page-break-after: avoid; }
h3 { font-size: 12.5pt; margin-top: 16px; margin-bottom: 6px; color: #1e3a8a; page-break-after: avoid; }
h4 { font-size: 11pt; margin-top: 12px; margin-bottom: 4px; color: #374151; page-break-after: avoid; }
p { margin: 6px 0 8px; text-align: justify; hyphens: auto; }
strong { color: #111827; }
em { color: #374151; }
hr { border: none; border-top: 1px dashed #d1d5db; margin: 18px 0; }

/* ============ LISTS ============ */
ul, ol { margin: 6px 0 10px; padding-left: 22px; }
ul li, ol li { margin: 3px 0; }
li > p { margin: 2px 0; }

/* ============ CODE ============ */
code { font-family: 'JetBrains Mono', 'Consolas', monospace; font-size: 9pt; background: #f3f4f6; color: #0b3a82; padding: 1px 5px; border-radius: 3px; }
pre { background: #0f172a; color: #e2e8f0; padding: 12px 16px; border-radius: 6px; overflow-x: auto; font-size: 9pt; line-height: 1.5; page-break-inside: avoid; }
pre code { background: transparent; color: inherit; padding: 0; font-size: 9pt; }

/* ============ TABLES ============ */
table { width: 100%; border-collapse: collapse; margin: 10px 0 14px; font-size: 9.5pt; page-break-inside: avoid; }
thead { background: #0b3a82; color: #ffffff; }
thead th { padding: 8px 10px; text-align: left; font-weight: 600; font-size: 9.5pt; border: 1px solid #0b3a82; }
tbody td { padding: 7px 10px; border: 1px solid #e5e7eb; vertical-align: top; }
tbody tr:nth-child(even) td { background: #f9fafb; }
tbody tr:hover td { background: #eff6ff; }

/* ============ BLOCKQUOTES (call-outs) ============ */
blockquote {
    margin: 12px 0;
    padding: 10px 14px 10px 16px;
    border-left: 4px solid #2563eb;
    background: #eff6ff;
    color: #1e3a8a;
    border-radius: 0 6px 6px 0;
    page-break-inside: avoid;
}
blockquote p { margin: 2px 0; }

/* ============ TOC ============ */
.toc { page: toc; page-break-after: always; }
.toc h2 { border: none; color: #0b3a82; font-size: 22pt; margin-bottom: 18px; }
.toc ol { list-style: none; padding-left: 0; counter-reset: toc-item; }
.toc ol li {
    counter-increment: toc-item;
    margin: 4px 0;
    padding: 8px 6px;
    border-bottom: 1px dotted #cbd5e1;
    font-size: 11pt;
}
.toc ol li::before {
    content: counter(toc-item, decimal-leading-zero);
    color: #2563eb; font-weight: 700; margin-right: 14px;
    display: inline-block; width: 28px;
}

/* ============ SECTION CHIPS ============ */
h2 { position: relative; }

/* Avoid orphan headings */
h1 + p, h2 + p, h3 + p { page-break-before: avoid; }
"""


COVER_HTML = """
<section class="cover">
  <div class="cover-top">
    <div class="cover-brand">Konis Automação</div>
    <h1 class="cover-title">Manual<br/>do Usuário</h1>
    <hr class="cover-rule"/>
    <p class="cover-subtitle">
      Sistema de Geração Automatizada de Laudos Técnicos de Segurança contra Atmosferas Explosivas.
    </p>
    <div class="cover-modules">
      <span class="badge">DHA · Dust Hazard Analysis</span>
      <span class="badge">Classificação de Áreas · IEC 60079</span>
    </div>
  </div>
  <div class="cover-footer">
    <div class="cover-footer-row">
      <div>
        Documento de uso interno<br/>
        Konis Engenharia &middot; Konis Ex
      </div>
      <div class="cover-version">
        <strong>Versão 1.0</strong>
        Maio / 2026
      </div>
    </div>
  </div>
</section>
"""


def build_toc_html(md_text: str) -> str:
    """Extract '## N. Title' headings to build a styled TOC page."""
    items = []
    for line in md_text.splitlines():
        m = re.match(r"^##\s+(\d+)\.\s+(.+?)\s*$", line)
        if m:
            num, title = m.group(1), m.group(2)
            items.append((num, title))
    lis = "\n".join(
        f'<li>{title}</li>' for _, title in items
    )
    return f'<section class="toc"><h2>Sumário</h2><ol>{lis}</ol></section>'


def main() -> int:
    md_text = MD_PATH.read_text(encoding="utf-8")

    # Strip the original markdown TOC block (between "## Sumário" and the next "---")
    md_text = re.sub(
        r"## Sumário.*?\n---\n",
        "",
        md_text,
        count=1,
        flags=re.DOTALL,
    )
    # Also remove the very first H1 since we use a custom cover
    md_text = re.sub(
        r"^# Manual do Usuário.*?\n(?:\*\*.*?\*\*\n)*\n*---\n",
        "",
        md_text,
        count=1,
        flags=re.DOTALL,
    )

    html_body = markdown.markdown(
        md_text,
        extensions=[
            "tables",
            "fenced_code",
            "sane_lists",
            "pymdownx.tilde",
            "pymdownx.tasklist",
            "attr_list",
        ],
    )

    toc_html = build_toc_html(MD_PATH.read_text(encoding="utf-8"))

    full_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><title>Manual do Usuário — Konis Automação</title></head>
<body>
{COVER_HTML}
{toc_html}
<main>
{html_body}
</main>
</body>
</html>
"""

    HTML(string=full_html, base_url=str(ROOT)).write_pdf(
        target=str(PDF_PATH),
        stylesheets=[CSS(string=CSS_STYLE)],
    )
    print(f"PDF gerado em: {PDF_PATH}")
    print(f"Tamanho: {PDF_PATH.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
