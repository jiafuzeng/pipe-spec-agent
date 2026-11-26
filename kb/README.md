计算服务从本目录读取服务端发布的 RI.json、MI.json 和 defect_score.json。当前仓库未提供通过人工复核的规则包。即使知识库整份 PDF 审核通过，计算规则仍须独立核验。

指数规则包包含 status、source_hash、version、reviewers、reference_cases、evidence、fields、coefficients、formula、bands。fields 的每项定义参数 name、minimum、maximum、可选 enum、单位、用途及条款。bands 按上界升序，含 upper、grade、advice，末档上界为 null。查分规则另需 rows（defect、grade、score 及表项来源）。当前指数求值器处理已经确认的分项参数；原始缺陷的空间分组和合并尚未接入。

三个随库 JSON 均为待审草稿。可用 `python -m rag.draft_rules RI`、`MI` 或 `defect_score` 重建对应候选清单。每处原文携带 PDF 页序和 layout ID。审核需比对原 PDF，补全适用条件、值域和边界，特别是因子上界为 null 的字段，再录入参考算例。查分草稿只抽取解析结果中具有明确数字分值的六列表行，完整性亦须逐行复核。
