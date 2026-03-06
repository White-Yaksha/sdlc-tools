"""Tests for the HTML converter."""

from __future__ import annotations

from sdlc_tools.html import convert_markdown_to_html


class TestConvertMarkdownToHtml:
    """Verify Markdown → HTML conversion."""

    def test_headings(self) -> None:
        md = "# Title\n## Subtitle\n### Sub-subtitle"
        html = convert_markdown_to_html(md)
        assert "<h2>Title</h2>" in html
        assert "<h3>Subtitle</h3>" in html
        assert "<h4>Sub-subtitle</h4>" in html

    def test_bold_and_italic(self) -> None:
        md = "This is **bold** and *italic* text."
        html = convert_markdown_to_html(md)
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_bullet_points(self) -> None:
        md = "- Item one\n- Item two"
        html = convert_markdown_to_html(md)
        assert "<li>Item one</li>" in html
        assert "<li>Item two</li>" in html
        assert "<ul>" in html

    def test_inline_code(self) -> None:
        md = "Use `git diff` to see changes."
        html = convert_markdown_to_html(md)
        assert "<code>git diff</code>" in html

    def test_code_block(self) -> None:
        md = "```python\nprint('hello')\n```"
        html = convert_markdown_to_html(md)
        assert "<pre><code>" in html
        assert "print('hello')" in html

    def test_horizontal_rule(self) -> None:
        md = "Above\n---\nBelow"
        html = convert_markdown_to_html(md)
        assert "<hr/>" in html

    def test_custom_title_and_marker(self) -> None:
        md = "## Summary\nSome text."
        html = convert_markdown_to_html(md, title="Custom Title", marker="<!-- CUSTOM -->")
        assert "Custom Title" in html
        assert "<!-- CUSTOM -->" in html

    def test_wrapper_structure(self) -> None:
        html = convert_markdown_to_html("Hello")
        assert html.startswith("<div")
        assert html.endswith("</div>")
        assert "<!-- AI-SDLC-REPORT -->" in html

    def test_simple_table(self) -> None:
        md = "| Col A | Col B |\n|---|---|\n| val1 | val2 |"
        html = convert_markdown_to_html(md)
        assert "<table>" in html
        assert "<th>Col A</th>" in html
        assert "<td>val1</td>" in html
