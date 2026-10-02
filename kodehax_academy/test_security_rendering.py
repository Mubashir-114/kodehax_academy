import json
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

from teacher.services import course_readme


class Attributes(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.links.extend((name, value) for name, value in attrs if name in {"href", "src"})


class ReadmeSecurityTests(SimpleTestCase):
    def test_protocol_policy_matches_shared_corpus(self):
        cases = json.loads((settings.BASE_DIR / "tests/url_policy_cases.json").read_text(encoding="utf-8"))
        for value in cases["safe"]:
            with self.subTest(value=value):
                self.assertTrue(course_readme.is_safe_url(value))
        for value in cases["unsafe"]:
            with self.subTest(value=value):
                self.assertFalse(course_readme.is_safe_url(value))

    def test_unsafe_html_urls_are_removed_in_every_path(self):
        vectors = ["javascript:synthetic()", "javascript&#58;synthetic()", "javascript&amp;colon;synthetic()",
                   "&#106;avascript:synthetic()", "%6aavascript%253Asynthetic()", "data:text/html,synthetic",
                   "java&#10;script:synthetic()", "vbscript:synthetic()", "https://[broken"]
        for value in vectors:
            html = f'<a href="{value}">Course</a><img src="{value}" alt="Diagram">'
            for mode in ("package", "fallback", "mixed"):
                with self.subTest(value=value, mode=mode):
                    if mode == "fallback":
                        with patch.object(course_readme, "_render_markdown_with_packages", return_value=None):
                            result = course_readme.render_course_readme_html(html)
                    else:
                        result = course_readme.render_course_readme_html(("# Heading\n" if mode == "mixed" else "") + html)
                    parsed = Attributes()
                    parsed.feed(result)
                    self.assertEqual(parsed.links, [])
                    self.assertIn("Course", result)

    def test_unsafe_markdown_urls_do_not_survive_package_or_fallback(self):
        for content in ("[Course](javascript:synthetic)", "![Diagram](data:text/html,synthetic)",
                        "[Course](javascript%3Asynthetic)", "![Diagram](file:///synthetic)"):
            for fallback in (False, True):
                with self.subTest(content=content, fallback=fallback):
                    if fallback:
                        with patch.object(course_readme, "_render_markdown_with_packages", return_value=None):
                            result = course_readme.render_course_readme_html(content)
                    else:
                        result = course_readme.render_course_readme_html(content)
                    parsed = Attributes()
                    parsed.feed(result)
                    self.assertEqual(parsed.links, [])

    def test_legitimate_links_formatting_and_code_remain(self):
        content = '# Overview\n\n**Important** [Course](https://example.com/lesson)\n\n```python\nprint("<safe>")\n```'
        for fallback in (False, True):
            with self.subTest(fallback=fallback):
                if fallback:
                    with patch.object(course_readme, "_render_markdown_with_packages", return_value=None):
                        result = course_readme.render_course_readme_html(content)
                else:
                    result = course_readme.render_course_readme_html(content)
                self.assertIn("<h1>", result)
                self.assertIn("<strong>Important</strong>", result)
                self.assertIn('href="https://example.com/lesson"', result)
                self.assertIn("&lt;safe&gt;", result)

    def test_images_disallow_mailto_and_data_but_keep_https(self):
        self.assertFalse(course_readme.is_safe_url("mailto:student@example.com", image=True))
        self.assertFalse(course_readme.is_safe_url("data:image/png;base64,synthetic", image=True))
        result = course_readme.render_course_readme_html('<img src="https://example.com/diagram.png" alt="Diagram">')
        self.assertIn('src="https://example.com/diagram.png"', result)

    def test_nested_encoding_limit_fails_closed(self):
        self.assertFalse(course_readme.is_safe_url("javascript" + "%25" * 10 + "3Asynthetic()"))


@override_settings(ROOT_URLCONF="kodehax_academy.urls")
class ChartSecurityTests(SimpleTestCase):
    def test_real_template_escapes_script_breakout_and_preserves_arrays(self):
        marker = '</script><script>synthetic()</script>&\u2028'
        fields = ("score_progression_labels", "score_progression_values", "assignment_score_labels",
                  "assignment_score_values", "submission_trend_labels", "submission_trend_values")
        context = {name: [marker] if name.endswith("labels") else [12.5, 0, 100] for name in fields}
        html = render_to_string("student/performance.html", context)
        self.assertNotIn(marker, html)
        import re
        for name in fields:
            identifier = name.replace("_", "-")
            data = re.search(r'<script id="' + identifier + r'" type="application/json">(.*?)</script>', html, re.S).group(1)
            self.assertEqual(json.loads(data), context[name])
            self.assertNotIn("<", data)
            self.assertIn('JSON.parse(document.getElementById("' + identifier + '").textContent)', html)

    def test_all_client_markdown_templates_use_shared_safe_renderer(self):
        templates = list((settings.BASE_DIR / "templates").rglob("*.html"))
        renderers = [path for path in templates if "marked.parse" in path.read_text(encoding="utf-8") or
                     "KodehaxMarkdown.render" in path.read_text(encoding="utf-8")]
        self.assertEqual(len(renderers), 10)
        for path in renderers:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("js/safe_markdown.js", text)
                self.assertIn("KodehaxMarkdown.render", text)
                self.assertNotIn(": parsed", text)
