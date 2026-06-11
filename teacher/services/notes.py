import re


_FENCED_MARKDOWN_WRAPPER = re.compile(r"\A\s*```(?:markdown|md)\s*\n([\s\S]*?)\n```\s*\Z", re.IGNORECASE)


def normalize_lecture_note_content(content):
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    wrapper_match = _FENCED_MARKDOWN_WRAPPER.match(text)
    if wrapper_match:
        text = wrapper_match.group(1).strip()

    text = text.replace("\u00a0", " ")
    text = re.sub(r"(?m)^[ \t]*([*+-])[ \t]{2,}", r"\1 ", text)
    text = re.sub(r"(?m)^([ \t]*#{1,6})([^\s#])", r"\1 \2", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # KaTeX handles standard delimiters; these replacements fix common copied AI output.
    text = text.replace("\\\\(", "\\(").replace("\\\\)", "\\)")
    text = text.replace("\\\\[", "\\[").replace("\\\\]", "\\]")
    text = re.sub(r"(?<!\\)\\begin\{equation\}", r"\\[", text)
    text = re.sub(r"(?<!\\)\\end\{equation\}", r"\\]", text)

    return text.strip()


def default_lecture_note_title(title, classroom):
    clean_title = (title or "").strip()
    if clean_title:
        return clean_title[:255]
    return f"Lecture Notes - {classroom.name}"[:255]
