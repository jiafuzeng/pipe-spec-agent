"""Decimal evaluator for versioned, reviewed index rules with confirmed factors."""

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from rag.source import PDF_SHA


def rulebook(kind, version=None):
    if kind not in {"RI", "MI", "defect_score"}:
        raise ValueError("未知规则")
    file = Path(__file__).resolve().parents[1] / "kb" / f"{kind}.json"
    if not file.is_file():
        return None
    rule = json.loads(file.read_bytes())
    if (
        rule.get("status") != "approved"
        or rule.get("source_hash") != PDF_SHA
        or len(set(rule.get("reviewers", []))) < 2
        or not rule.get("reference_cases")
        or not rule.get("evidence")
        or version
        and rule.get("version") != version
    ):
        return None
    if kind in {"RI", "MI"}:
        if any(
            field.get("minimum") is None or field.get("maximum") is None
            for field in rule["fields"]
        ):
            return None
        for case in rule["reference_cases"]:
            result = evaluate(rule, case["parameters"])
            if (
                numeric(result["value"]) != numeric(case["value"])
                or result["grade"] != case["grade"]
            ):
                return None
    return rule


def missing_fields(fields, values):
    return [
        field
        for field in fields
        if field["name"] not in values or values[field["name"]] is None
    ]


def numeric(value):
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("参数须为有限数值") from exc
    if not result.is_finite():
        raise ValueError("参数须为有限数值")
    return result


def evaluate(rule, parameters):
    if missing_fields(rule["fields"], parameters):
        raise ValueError("缺少参数")
    trace = {}
    for field in rule["fields"]:
        name = field["name"]
        value = numeric(parameters[name])
        if value < numeric(field["minimum"]) or value > numeric(field["maximum"]):
            raise ValueError(f"{name} 超出范围")
        if "enum" in field and value not in map(numeric, field["enum"]):
            raise ValueError(f"{name} 不在已审核分档内")
        trace[name] = str(value * numeric(rule["coefficients"][name]))
    total = sum(map(Decimal, trace.values()))
    band = next(
        b for b in rule["bands"] if b["upper"] is None or total <= numeric(b["upper"])
    )
    return dict(
        value=str(total),
        grade=band["grade"],
        advice=band["advice"],
        formula=rule["formula"],
        parameters=parameters,
        contributions=trace,
        evidence=rule["evidence"],
    )


def result_id(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
