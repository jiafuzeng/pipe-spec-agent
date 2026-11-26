# 006 RAG 文档导入与向量索引 V1

状态：Draft（实现前需确认）  
版本：V1  
范围：Web 文件导入、DocMind 解析结果复用、LlamaIndex 切片与 embedding、Chroma 持久化、原文元数据追溯。

## 1. 目标与边界

V1 让用户能从 Web 导入 CJJ 181—2012 原文或现有 DocMind 清洗产物，预览并选择切片方式和 embedding 模型，再将文档切片写入可持久化的向量库。每个向量节点都能追溯到原始文件、文档版本、PDF 页序和 DocMind 版面块。

本 Spec 沿用 `001-knowledge-and-citations.md` 的知识边界：DocMind/OCR 产物是待核验内容，导入成功不等于获准回答。只有审核状态为 `approved` 的文档版本可进入已发布问答索引。未审核内容可完成切片和向量预构建，但只能停留在隔离的 staging collection，不能被 RAG 检索。

### V1 包含

- 浏览器上传 PDF、Markdown；上传现成 DocMind 结果时可同时附加原始 PDF、`document.json` 和 `document.md`。
- 原始 PDF 未提供 DocMind 结果时，由后端使用 DocMind 大模型解析；已提供 `document.json` 时复用版面结果，不重复调用解析 API。
- Web 选择切片策略、chunk size、overlap 和 embedding profile，先预览再执行导入。
- 使用 LlamaIndex `Document`、Node Parser、`IngestionPipeline` 与 embedding integrations 生成节点和向量。
- 使用持久化 Chroma 作为 V1 本地向量数据库；SQLite 保存文档、任务、审核和索引版本元数据；磁盘保留原始文件及 DocMind 产物。
- 保存文档级原始元数据及每个 chunk 的页码、章节、条款、版面类型和源位置。
- 导入状态、失败原因、文档列表、chunk 预览、审核发布和删除操作可在 Web 查看。

### V1 不包含

- 自动认定 OCR/DocMind 结果正确，或自动将新导入内容标为 `approved`。
- RRF 融合。后续混合检索遵循现有 Spec：BM25 与向量召回候选合并去重后，直接交给 reranker。
- 多租户权限模型、远程托管向量数据库、embedding 微调、自动条款事实核验。
- 一次上传任意复杂压缩包并猜测文件之间关系。上传的原文件和清洗产物必须由用户在同一导入表单中明确关联。

## 2. 用户流程

1. 用户打开「知识库 → 导入文档」，选择原始文档。可选附加 DocMind `document.json` / `document.md`；如果不附加 JSON，PDF 由后端调用 DocMind 解析。
2. 用户填写/确认文档标题、规程版次和原始文件名；后端计算原始文件 SHA-256。附件中的文件不能覆盖原文件。
3. 用户选择切片策略、切片长度、重叠长度和 embedding profile。默认策略为「按版面结构」，默认 chunk size 为 512 tokens、overlap 为 64 tokens。
4. 用户点击「预览切片」。后端按正式导入同一套 LlamaIndex 转换生成最多 10 个样例 chunk，显示 chunk 文本、章节/条款、页码、类型和预计 chunk 总数；预览不调用 embedding、不写 Chroma。
5. 用户确认后创建导入任务。Web 返回 job ID，页面展示解析、切片、向量化、staging 写入、待审核/发布或失败的状态和进度。
6. 成功后用户可查看文档信息和 chunk；人工对照原 PDF 后点击「审核通过」，staging collection 方可发布并进入问答检索范围。

## 3. 文件与解析契约

### 3.1 支持的导入形式

| 主文件 | 清洗附件 | 处理方式 |
|---|---|---|
| PDF | 无 | 调用 DocMind；保存原 PDF、DocMind JSON 和 Markdown 输出 |
| PDF | `document.json`（可附 `document.md`） | 复用 JSON 的 `Data.layouts`；不重复解析；记录附件来源 |
| Markdown | 无 | 直接作为 LlamaIndex Document；按 Markdown 标题及段落解析；页码未知时为 null |
| PDF + Markdown/JSON | 文件名由用户在表单明确关联 | 原 PDF 是来源权威文件；清洗附件用于切片；不按文件名自动猜配 |

V1 上传限制由服务端配置统一返回给前端；格式、文件大小、PDF 页数不满足 DocMind 限制时，在解析前拒绝并展示具体原因。服务端不得信任浏览器传来的 MIME 类型，需同时检查扩展名、文件签名和大小。

`document.json` 的权威结构为 `Data.layouts[]`。优先使用每个 layout 的 `markdownContent`，缺失时回退到 `text`。保留原 layout 的 `index`、`uniqueId`、`pageNum`、`type`、`subType`、`level`。没有 Markdown/JSON 版面数据的输入不得伪造页码或版面坐标。

### 3.2 文件持久化

```text
data/knowledge/
  originals/{source_doc_id}/{safe_filename}   # 不可变原文
  parsed/{source_doc_id}/document.json         # DocMind 原始解析结果
  parsed/{source_doc_id}/document.md           # DocMind 输出 Markdown
  chroma/                                      # Chroma 持久化数据
  registry.sqlite                              # 文档、任务、索引版本和审核状态
```

路径使用服务端生成的 ID；原始文件名仅用于显示和元数据，不能直接拼接成存储路径。原始文件在替换、重新切片或更换 embedding 时保留。删除操作采用逻辑删除并从活动 Chroma collection 移除节点；保留审计信息。

### 3.3 当前首批导入数据

仓库中已有原文 `docs/CJJ 181-2012 城镇排水管道检测与评估技术规程.pdf`，以及 DocMind 结果 `data/docmind/cjj-181-2012/document.json`、`document.md`。当前 JSON 顶层为 `RequestId` 和 `Data.layouts`，包含 611 个 layout；Markdown 文件约 63 KB。首次演示导入应由 Web 将原始 PDF 和这两个解析附件明确关联，复用 JSON layout，不再向 DocMind 重复提交；chunk 预览中应能看到 `pageNum`、`index`、`uniqueId`、`type`、`subType` 等来源字段。

## 4. 切片策略

切片参数以 tokens 为单位，UI 明确标注单位。V1 提供两种策略：

| `strategy` | 行为 | 适用场景 |
|---|---|---|
| `structure`（默认） | 读取 DocMind layout 或 Markdown 标题结构；继承最近的章节标题上下文；按段落/条款/表格/公式边界建立 LlamaIndex Documents；再以 `SentenceSplitter` 将过长内容切到目标 chunk size。短表格/公式保持为一个 chunk。 | 规程、条款、表格，优先保留页码与结构 |
| `sentence` | 对文档文本直接使用 LlamaIndex `SentenceSplitter(chunk_size, chunk_overlap)` 按句子边界切片。每个节点继承来源文档元数据；DocMind JSON 输入时还继承对应 layout 页码和类型。 | 对照实验或结构信息较弱的 Markdown |

V1 默认 `chunk_size=512`、`chunk_overlap=64`；允许用户选择 256/512/768/1024，overlap 选择 0/32/64/128，且必须小于 chunk size 的一半。两个参数都绑定进索引版本。实际 tokenizer 使用模型默认 tokenizer；如果所选模型 integration 不提供 tokenizer，统一使用 LlamaIndex 默认 tokenizer，并在预览页说明这是估算长度。

不能把全文按字符硬切后丢失来源定位。对跨多个 layout 的章节，chunk 可带多个来源 layout ID 的逗号分隔字符串；PDF 页码使用 1 起始 `page_pdf`，同时原样保存 DocMind 的 0 起始 `docmind_page_num`。印刷页码无法从解析结果可靠确认时为 null，不做推算。

## 5. Embedding 模型配置与选择

Web 从后端模型注册表读取可用 profile，不允许浏览器提交 API 密钥或任意 Python 类名。V1 提供 LlamaIndex 官方 integration：

- Ollama 本地 embedding（默认 profile：`ollama:bge-m3`；服务地址和模型名从后端配置读取）。
- DashScope embedding（示例 profile：`dashscope:text-embedding-v2`；需要服务端 `DASHSCOPE_API_KEY`）。

profile 字段：`profile_id`、`provider`、`model_name`、`model_version`、`dimension`、`deployment`（local/cloud）、`available`、`health_status`。DocMind AccessKey 不等于 DashScope API Key；DashScope profile 未配置独立 `DASHSCOPE_API_KEY` 时显示不可用。所有密钥仅在服务端环境变量或密钥管理服务中保存。模型不可用或凭证缺失时，该选项显示不可用并说明原因，不能创建任务。

提交前后端对所选模型执行一次短文本 embedding 健康检查，确认返回维度与 profile 记录一致。新 profile 首次使用时以实际返回维度为准；维度变化视为模型版本变更，必须建立新的 Chroma collection。

文档向量、查询向量必须使用同一 profile、同一模型版本和兼容的文本类型参数。更换 profile/model/version 不得复用旧 embedding。索引 collection 绑定：`source_doc_id + chunk_config_hash + embedding_profile_id + embedding_model_version`；用户确认后生成不可变 `index_version`。

## 6. LlamaIndex 和向量存储实现契约

1. 解析层将 DocMind `layouts` 转成 LlamaIndex `Document`，每个 Document 只包含可检索文本与标量 metadata。
2. 切片策略由后端 allowlist 映射到 LlamaIndex `SentenceSplitter`、`MarkdownNodeParser` 等 Node Parser。禁止将前端任意类名或参数透传到 Python import。
3. 使用 `IngestionPipeline(transformations=[node_parser, embed_model], vector_store=ChromaVectorStore)` 或等价 LlamaIndex 标准组件产出 nodes 并写入 Chroma。禁止自行计算 embedding 向量。
4. Chroma client 使用 `PersistentClient(path=...)`；collection 与索引版本一一对应。写入时带稳定 node ID、原文 text、可过滤 metadata 和 embedding。
5. 索引任务采用 staging collection。所有节点写入成功且数量与 LlamaIndex 输出一致后，registry 将索引版本标记为 `built_pending_review`，该 collection 仍不可检索；审核通过后将版本发布为 `active_approved`。发生失败时删除 staging collection/回滚任务，不影响上一活动版本。
6. 重复导入按原始源文件 SHA-256 去重。相同 SHA + 相同切片配置 + 相同 embedding profile/model version 返回已有索引；任一配置变更建立新 index version，避免重复 chunk ID 覆盖不同模型向量。
7. 向量数据与 metadata 均可从磁盘重新加载。后端重启后可按 registry 中的 collection 和 embedding profile 加载索引。

## 7. 元数据 Schema

### 7.1 文档版本（SQLite `source_documents`）

| 字段 | 类型 | 含义 |
|---|---|---|
| `source_doc_id` | string/UUID | 文档版本 ID；同一原文的不同 SHA 为不同版本 |
| `source_sha256` | string | 原始文件字节 SHA-256；去重与来源版本标识 |
| `original_filename` | string | 用户上传的原始文件名 |
| `stored_path` | string | 服务端相对存储路径 |
| `media_type` / `file_size` | string/int | 原始格式及字节数 |
| `title` / `edition` | string | 文档标题、版次，如 CJJ 181-2012 |
| `uploaded_at` / `uploaded_by` | datetime/string | 导入时间和操作者 |
| `parser` / `parser_version` / `docmind_task_id` | string/null | 清洗来源和解析任务追踪 |
| `review_status` | enum | `pending_review`、`approved`、`rejected`、`deleted` |

### 7.2 每个 LlamaIndex Node 的 Chroma metadata

每个 chunk 至少保存：

```json
{
  "source_doc_id": "...",
  "source_sha256": "...",
  "original_filename": "CJJ 181-2012 城镇排水管道检测与评估技术规程.pdf",
  "edition": "CJJ 181-2012",
  "page_pdf": 1,
  "page_printed": null,
  "section_path": "第4章/4.1一般规定",
  "clause_no": "4.1.1",
  "content_type": "normative_text|table|formula|figure|other",
  "docmind_layout_ids": "id1,id2",
  "docmind_layout_indexes": "10,11",
  "chunk_index": 0,
  "chunk_strategy": "structure",
  "chunk_size": 512,
  "chunk_overlap": 64,
  "embedding_profile_id": "ollama:bge-m3",
  "embedding_model_version": "configured-version",
  "embedding_dimension": 1024,
  "index_version": "...",
  "review_status": "pending_review"
}
```

`clause_no` 仅在原文能明确识别时填写，否则为 null；`section_path` 原样反映结构标题，不由 LLM 总结。`page_printed` 未核验时保持 null。可选字段为 null 时，只在 SQLite 中保存 null，在 Chroma metadata 中省略该字段；Chroma metadata 只写入其支持的标量，不写入 null、列表或嵌套对象。复杂来源对象留在 SQLite/原始 JSON，不能悄悄丢弃。行政元数据可供过滤和审计，但不应被当作法规正文嵌入；embedding 文本只包含 chunk 原文，必要时可显式追加条款号和章节标题。

## 8. 逻辑 API

### `GET /api/v1/knowledge/embedding-profiles`

返回服务端配置的模型 profile、维度、部署类型和可用状态；不返回密钥、完整 endpoint 凭证或本机敏感路径。

### `POST /api/v1/knowledge/imports/preview`

输入 multipart：`source_file`、可选 `docmind_json` / `docmind_markdown`、`title`、`edition`、`chunking.strategy`、`chunking.chunk_size`、`chunking.chunk_overlap`、`embedding_profile_id`。返回解析摘要、预览 chunks、元数据和估算 chunks 数；不写向量库、不调用 embedding。

### `POST /api/v1/knowledge/imports`

接受相同输入和 `Idempotency-Key`，创建异步任务并立即返回 `{job_id, source_doc_id, status}`。首次任务仅有 `pending_review` 状态，不允许客户端传 `approved`。

### `GET /api/v1/knowledge/imports/{job_id}`

返回状态、分阶段进度、chunk 数、索引版本、错误码和可读错误摘要，不暴露密钥或堆栈。

### `GET /api/v1/knowledge/documents`、`GET /api/v1/knowledge/documents/{source_doc_id}/chunks`

返回文档原始元数据、导入配置、审核状态、索引版本和可分页 chunk 预览。

### `POST /api/v1/knowledge/documents/{source_doc_id}/approve`

人工审核通过后，将审核状态更新为 `approved`，并把 staging collection 发布到活动检索集合。要求确认源 PDF 已可查阅；审核操作人和时间写入审计记录。发布失败时审核状态保持待审核，避免出现已批准但不可检索的半完成状态。

### `DELETE /api/v1/knowledge/documents/{source_doc_id}`

执行逻辑删除，从活动检索集合移除节点并保留删除审计记录。

## 9. Web 页面要求

- **导入页**：拖放/文件选择，展示原文和清洗附件各自文件名、大小、格式；选择标题、版次和来源关系。
- **切片设置**：切片策略下拉框，chunk size/overlap 下拉框；显示默认值和单位；不允许 overlap 超范围。
- **Embedding 设置**：profile 下拉框显示供应方、模型 ID、维度、local/cloud、连通状态；不可用 profile 不可提交。
- **预览区**：显示前 10 个 chunk 的原文、页码、章节、条款、类型和长度；明确提示“预览不会入库”。
- **任务列表**：显示进度阶段、状态、错误、导入时间、配置快照和 chunk 数。刷新页面仍能恢复任务状态。
- **文档详情/审核**：可查看原始文件元数据、DocMind 文件、索引配置、chunk、审核状态；审核前显示原文/PDF 可访问链接。
- **失败和重试**：只对可重试阶段重试；重试沿用原始 SHA 和参数快照。修改 chunk 或 embedding 后创建新的 index version。

## 10. Given / When / Then 验收

### ING-01 复用现有 DocMind 产物

**Given** 用户关联上传原始 PDF 和 `data/docmind/.../document.json`（可带 `document.md`）。  
**When** 预览并导入。  
**Then** 后端不调用 DocMind，按 `Data.layouts` 建立 LlamaIndex Documents；chunk 保留 PDF 页序、layout ID 和原文件 SHA。

### ING-02 PDF 直传解析

**Given** 用户上传 PDF 且没有 DocMind JSON，服务端 DocMind profile 已配置。  
**When** 启动导入。  
**Then** 后端调用 DocMind 异步解析并持久化 JSON/Markdown，成功后进入切片和 embedding 阶段；解析失败则任务失败且不发布半成品索引。

### ING-03 切片设置和预览一致

**Given** 用户选定任一切片策略、chunk size 和 overlap。  
**When** 点击预览并随后用相同设置导入。  
**Then** 预览调用与导入调用同一解析器/参数版本；样例 chunk 文本、边界与元数据一致。

### ING-04 Embedding profile 可选和绑定

**Given** 配置中存在可用 Ollama 与 DashScope profile。  
**When** 用户选定其中之一并完成导入。  
**Then** 每个节点和 index version 记录所选 profile/model/version/dimension；未配置凭证或连接失败时阻止建索引并展示可操作错误。

### ING-05 原文元数据追溯

**Given** 导入任务成功。  
**When** 用户从任一命中 chunk 打开来源。  
**Then** 能定位原始文件、SHA、版次、PDF 页序；存在 DocMind layout 时同时定位 layout ID/index/type。没有印刷页码证据时显示“未核验”，不得伪造页码。

### ING-06 待审核数据不进入回答

**Given** 文档已成功建索引但 `review_status=pending_review`。  
**When** RAG 执行向量/混合检索。  
**Then** 该文档节点被 metadata filter 排除；人工审核通过后才可被检索引用。

### ING-07 重复导入幂等

**Given** 同一原始 SHA、相同切片配置和 embedding model version 已成功导入。  
**When** 用户重试或重复上传。  
**Then** 返回已有 job/index 记录，不重复生成向量；改动任一配置则新建版本，不覆盖旧版本。

### ING-08 失败不污染可用索引

**Given** embedding 在第 N 个 chunk 失败或 Chroma 写入中断。  
**When** 导入任务失败。  
**Then** staging collection 不成为 active version，旧版本仍可查询，错误和阶段可见；原文件及 DocMind 结果保留供重试。

### ING-09 服务重启后恢复

**Given** 文档及向量已成功写入持久目录。  
**When** Web 服务重启后重新加载。  
**Then** registry、文档审核状态、索引版本和 Chroma collection 可恢复，metadata 和向量数量匹配。

## 11. 非功能与安全

- 上传、DocMind、embedding、Chroma 写入各阶段均记录耗时、计数和 job ID；不把 AccessKey/API key 写入日志。
- 对同一 index version 的重试具备幂等性；同一源版本支持多套 chunk/model index 版本共存。
- 临时上传文件在任务结束后清除；原文、清洗产物和 Chroma collection 使用配置目录并有备份/恢复说明。
- 页面响应不等待整份 PDF 解析/embedding；所有长任务异步执行，并可查询状态。
- 元数据 schema 版本化；更换字段、chunk 配置、embedding model/version 必须可识别并触发新索引构建。

## 12. V1 实施顺序与退出门禁

1. **数据契约**：锁定 `source_documents`、job、index version、Node metadata Schema 与状态机；用现有 `document.json` 样例校对。
2. **LlamaIndex POC**：在本地用现有 DocMind JSON 建 Document/Nodes，证明 metadata 从 layout 传到 Chroma，并能 reload；这一步先用可控 embedding 替身验证流程。
3. **embedding profiles**：接入 Ollama/DashScope，测试连接、维度、密钥配置和失败映射。
4. **切片预览**：实现结构切片、固定句子切片，保证 preview 与正式 ingestion 共用 pipeline 配置。
5. **持久化与版本**：实现 SQLite registry、Chroma staging collection、幂等、重建和删除。
6. **Web 导入/审核**：实现上传、配置、预览、进度、chunk 详情及人工审核状态。
7. **RAG 联调**：只检索 approved 节点；混合候选去重后使用 reranker，不接入 RRF。

退出条件：ING-01 至 ING-09 有对应自动化验收；现有 CJJ 文件能构建、重启恢复并追溯到源 PDF；未审核文档无法进入问答。

## 13. 依赖和待确认项

- LlamaIndex 标准组件以当前稳定版为准，锁定 `llama-index-core`、Chroma vector-store integration、Ollama/DashScope embedding integrations 版本。
- V1 先用本地 Chroma，后续若并发/规模超出单机演示，再评估迁移到独立向量服务；当前数据格式不得绑定 Chroma 私有字段。
- `approved` 的审核粒度 V1 是整份文档版本；若后续需按条款审核，再扩展到 chunk 粒度。
- 检索阈值和 reranker 模型继续按 `001` 的人工标注查询集决策；不在本 Spec 中预设分数阈值。

## 14. LlamaIndex 参考

- [Ingestion Pipeline](https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/)
- [Node Parser Modules](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/)
- [Chroma Vector Store](https://developers.llamaindex.ai/python/framework/integrations/vector_stores/chromaindexdemo/)
- [Ollama Embeddings](https://developers.llamaindex.ai/python/framework/integrations/embeddings/ollama_embedding/)
- [DashScope Embeddings](https://developers.llamaindex.ai/python/framework/integrations/embeddings/dashscope_embeddings/)
