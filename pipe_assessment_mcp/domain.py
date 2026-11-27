"""Decimal evaluator for versioned, reviewed index rules with confirmed factors."""

import hashlib
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

PDF_SHA = "caf966e093bb99f59e73aa3b48a617b7fb08407b56a06b54036c26c27071178a"

ROOT = Path(__file__).resolve().parents[1]


def _rule_search_paths(kind):
    """Yield candidate rule JSON paths. Fixtures only under RULE_FIXTURE=1; never worksheets/."""
    names = (f"{kind}.json", f"{kind}.min.json")
    if os.environ.get("RULE_FIXTURE") == "1":
        fixture_dir = ROOT / "agentEval" / "fixtures" / "rules"
        for name in names:
            yield fixture_dir / name, True
    if os.environ.get("RULES_DIR"):
        dirs = [Path(os.environ["RULES_DIR"])]
    else:
        mcp_rules = ROOT / "pipe_assessment_mcp" / "rules"
        dirs = [mcp_rules / "published"]
    for rules_dir in dirs:
        for name in names:
            path = rules_dir / name
            # Worksheets and reviews are never loadable production paths.
            if "worksheets" in path.parts or "reviews" in path.parts:
                continue
            yield path, False


def _case_value_grade(case):
    expected = case.get("expected") or {}
    return case.get("value", expected.get("RI") or expected.get("value")), case.get(
        "grade", expected.get("grade")
    )


def rulebook(kind, version=None):
    if kind not in {"RI", "MI", "defect_score"}:
        raise ValueError("未知规则")
    for file, fixture_mode in _rule_search_paths(kind):
        if not file.is_file():
            continue
        rule = json.loads(file.read_bytes())
        if rule.get("status") != "approved":
            continue
        if fixture_mode:
            if not rule.get("fixture_only"):
                continue
        else:
            from pipe_assessment_mcp.validate_rules import validate_package

            if validate_package(file):
                continue
            if rule.get("fixture_only"):
                continue
            if (
                rule.get("source_hash") != PDF_SHA
                or len(set(rule.get("reviewers", []))) < 2
                or not rule.get("reference_cases")
                or not rule.get("evidence")
            ):
                continue
        if version and rule.get("version") != version:
            continue
        if kind in {"RI", "MI"}:
            if any(
                field.get("minimum") is None or field.get("maximum") is None
                for field in rule["fields"]
            ):
                continue
            cases = rule.get("reference_cases") or []
            if not fixture_mode and not cases:
                continue
            ok = True
            for case in cases:
                value, grade = _case_value_grade(case)
                result = evaluate(rule, case["parameters"])
                if (
                    numeric(result["value"]) != numeric(value)
                    or result["grade"] != grade
                ):
                    ok = False
                    break
            if not ok:
                continue
        return rule
    return None


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
        evidence=rule.get("evidence") or [],
    )


def result_id(data):
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
