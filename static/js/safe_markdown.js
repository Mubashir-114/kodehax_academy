/* CDN failures always render text. This helper never inserts unsanitized HTML. */
(function (global) {
  "use strict";
  const hooked = new WeakSet();

  function safeUrl(value, image) {
    let candidate = String(value || "").trim();
    for (let index = 0; index < 8; index += 1) {
      let decoded;
      try {
        const entities = candidate.replace(/&(?:#x([0-9a-f]+)|#([0-9]+)|(amp|colon|tab|newline|nbsp));?/gi,
          function (_, hex, decimal, named) {
            if (hex || decimal) return String.fromCodePoint(parseInt(hex || decimal, hex ? 16 : 10));
            return { amp: "&", colon: ":", tab: "\t", newline: "\n", nbsp: " " }[named.toLowerCase()];
          });
        decoded = entities.replace(/(?:%[0-9a-f]{2})+/gi, function (encoded) { return decodeURIComponent(encoded); });
      } catch (_) { return false; }
      if (decoded === candidate) break;
      candidate = decoded;
      if (index === 7) return false;
    }
    if (!candidate || /[\\\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/.test(candidate)) return false;
    const compact = candidate.normalize("NFKC").replace(/\s/g, "");
    const scheme = /^([^/?#]*):/.exec(compact);
    if (scheme && !(image ? /^(https?)$/i : /^(https?|mailto)$/i).test(scheme[1])) return false;
    if (compact.startsWith("///")) return false;
    try {
      const url = new URL(compact, "https://relative.invalid/");
      if (url.username || url.password) return false;
      if (scheme && /^https?$/i.test(scheme[1]) && !/^https?:\/\//i.test(compact)) return false;
      return true;
    } catch (_) { return false; }
  }

  function render(output, source) {
    const text = String(source || "");
    try {
      const purifier = global.DOMPurify;
      if (!global.marked || typeof global.marked.parse !== "function" ||
          !purifier || typeof purifier.sanitize !== "function" || typeof purifier.addHook !== "function") {
        output.textContent = text;
        return false;
      }
      if (typeof purifier.addHook === "function" && !hooked.has(purifier)) {
        purifier.addHook("afterSanitizeAttributes", function (node) {
          ["href", "src"].forEach(function (name) {
            if (node.hasAttribute(name) && !safeUrl(node.getAttribute(name), name === "src")) node.removeAttribute(name);
          });
        });
        hooked.add(purifier);
      }
      output.innerHTML = purifier.sanitize(global.marked.parse(text));
      return true;
    } catch (_) {
      output.textContent = text;
      return false;
    }
  }
  global.KodehaxMarkdown = Object.freeze({ render: render, safeUrl: safeUrl });
})(window);
