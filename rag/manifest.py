"""Rebuild the pending-review inventory directly from the repository attachments."""

import hashlib
import json
from pathlib import Path

from rag.source import EDITION, PDF_SHA, sections


def manifest(root):
    pdf = next((root / "docs").glob("CJJ 181-2012*.pdf"))
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if sha != PDF_SHA:
        raise ValueError("源 PDF 与基线不匹配")
    parsed = root / "data/docmind/cjj-181-2012/document.json"
    blocks = json.loads(parsed.read_bytes())
    pages = {}
    for text, meta in sections(blocks):
        page = pages.setdefault(
            meta["page_pdf"],
            dict(page_pdf=meta["page_pdf"], page_printed=None, headings=[], clauses=[]),
        )
        if meta["layout_type"] == "title":
            page["headings"].append(text)
        clause = meta["clause_no"]
        if clause and clause not in page["clauses"]:
            page["clauses"].append(clause)
    return dict(
        edition=EDITION,
        original_filename=pdf.name,
        source_hash=sha,
        parsed_hash=hashlib.sha256(parsed.read_bytes()).hexdigest(),
        review_status="pending_review",
        layout_count=len(blocks["Data"]["layouts"]),
        pages=list(pages.values()),
    )


if __name__ == "__main__":
    print(
        json.dumps(
            manifest(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2
        )
    )
