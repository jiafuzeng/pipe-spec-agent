"""Streamable HTTP MCP: calculation and plotting only (specs/04 §3.2)."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from pipe_assessment_mcp import storage
from rag.calculation import evaluate, missing_fields, result_id, rulebook

load_dotenv()

server = FastMCP(
    "pipe-assessment-mcp",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "8001")),
    stateless_http=True,
    json_response=True,
)


@server.custom_route("/health", methods=["GET"])
async def health_check(request):  # noqa: ARG001
    from starlette.responses import JSONResponse

    root = storage.data_root()
    return JSONResponse(
        {
            "status": "ok",
            "service": "pipe-assessment-mcp",
            "data_dir": str(root),
        }
    )


@server.tool()
def get_calculation_schema(calculation_type: str, rule_version: str | None = None) -> dict:
    rule = rulebook(calculation_type, rule_version)
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
    conflict = storage.save_result(idempotency_key, digest, result)
    if conflict:
        return {"error": conflict}
    return result | {"result_id": digest}


@server.tool()
def plot_curve(
    result_ids: list[str],
    axis: str | None = None,
    x_axis: str | None = None,
    y_axis: str | None = None,
    fixed_parameters_summary: str | None = None,
    rule_version: str | None = None,
) -> dict:
    """Draw from stored results. Prefer x_axis; `axis` kept as transitional alias."""
    independent = x_axis or axis
    if independent not in {"T", "K"} or not 2 <= len(result_ids) <= 100:
        return {"error": "INVALID_PARAMETER"}
    from matplotlib.figure import Figure

    rows = storage.load_results_by_digest(result_ids)
    if rows is None:
        return {"error": "RESULT_NOT_FOUND"}
    first = rows[0]
    dependent = y_axis or first["calculation_type"]

    def fixed(row):
        return (
            row["calculation_type"],
            row["rule_version"],
            {k: v for k, v in row["parameters"].items() if k != independent},
        )

    if any(
        independent not in r["parameters"] or fixed(r) != fixed(first) for r in rows
    ):
        return {"error": "INCONSISTENT_POINTS"}
    points = [(r["parameters"][independent], r["value"]) for r in rows]
    fig = Figure(figsize=(6, 3.5), layout="constrained")
    ax = fig.subplots()
    ax.plot([float(x) for x, _ in points], [float(y) for _, y in points], marker="o")
    ax.set(xlabel=independent, ylabel=dependent)
    png = io.BytesIO()
    fig.savefig(png, format="png")
    png_bytes = png.getvalue()
    resource_id = hashlib.sha256(
        json.dumps(
            {"result_ids": result_ids, "x_axis": independent, "points": points},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    storage.artifact_path(resource_id).write_bytes(png_bytes)
    output = io.StringIO()
    csv.writer(output).writerows([(independent, dependent), *points])
    payload = dict(
        resource_id=resource_id,
        points=points,
        result_ids=result_ids,
        x_axis=independent,
        y_axis=dependent,
        rule_version=rule_version or first.get("rule_version"),
        csv=output.getvalue(),
        # Transition: clients may still read Base64 until Phase 2 artifacts URL lands.
        png_base64=base64.b64encode(png_bytes).decode(),
    )
    if fixed_parameters_summary:
        payload["fixed_parameters_summary"] = fixed_parameters_summary
    return payload


def main() -> None:
    storage.data_root()
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
