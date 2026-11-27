"""Machine gate for dual-reviewed calculation packages (specs/008)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag.calculation import evaluate, numeric
from rag.source import PDF_SHA

ROOT = Path(__file__).resolve().parent


def _case_value_grade(case: dict):
    expected = case.get("expected") or {}
    value = case.get("value", expected.get("RI") or expected.get("MI") or expected.get("value"))
    grade = case.get("grade", expected.get("grade"))
    return value, grade


def validate_package(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        rule = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"无法读取 JSON: {exc}"]

    if rule.get("fixture_only"):
        errors.append("fixture_only 包不得作为 published 发布包")
    if rule.get("status") != "approved":
        errors.append("status 必须为 approved 才能通过发布门禁")
    if not rule.get("version"):
        errors.append("缺少 version")
    if rule.get("source_hash") != PDF_SHA:
        errors.append(f"source_hash 必须等于 PDF_SHA ({PDF_SHA})")
    reviewers = [r for r in rule.get("reviewers") or [] if str(r).strip()]
    if len(set(reviewers)) < 2:
        errors.append("reviewers 去重后须至少 2 人")
    if not rule.get("evidence"):
        errors.append("evidence 不能为空")

    kind = path.stem.split(".")[0]
    if kind in {"RI", "MI"} or rule.get("formula"):
        fields = rule.get("fields") or []
        if not fields:
            errors.append("RI/MI 缺少 fields")
        for field in fields:
            if field.get("minimum") is None or field.get("maximum") is None:
                errors.append(f"字段 {field.get('name')} 的 minimum/maximum 不能为 null")
        if not rule.get("formula") or not rule.get("coefficients") or not rule.get("bands"):
            errors.append("RI/MI 需要 formula、coefficients、bands")
        cases = rule.get("reference_cases") or []
        if len(cases) < 2:
            errors.append("reference_cases 至少 2 条")
        for i, case in enumerate(cases):
            try:
                value, grade = _case_value_grade(case)
                result = evaluate(rule, case["parameters"])
                if numeric(result["value"]) != numeric(value) or result["grade"] != grade:
                    errors.append(
                        f"reference_cases[{i}] 复算不一致: got {result['value']}/{result['grade']} "
                        f"expected {value}/{grade}"
                    )
            except Exception as exc:  # noqa: BLE001 — surface any evaluate failure
                errors.append(f"reference_cases[{i}] 复算失败: {exc}")
    elif kind == "defect_score" or "rows" in rule:
        rows = rule.get("rows") or []
        if not rows:
            errors.append("defect_score 的 rows 不能为空")
    else:
        errors.append("无法识别规则类型（文件名或内容需为 RI/MI/defect_score）")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验计算规则包是否满足双审发布门禁")
    parser.add_argument("paths", nargs="+", type=Path, help="候选 JSON 路径")
    args = parser.parse_args(argv)
    failed = 0
    for path in args.paths:
        errs = validate_package(path)
        if errs:
            failed = 1
            print(f"FAIL {path}")
            for err in errs:
                print(f"  - {err}")
        else:
            print(f"OK   {path}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
