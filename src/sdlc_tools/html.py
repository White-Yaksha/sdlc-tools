"""Markdown to styled HTML converter for PR comments."""

from __future__ import annotations

import re

_DEFAULT_TITLE = "\U0001f50d AI Code Impact Report"
_DEFAULT_MARKER = "<!-- AI-SDLC-REPORT -->"


def convert_markdown_to_html(
    markdown_text: str,
    *,
    title: str = _DEFAULT_TITLE,
    marker: str = _DEFAULT_MARKER,
    subtitle: str = "",
) -> str:
    """Convert Markdown to HTML wrapped in a styled container.

    Uses regex-based conversion (no external dependency). Handles:
    headings, bold, italic, inline code, fenced code blocks, bullet
    points, horizontal rules, and simple pipe tables.
    """
    html = markdown_text

    # Fenced code blocks (``` ... ```).
    html = re.sub(
        r"```(\w*)\n(.*?)```",
        r"<pre><code>\2</code></pre>",
        html,
        flags=re.DOTALL,
    )

    # Inline code.
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)

    # Horizontal rules.
    html = re.sub(r"^-{3,}$", "<hr/>", html, flags=re.MULTILINE)

    # Headings (order matters: ### before ## before #).
    html = re.sub(r"^### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)
    html = re.sub(r"^## (.+)$", r"<h3>\1</h3>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)

    # Bold and italic.
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

    # Simple pipe tables.
    html = _convert_tables(html)

    # Bullet points → list items.
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    # Wrap consecutive <li> in <ul>.
    html = re.sub(r"((?:<li>.*?</li>\n?)+)", r"<ul>\1</ul>", html)

    # Paragraphs — wrap non-tag, non-empty lines.
    lines = html.split("\n")
    processed: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("<"):
            processed.append(f"<p>{stripped}</p>")
        else:
            processed.append(line)
    html = "\n".join(processed)

    subtitle_html = (
        f'  <p style="color: #888; font-size: 0.85em; margin-top: -8px;">'
        f"{subtitle}</p>\n"
        if subtitle else ""
    )

    return (
        '<div style="font-family: Arial, sans-serif; line-height: 1.6;">\n'
        f"  <h2>{title}</h2>\n"
        f"{subtitle_html}"
        f"  {marker}\n"
        f"  {html}\n"
        "</div>"
    )


def _convert_tables(text: str) -> str:
    """Convert simple pipe-delimited Markdown tables to HTML tables."""
    lines = text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Detect table start: line with pipes and next line is separator (|---|---|).
        if (
            "|" in line
            and i + 1 < len(lines)
            and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip())
        ):
            # Parse header.
            headers = [c.strip() for c in line.strip("|").split("|")]
            table_html = "<table><thead><tr>"
            for h in headers:
                table_html += f"<th>{h}</th>"
            table_html += "</tr></thead><tbody>"
            i += 2  # Skip header + separator.
            # Parse rows.
            while i < len(lines) and "|" in lines[i]:
                cols = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                table_html += "<tr>"
                for c in cols:
                    table_html += f"<td>{c}</td>"
                table_html += "</tr>"
                i += 1
            table_html += "</tbody></table>"
            result.append(table_html)
        else:
            result.append(lines[i])
            i += 1
    return "\n".join(result)
