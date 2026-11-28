/** 轻量 Markdown → 安全 HTML（标题 / 列表 / 粗体 / 行内代码 / 段落）。 */

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

/**
 * @param {string} source
 * @returns {string}
 */
export function renderMarkdown(source) {
  const lines = String(source || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let list = null; // { ordered: bool, items: string[] }

  function flushList() {
    if (!list) return;
    const tag = list.ordered ? "ol" : "ul";
    html.push(
      `<${tag}>` +
        list.items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("") +
        `</${tag}>`,
    );
    list = null;
  }

  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    const ul = /^[-*]\s+(.+)$/.exec(line);
    const ol = /^(\d+)\.\s+(.+)$/.exec(line);

    if (heading) {
      flushList();
      const level = heading[1].length;
      html.push(`<h${level}>${inlineMarkdown(heading[2].trim())}</h${level}>`);
      continue;
    }
    if (ul) {
      if (!list || list.ordered) {
        flushList();
        list = { ordered: false, items: [] };
      }
      list.items.push(ul[1]);
      continue;
    }
    if (ol) {
      if (!list || !list.ordered) {
        flushList();
        list = { ordered: true, items: [] };
      }
      list.items.push(ol[2]);
      continue;
    }
    if (!line.trim()) {
      flushList();
      continue;
    }
    flushList();
    html.push(`<p>${inlineMarkdown(line.trim())}</p>`);
  }
  flushList();
  return html.join("");
}
