import assert from "node:assert/strict";
import { renderMarkdown } from "../src/markdown.js";

const html = renderMarkdown(
  "依据规程如下：\n\n- **编制目的**：结论。原文：「句。」\n\n- **适用范围**：结论。",
);
assert.match(html, /<p>依据规程如下：<\/p>/);
assert.match(html, /<ul>/);
assert.match(html, /<strong>编制目的<\/strong>/);
assert.match(html, /<strong>适用范围<\/strong>/);
assert.equal(renderMarkdown("<script>x</script>"), "<p>&lt;script&gt;x&lt;/script&gt;</p>");
console.log("markdown ok");
