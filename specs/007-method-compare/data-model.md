# Data Model: 检测方法对比与检测方案

## MethodNote

一种检测方法在本轮回答中的一段说明。

- `name`: 展示名。允许 CCTV、QV、声纳、人员进入、潜水。
- `aliases`: 同一方法的说法。人员进入包含「人工下井」「进入管内」。
- `clauses`: 本轮证据里提到该方法的条款号列表。可为空。
- `quotes`: 对应原文。空则该段声明未检索到，不编造定义。

## PlanCheck

一次方案题的核对结果。

- `known`: 从用户原文读到的条件短句（管径、水位、埋深、管道种类、道路、能否停水、积泥）。没有则省略该项。
- `missing`: 四项关键条件中用户原文未提及的项。每项有名称和用途。
- `violations`: 用户条件与某条证据冲突的记录。每条含 `clause_no`、`method`、`quote`、对照说明。`method` 取证据原文里出现的方法名；没有方法名时用「该条款所述方法」。
- `may_recommend`: 仅当 `missing` 为空时为真。为假时回答不得给出最终推荐。

## EvidenceQuote

检索证据，本功能只读这些字段。

- `evidence_id`: 引用标识。
- `clause_no`: 条款号。必填才会进入回答。
- `quote`: 原文摘录。界限解析只扫描该字段。

## ExplainFinding

解释题从证据中抽出的肯定句。没有对应原文则不产生该句。

- `kind`: `prohibition` 或 `order`。
- `clause_no`
- `quote`
- `statement`: 只复述原文已经表达的限制或先后，不追加规程外理由。
