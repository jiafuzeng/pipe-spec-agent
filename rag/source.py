"""CJJ source manifest and DocMind provenance (T01, KN-02, ING-01)."""

import json
import re
from pathlib import Path

PDF_SHA = "caf966e093bb99f59e73aa3b48a617b7fb08407b56a06b54036c26c27071178a"
EDITION = "CJJ 181-2012"


# LlamaIndex core parsers that can split regulation text without another service.
# Code, JSON, HTML, Markdown-element, Unstructured and LlamaParse are omitted:
# they need a programming language, JSON/HTML input, an LLM summary, or an external parser.
STRATEGIES = (
    ("structure", "按版面结构"),
    ("sentence", "按句子"),
    ("token", "按 Token"),
    ("markdown", "按 Markdown 标题"),
    ("sentence_window", "句子窗口"),
    ("hierarchical", "层次"),
    ("semantic", "语义"),
    ("semantic_merge", "语义双合并"),
)


def configuration(strategy, size, overlap):
    if strategy not in {item[0] for item in STRATEGIES} or size not in {
        256,
        512,
        768,
        1024,
    }:
        raise ValueError("不支持的切片策略或长度")
    if overlap not in {0, 32, 64, 128} or overlap * 2 >= size:
        raise ValueError("overlap 超出允许范围")
    return dict(chunk_strategy=strategy, chunk_size=size, chunk_overlap=overlap)


def sections(parsed):
    layouts = parsed.get("Data", {}).get("layouts")
    if not isinstance(layouts, list) or not layouts:
        raise ValueError("缺少 Data.layouts")
    headings = {}
    clause_no = None
    for block in layouts:
        text = (block.get("markdownContent") or block.get("text") or "").strip()
        if not text:
            continue
        heading = re.match(r"^(#{1,6})\s+([^\n]+)", text)
        if heading:
            depth = len(heading[1])
            headings = {k: v for k, v in headings.items() if k < depth}
            headings[depth] = heading[2]
            clause_no = None
        page = block.get("pageNum")
        clause = re.match(r"^[#>\s]*(?:续)?((?:表\s*)?\d+\.\d+\.\d+(?:-\d+)?)\b", text)
        if clause:
            clause_no = clause[1].replace(" ", "")
        yield (
            text,
            {
                "section_path": "/".join(headings.values()),
                "clause_no": clause_no,
                "page_pdf": page + 1 if isinstance(page, int) else None,
                "page_printed": None,
                "docmind_page_num": page,
                "docmind_layout_ids": block.get("uniqueId"),
                "docmind_layout_indexes": block.get("index"),
                "layout_type": block.get("type"),
                "layout_subtype": block.get("subType"),
                "layout_level": block.get("level"),
                "content_type": {
                    "text": "normative_text",
                    "table": "table",
                    "formula": "formula",
                    "figure": "figure",
                }.get(block.get("type"), "other"),
            },
        )


def docmind_candidates(parsed_dir):
    paths = []
    direct = Path(parsed_dir) / "document.json"
    if direct.is_file():
        paths.append(direct)
    root = Path(__file__).resolve().parents[1] / "data"
    named = root / "document.json"
    if named.is_file():
        paths.append(named)
    folder = root / "docmind"
    if folder.is_dir():
        paths.extend(folder.rglob("document.json"))
    unique = []
    seen = set()
    for path in paths:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def align_layouts(markdown, parsed):
    """Map each layout onto the original markdown, in order. None when any block is missing."""
    pos = 0
    spans = []
    for text, meta in sections(parsed):
        found = markdown.find(text, pos)
        if found < 0:
            return None
        spans.append((found, found + len(text), meta))
        pos = found + len(text)
    return spans or None


def pages_from_markdown(markdown, parsed_dir):
    """Group the original text by PDF page when it fully matches a DocMind JSON."""
    for path in docmind_candidates(parsed_dir):
        try:
            parsed = json.loads(path.read_bytes())
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        spans = align_layouts(markdown, parsed)
        if not spans:
            continue
        groups = []
        for start, end, meta in spans:
            page = meta.get("page_pdf")
            if groups and groups[-1]["page"] == page:
                groups[-1]["end"] = end
                groups[-1]["spans"].append((start, end, meta))
            else:
                groups.append(
                    {"page": page, "start": start, "end": end, "spans": [(start, end, meta)]}
                )
        pages = []
        for group in groups:
            origin = group["start"]
            pages.append(
                (
                    markdown[origin : group["end"]],
                    {
                        "page_pdf": group["page"],
                        "docmind_page_num": None
                        if group["page"] is None
                        else group["page"] - 1,
                    },
                    [
                        (start - origin, end - origin, meta)
                        for start, end, meta in group["spans"]
                    ],
                )
            )
        return pages
    return None
