"""RI alternate inputs under a reviewed paired-defect rule package."""

from .domain import numeric


class InputError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.payload = {"error": code, "message": message, **details}


def derive_pair(scores, gap_m, policy):
    if len(scores) != 2:
        raise InputError("INVALID_PARAMETER", "双缺陷算例要求两条缺陷记录")
    a, b = map(numeric, scores)
    gap = numeric(gap_m)
    if min(a, b, gap) < 0:
        raise InputError("INVALID_PARAMETER", "分值和纵向净距须为非负数")
    if gap <= numeric(policy["overlap_m"]):
        mean = peak = min(a + b, numeric(policy["score_cap"]))
        group = "overlap"
    else:
        near = gap <= numeric(policy["near_m"])
        mean = (a + b) / 2
        if near:
            mean *= numeric(policy["near_weight"])
        peak = max(a, b)
        group = "n2" if near else "n1"
    return dict(S=str(mean), Smax=str(peak), F=str(max(mean, peak)), group=group)


def resolve_inputs(rule, raw, score_lookup):
    params = dict(raw)
    trace = []
    policy = rule.get("paired_defect_rules")
    if not any(k in params for k in ("defects", "D", "soil")):
        return params, trace
    if not policy or rule.get("fixture_only"):
        raise InputError("RULE_NOT_PUBLISHED", "缺陷推导与映射规则尚未发布")
    if "defects" in params:
        records = params.pop("defects")
        if not isinstance(records, list) or len(records) != 2 or "gap_m" not in params:
            raise InputError("MISSING_PARAMETERS", "请给出两条缺陷记录及纵向净距")
        scores = []
        for record in records:
            if not isinstance(record, dict) or not {"defect", "grade"} <= record.keys():
                raise InputError("MISSING_PARAMETERS", "请提供缺陷类型和等级")
            lookup = score_lookup(record["defect"], record["grade"], rule["version"])
            if "error" in lookup:
                raise InputError(lookup["error"], "缺陷分值表无法唯一核对该记录")
            row = lookup["row"]
            if "score" in record and numeric(record["score"]) != numeric(row["score"]):
                raise InputError(
                    "INVALID_PARAMETER", "题给分值与已审核表项不符", row=row
                )
            scores.append(row["score"])
            trace.append(dict(table_row=row))
        metrics = derive_pair(scores, params.pop("gap_m"), policy)
        if "F" in params and numeric(params["F"]) != numeric(metrics["F"]):
            raise InputError("AMBIGUOUS_MAPPING", "已给 F 与缺陷记录推导结果冲突")
        params["F"] = metrics["F"]
        trace.append(dict(metrics, evidence=policy["evidence"]))
    if "D" in params:
        diameter = numeric(params.pop("D"))
        if diameter <= 0 or "F" not in params:
            raise InputError("INVALID_PARAMETER", "管径须为正数且缺陷参数须可核对")
        if numeric(params["F"]) < numeric(policy["low_f"]):
            value = policy["low_f_E"]
        else:
            rows = [
                r
                for r in policy["diameters"]
                if (
                    r.get("lower") is None
                    or diameter > numeric(r["lower"])
                    or (r.get("include_lower") and diameter == numeric(r["lower"]))
                )
                and (
                    r.get("upper") is None
                    or diameter < numeric(r["upper"])
                    or (r.get("include_upper") and diameter == numeric(r["upper"]))
                )
            ]
            if len(rows) != 1:
                raise InputError("AMBIGUOUS_MAPPING", "管径未匹配唯一表项")
            value = rows[0]["E"]
        if "E" in params and numeric(params["E"]) != numeric(value):
            raise InputError("AMBIGUOUS_MAPPING", "已给 E 与管径映射冲突")
        params["E"] = str(value)
        trace.append(dict(D=str(diameter), E=params["E"], evidence="表8.3.4-2"))
    if "soil" in params:
        soil = params.pop("soil")
        if soil not in policy["soils"]:
            raise InputError(
                "AMBIGUOUS_MAPPING",
                "请确认土质表列或直接给出 T",
                candidates=list(policy["soils"]),
            )
        value = policy["soils"][soil]
        if "T" in params and numeric(params["T"]) != numeric(value):
            raise InputError("AMBIGUOUS_MAPPING", "土质表列与已给 T 冲突")
        params["T"] = str(value)
        trace.append(dict(soil=soil, T=params["T"], evidence="表8.3.4-3"))
    return params, trace
