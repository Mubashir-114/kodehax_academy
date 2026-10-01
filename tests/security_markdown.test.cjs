/* Offline DOM/controller probes: no browser, CDN, credentials or network access. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const helper = fs.readFileSync(path.join(root, "static/js/safe_markdown.js"), "utf8");
const corpus = JSON.parse(fs.readFileSync(path.join(__dirname, "url_policy_cases.json"), "utf8"));
const templates = ["course/readme_view.html", "course/readme_edit.html", "student/class_detail.html",
  "teacher/assignment_detail.html", "teacher/grade_code_submission.html", "teacher/grade_file_submission.html",
  "teacher/ai_tools.html", "student/assignment/submit_assignment.html", "student/assignment/submit_code.html",
  "student/assignment/view_assignment.html"];
const source = '<img src="synthetic" onerror="synthetic()">\n<script>synthetic()</script>\n**Lesson**';
let probes = 0;

function setup(mode) {
  const writes = [];
  const output = {
    set innerHTML(value) { writes.push(["html", value]); },
    set textContent(value) { writes.push(["text", value]); },
    querySelectorAll() { return []; },
    classList: { contains() { return true; }, add() {}, remove() {}, toggle() {} },
    addEventListener() {},
  };
  const raw = { value: source, classList: { contains() { return true; } }, addEventListener() {} };
  output.nextElementSibling = raw;
  output.parentElement = { querySelector() { return raw; } };
  const context = { URL, console: { warn() {} }, WeakSet,
    document: { cookie: "", getElementById(id) {
      if (["readme-view-output", "readme-preview", "class-readme-output", "ai-output-render"].includes(id)) return output;
      if (["readme-view-raw", "readme-editor", "class-readme-raw", "ai-output-raw"].includes(id)) return raw;
      if (["readme-save-btn", "readme-save-status"].includes(id)) return output;
      return null;
    }, querySelector() { return null; }, querySelectorAll(selector) {
      return [".ai-output-render", "[data-note-render]"].includes(selector) ? [output] : [];
    } },
  };
  context.window = context;
  if (mode !== "no-marked") context.marked = {
    setOptions() {}, parse() { if (mode === "parse-error") throw Error("synthetic parse error"); return "<p>parsed lesson</p>"; }
  };
  if (mode !== "no-purifier") context.DOMPurify = {
    addHook(name, hook) { context.hook = hook; }, sanitize(value) {
      if (mode === "sanitize-error") throw Error("synthetic sanitizer error");
      return "<p>sanitized lesson</p>";
    }
  };
  vm.createContext(context);
  vm.runInContext(helper, context);
  return { context, output, writes };
}

for (const mode of ["no-marked", "no-purifier", "parse-error", "sanitize-error", "normal"]) {
  const test = setup(mode);
  test.context.KodehaxMarkdown.render(test.output, source);
  assert.deepEqual(test.writes, [[mode === "normal" ? "html" : "text", mode === "normal" ? "<p>sanitized lesson</p>" : source]]);
  probes += 1;
}

const policy = setup("normal").context.KodehaxMarkdown;
for (const value of corpus.safe) { assert.equal(policy.safeUrl(value, false), true, value); probes += 1; }
for (const value of corpus.unsafe) { assert.equal(policy.safeUrl(value, false), false, value); probes += 1; }
assert.equal(policy.safeUrl("mailto:student@example.com", true), false);
probes += 1;

const hookTest = setup("normal");
hookTest.context.KodehaxMarkdown.render(hookTest.output, source);
const attrs = { href: "javascript%3Asynthetic()", src: "https://example.com/diagram.png" };
hookTest.context.hook({ hasAttribute(name) { return Object.hasOwn(attrs, name); }, getAttribute(name) { return attrs[name]; },
  removeAttribute(name) { delete attrs[name]; } });
assert.deepEqual(attrs, { src: "https://example.com/diagram.png" });
probes += 1;

// Run the actual rendering controller from every affected template, with failed
// sanitizer/parser CDNs. Stubs record HTML/text assignments without interpreting it.
for (const filename of templates) {
  const html = fs.readFileSync(path.join(root, "templates", filename), "utf8");
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(match => match[1]);
  const controller = scripts.find(script => script.includes("KodehaxMarkdown.render"));
  assert.ok(controller, filename);
  for (const mode of ["no-purifier", "no-marked", "sanitize-error", "normal"]) {
    const test = setup(mode);
    vm.runInContext(controller, test.context, { filename, timeout: 1000 });
    assert.ok(test.writes.length > 0, filename + ": no renderer ran in " + mode);
    for (const [kind, value] of test.writes) {
      assert.equal(kind, mode === "normal" ? "html" : "text", filename + ": " + mode);
      assert.equal(value, mode === "normal" ? "<p>sanitized lesson</p>" : source);
    }
    probes += 1;
  }
}
console.log("Offline Markdown/URL/controller security probes passed:", probes);
