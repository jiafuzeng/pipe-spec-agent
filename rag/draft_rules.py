"""Materialize review worksheets from DocMind parse to stdout (pending_review).

Does not write into the repo. Approved packages belong in pipe-assessment-mcp/rules/
(or RULES_DIR); eval fixtures live under agentEval/fixtures/rules/.
"""

import json
import re
from pathlib import Path

from rag.source import PDF_SHA, sections

ROOT = Path(__file__).resolve().parents[1]


def candidate_rules(root):
    blocks = list(
        sections(
            json.loads(
                next((root / "data/docmind").rglob("document.json")).read_bytes()
            )
        )
    )

    def evidence(refs):
        return [
            dict(quote=text, **location)
            for text, location in blocks
            if location["clause_no"] in refs
        ]

    base = dict(
        status="pending_review",
        version="CJJ181-2012-draft1",
        source_hash=PDF_SHA,
        reviewers=[],
        reference_cases=[],
    )
    lookup = base | dict(
        fields=[dict(name="defect", type="string"), dict(name="grade", type="integer")],
        evidence=evidence({"表8.2.3", "表8.2.4"}),
        rows=[],
    )
    for entry in lookup["evidence"]:
        if entry["content_type"] != "table":
            continue
        for line in entry["quote"].splitlines():
            cells = [s.strip() for s in line.strip().strip("|").split("|")]
            if (
                len(cells) == 6
                and cells[3].isdigit()
                and re.fullmatch(r"\d+(?:\.\d+)?", cells[-1])
            ):
                lookup["rows"].append(
                    dict(
                        defect=cells[0],
                        grade=int(cells[3]),
                        score=cells[5],
                        evidence=entry["clause_no"],
                        page_pdf=entry["page_pdf"],
                        layout=entry["docmind_layout_ids"],
                    )
                )
    yield "defect_score", lookup
    for kind, section, factor, coefficients in [
        ("RI", "8.3", "F", {"F": "0.7", "K": "0.1", "E": "0.05", "T": "0.15"}),
        ("MI", "8.4", "G", {"G": "0.8", "K": "0.15", "E": "0.05"}),
    ]:
        ref = section + ".4"
        refs = {
            section + ".1",
            section + ".2",
            ref,
            section + ".5",
            "表" + section + ".5",
            "表8.3.4-1",
            "表8.3.4-2",
            "8.1.3",
            "8.1.4",
        }
        if kind == "RI":
            refs.add("表8.3.4-3")
        entries = evidence(refs)
        labels = {
            factor: "缺陷参数",
            "K": "地区重要性参数",
            "E": "管道重要性参数",
            "T": "土质影响参数",
        }
        fields = [
            dict(
                name=k,
                label_zh=labels[k],
                minimum=0,
                maximum=None if k == factor else 10,
                unit="无量纲",
                description=labels[k],
                evidence_refs=[ref],
            )
            for k in coefficients
        ]
        bands = []
        for e in entries:
            if e["clause_no"] == "表" + section + ".5" and e["content_type"] == "table":
                for line in e["quote"].splitlines():
                    cells = [s.strip() for s in line.strip().strip("|").split("|")]
                    if len(cells) == 3 and re.fullmatch(r"[ⅠⅡⅢⅣIV]+", cells[0]):
                        bands.append(
                            dict(
                                grade=cells[0],
                                upper=[1, 4, 7, None][len(bands)],
                                advice=cells[2],
                            )
                        )
        yield (
            kind,
            base
            | dict(
                fields=fields,
                formula=kind
                + " = "
                + " + ".join(v + " × " + k for k, v in coefficients.items()),
                coefficients=coefficients,
                bands=bands,
                evidence=entries,
            ),
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate pending_review worksheets for dual review (specs/008)."
    )
    parser.add_argument("kind", choices=["RI", "MI", "defect_score"])
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write to pipe_assessment_mcp/rules/worksheets/<kind>.pending.json",
    )
    args = parser.parse_args()
    payload = dict(candidate_rules(ROOT))[args.kind]
    payload["status"] = "pending_review"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.write:
        out = (
            ROOT
            / "pipe_assessment_mcp"
            / "rules"
            / "worksheets"
            / f"{args.kind}.pending.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out} (pending_review; not loadable by rulebook)")
    else:
        print(text)
