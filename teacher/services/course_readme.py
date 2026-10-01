from __future__ import annotations

from html import escape, unescape
from html.parser import HTMLParser
import re
import unicodedata
from urllib.parse import unquote, urlsplit


def is_safe_url(value: str, *, image: bool = False) -> bool:
    """One conservative URI policy for package, HTML and Markdown paths."""
    candidate = value.strip()
    for _ in range(8):
        try:
            decoded = unquote(unescape(candidate), errors="strict")
        except UnicodeError:
            return False
        if decoded == candidate:
            break
        candidate = decoded
    else:
        return False
    if not candidate or "\\" in candidate:
        return False
    if any(unicodedata.category(char).startswith("C") for char in candidate):
        return False
    candidate = unicodedata.normalize("NFKC", candidate)
    # Browsers tolerate whitespace/control tricks in scheme spellings.
    compact = "".join(char for char in candidate if not char.isspace())
    try:
        parsed = urlsplit(compact)
        if parsed.scheme:
            allowed = {"http", "https"} if image else {"http", "https", "mailto"}
            if parsed.scheme.lower() not in allowed:
                return False
            if parsed.scheme.lower() in {"http", "https"} and not parsed.hostname:
                return False
        elif ":" in compact.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]:
            return False
        if parsed.netloc:
            if not parsed.hostname or parsed.username is not None or parsed.password is not None:
                return False
            parsed.port  # Reject malformed authorities/ports.
        return not compact.startswith("///")
    except (ValueError, UnicodeError):
        return False


DEFAULT_EMPTY_README = """# Course README

This classroom does not have a README yet.

Teachers can add an overview, learning goals, resources, setup steps, and important notes here.
"""

IMAGE_ONLY_PATTERN = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?:\s+\"[^\"]*\")?\)$")
INLINE_IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_LINK_PATTERN = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<href>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_TAG_PATTERN = re.compile(r"<[a-zA-Z][^>]*>")
MARKDOWN_BLOCK_PATTERN = re.compile(r"(?m)^\s{0,3}(#{1,6}\s+|[-*]\s+|```)")

ALLOWED_HTML_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

ALLOWED_HTML_ATTRIBUTES = {
    "a": {"href", "title", "target", "rel"},
    "div": {"align", "class"},
    "h1": {"align", "class"},
    "h2": {"align", "class"},
    "h3": {"align", "class"},
    "h4": {"align", "class"},
    "h5": {"align", "class"},
    "h6": {"align", "class"},
    "img": {"src", "alt", "title", "width", "height", "align", "loading", "referrerpolicy"},
    "p": {"align", "class"},
    "span": {"class"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align"},
}


class _BasicHtmlSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def _format_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed = ALLOWED_HTML_ATTRIBUTES.get(tag, set())
        cleaned: list[str] = []
        for key, value in attrs:
            if key not in allowed or value is None:
                continue
            if key in {"href", "src"} and not is_safe_url(value, image=key == "src"):
                continue
            cleaned.append(f' {key}="{escape(value, quote=True)}"')
        return "".join(cleaned)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_HTML_TAGS:
            return
        self.parts.append(f"<{tag}{self._format_attrs(tag, attrs)}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_HTML_TAGS:
            return
        self.parts.append(f"<{tag}{self._format_attrs(tag, attrs)}>")

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_HTML_TAGS or tag in {"br", "hr", "img"}:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.parts.append(escape(data))

    def get_html(self) -> str:
        return "".join(self.parts)


def _sanitize_basic_html(text: str) -> str:
    parser = _BasicHtmlSanitizer()
    parser.feed(text or "")
    parser.close()
    return parser.get_html()


def _render_inline_markdown(text: str) -> str:
    escaped = _sanitize_basic_html(text) if HTML_TAG_PATTERN.search(text) else escape(text)

    def replace_image(match: re.Match[str]) -> str:
        alt = escape(match.group("alt"))
        if not is_safe_url(match.group("src"), image=True):
            return alt
        src = escape(match.group("src"), quote=True)
        return f'<img src="{src}" alt="{alt}" loading="lazy" referrerpolicy="no-referrer">'

    def replace_link(match: re.Match[str]) -> str:
        label = escape(match.group("label"))
        if not is_safe_url(match.group("href")):
            return label
        href = escape(match.group("href"), quote=True)
        return f'<a href="{href}" target="_blank" rel="noopener noreferrer">{label}</a>'

    escaped = INLINE_IMAGE_PATTERN.sub(replace_image, escaped)
    escaped = INLINE_LINK_PATTERN.sub(replace_link, escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _fallback_markdown_to_html(content: str) -> str:
    lines = (content or "").splitlines()
    parts: list[str] = []
    paragraph_lines: list[str] = []
    list_items: list[str] = []
    in_code_block = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph_lines:
            return
        text = " ".join(part.strip() for part in paragraph_lines if part.strip())
        if text:
            parts.append(f"<p>{_render_inline_markdown(text)}</p>")
        paragraph_lines.clear()

    def flush_list() -> None:
        if not list_items:
            return
        parts.append("<ul>" + "".join(f"<li>{_render_inline_markdown(item)}</li>" for item in list_items) + "</ul>")
        list_items.clear()

    def flush_code_block() -> None:
        if not code_lines:
            parts.append("<pre><code></code></pre>")
        else:
            parts.append("<pre><code>" + "\n".join(code_lines) + "</code></pre>")
        code_lines.clear()

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code_block:
                flush_code_block()
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(escape(line))
            continue

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            flush_list()
            parts.append("<hr>")
            continue

        if HTML_TAG_PATTERN.search(stripped):
            flush_paragraph()
            flush_list()
            parts.append(_sanitize_basic_html(stripped))
            continue

        if stripped.startswith("#"):
            flush_paragraph()
            flush_list()
            level = min(len(stripped) - len(stripped.lstrip("#")), 6)
            heading = stripped[level:].strip()
            if heading:
                parts.append(f"<h{level}>{_render_inline_markdown(heading)}</h{level}>")
            continue

        image_match = IMAGE_ONLY_PATTERN.match(stripped)
        if image_match:
            flush_paragraph()
            flush_list()
            alt = escape(image_match.group("alt"))
            src = escape(image_match.group("src"), quote=True)
            parts.append(
                f'<p><img src="{src}" alt="{alt}" loading="lazy" referrerpolicy="no-referrer"></p>'
            )
            continue

        if stripped.startswith(("- ", "* ")):
            flush_paragraph()
            list_items.append(stripped[2:].strip())
            continue

        paragraph_lines.append(stripped)

    flush_paragraph()
    flush_list()
    if in_code_block:
      flush_code_block()

    return _sanitize_basic_html("".join(parts)) or "<p>No README available yet.</p>"


def _render_markdown_with_packages(content: str) -> str | None:
    try:
        import markdown
        import bleach
    except ImportError:
        return None

    rendered = markdown.markdown(
        content or "",
        extensions=[
            "fenced_code",
            "tables",
            "codehilite",
            "sane_lists",
        ],
    )

    allowed_tags = set(bleach.sanitizer.ALLOWED_TAGS).union(
        {
            "p",
            "pre",
            "code",
            "div",
            "span",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "table",
            "thead",
            "tbody",
            "tr",
            "th",
            "td",
            "blockquote",
            "hr",
            "ul",
            "ol",
            "li",
            "img",
        }
    )
    allowed_attributes = {
        "*": ["class", "id", "align"],
        "a": ["href", "title", "target", "rel"],
        "img": ["src", "alt", "title", "loading", "referrerpolicy", "width", "height", "align"],
        "code": ["class"],
        "span": ["class"],
        "div": ["class", "align"],
        "th": ["colspan", "rowspan", "align"],
        "td": ["colspan", "rowspan", "align"],
    }
    def allowed_attribute(tag, name, value):
        permitted = name in allowed_attributes.get(tag, []) or name in allowed_attributes["*"]
        return permitted and (name not in {"href", "src"} or is_safe_url(value, image=name == "src"))

    def clean(html):
        return bleach.clean(html, tags=allowed_tags, attributes=allowed_attribute,
                            protocols={"http", "https", "mailto"}, strip=True)

    # Linkification creates new attributes; apply the same policy afterward.
    return clean(bleach.linkify(clean(rendered or ""))) or "<p>No README available yet.</p>"


def render_course_readme_html(content: str | None) -> str:
    markdown_source = (content or "").strip() or DEFAULT_EMPTY_README
    has_html = bool(HTML_TAG_PATTERN.search(markdown_source))
    has_markdown_blocks = bool(MARKDOWN_BLOCK_PATTERN.search(markdown_source))

    if has_html and has_markdown_blocks:
        return _fallback_markdown_to_html(markdown_source)

    package_rendered = _render_markdown_with_packages(markdown_source)
    if package_rendered is not None:
        return package_rendered
    if has_html:
        return _sanitize_basic_html(markdown_source)
    return _fallback_markdown_to_html(markdown_source)
