"""Extract explicit site observations. The MCP owns all table mappings and arithmetic."""

import re


def observations(query, alternatives):
    values = {}
    if match := re.search(r"DN\s*(\d+)\b|DN\s*(\d+)(?=[\u4e00-\u9fff])", query, re.I):
        values["D"] = match[1] or match[2]
    if match := re.search(r"土质(?:为|是|=|：)?\s*([^，,。；;\s（）()]+)", query):
        values["soil"] = match[1]
    for column in alternatives["soil_columns"]:
        if column in query and ("确认" in query or query.strip("。， ") == column):
            values["soil"] = column
    grades = "|".join(re.escape(g) for g in alternatives["grades"])
    pair = re.search(
        r"(?:2|两)\s*处\s*(" + grades + r")([\u4e00-\u9fff]{1,10})(?=[（(，,。；;\s])",
        query,
    )
    if pair:
        defect = dict(defect=pair[2], grade=alternatives["grades"][pair[1]])
        if score := re.search(
            r"(?:各|单处)(?:分值|为|得分)?\s*(\d+(?:\.\d+)?)\s*分?", query
        ):
            defect["score"] = score[1]
        values["defects"] = [defect.copy(), defect.copy()]
    if gap := re.search(
        r"(?:纵向)?(?:间距|净距)(?:为|约)?\s*(\d+(?:\.\d+)?)\s*(?:m|米)", query, re.I
    ):
        values["gap_m"] = gap[1]
    return values
