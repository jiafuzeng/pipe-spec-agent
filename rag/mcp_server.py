"""Independent Streamable HTTP tool process (04-interfaces)."""

import os
import json
from rag.calculation import rulebook, evaluate, result_id, missing_fields

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from rag.registry import Registry, knowledge_root

load_dotenv()
ROOT = knowledge_root()
server = FastMCP(
    "pipe-spec",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8001")),
    stateless_http=True,
    json_response=True,
)


@server.tool()
def search_clauses(query: str, top_k: int = 5) -> dict:
    registry = Registry(ROOT)
    if not registry.active():
        return {"evidence": []}
    from rag.search import search

    return {"evidence": search(ROOT, registry, query, max(1, min(top_k, 20)))}


@server.tool()
def get_calculation_schema(calculation_type: str) -> dict:
    rule = rulebook(calculation_type)
    if rule:
        return dict(
            calculation_type=calculation_type,
            status="approved",
            fields=rule["fields"],
            rule_version=rule["version"],
        )
    return dict(
        calculation_type=calculation_type,
        status="pending_review",
        fields=[],
        reason="公式、分值表及算例尚未完成人工双重复核。",
    )


@server.tool()
def lookup_defect_score(defect: str, grade: int, rule_version: str) -> dict:
    rule = rulebook("defect_score", rule_version)
    if not rule:
        return {"error": "RULE_NOT_PUBLISHED"}
    rows = [r for r in rule["rows"] if r["defect"] == defect and r["grade"] == grade]
    if len(rows) != 1:
        return {"error": "AMBIGUOUS_MAPPING", "candidates": rows}
    return {"row": rows[0], "rule_version": rule_version}


@server.tool()
def calculate_index(
    calculation_type: str, rule_version: str, parameters: dict, idempotency_key: str
) -> dict:
    rule = rulebook(calculation_type, rule_version)
    if not rule or calculation_type not in {"RI", "MI"}:
        return {"error": "RULE_NOT_PUBLISHED"}
    missing = missing_fields(rule["fields"], parameters)
    if missing:
        return {"error": "MISSING_PARAMETERS", "fields": missing}
    try:
        result = evaluate(rule, parameters)
    except ValueError as exc:
        return {"error": "INVALID_PARAMETER", "message": str(exc)}
    result.update(calculation_type=calculation_type, rule_version=rule_version)
    digest = result_id(result)
    registry = Registry(ROOT)
    with registry.connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS results (request TEXT PRIMARY KEY, digest TEXT, body TEXT)"
        )
        db.execute(
            "INSERT OR IGNORE INTO results VALUES(?,?,?)",
            (idempotency_key, digest, json.dumps(result)),
        )
        saved = db.execute(
            "SELECT digest FROM results WHERE request=?", (idempotency_key,)
        ).fetchone()
        if saved[0] != digest:
            return {"error": "IDEMPOTENCY_CONFLICT"}
    return result | {"result_id": digest}


@server.tool()
def plot_curve(result_ids: list[str], axis: str) -> dict:
    if axis not in {"T", "K"} or not 2 <= len(result_ids) <= 100:
        return {"error": "INVALID_PARAMETER"}
    import base64
    import csv
    import io
    from matplotlib.figure import Figure

    rows = []
    with Registry(ROOT).connect() as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='results'"
        ).fetchone():
            return {"error": "RESULT_NOT_FOUND"}
        for key in result_ids:
            row = db.execute(
                "SELECT body FROM results WHERE digest=? LIMIT 1", (key,)
            ).fetchone()
            if row is None:
                return {"error": "RESULT_NOT_FOUND"}
            rows.append(json.loads(row[0]))
    first = rows[0]

    def fixed(row):
        return (
            row["calculation_type"],
            row["rule_version"],
            {k: v for k, v in row["parameters"].items() if k != axis},
        )

    if any(axis not in r["parameters"] or fixed(r) != fixed(first) for r in rows):
        return {"error": "INCONSISTENT_POINTS"}
    points = [(r["parameters"][axis], r["value"]) for r in rows]
    fig = Figure(figsize=(6, 3.5), layout="constrained")
    ax = fig.subplots()
    ax.plot([float(x) for x, y in points], [float(y) for x, y in points], marker="o")
    ax.set(xlabel=axis, ylabel=first["calculation_type"])
    png = io.BytesIO()
    fig.savefig(png, format="png")
    output = io.StringIO()
    csv.writer(output).writerows([(axis, first["calculation_type"]), *points])
    return dict(
        points=points,
        result_ids=result_ids,
        csv=output.getvalue(),
        png_base64=base64.b64encode(png.getvalue()).decode(),
    )


if __name__ == "__main__":
    server.run(transport="streamable-http")
