# Pipe Spec Agent · 管道规程工作台

当前实现提供知识库导入与审核、条款检索、SSE 对话和独立 MCP 服务。唯一可发布的知识源由规程 PDF 的 SHA-256 锁定。计算规则审核状态见 kb/README.md。

## 本地运行

使用 Python 3.11，项目目录内执行：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m rag.mcp_server
```

另开两个终端，分别运行 API 和前端：

```sh
.venv/bin/uvicorn rag.web:app --port 8000 --workers 1
```

```sh
cd frontend
npm install
npm run dev
```

浏览器打开 http://127.0.0.1:5173。8000 只提供接口，不提供页面。前端开发服务器把 `/api` 转到 8000。

在 Cursor 的「运行和调试」里选择「启动工作台」，会按上面三个进程一起启动，并在前端就绪后打开浏览器。单独调试时可分别选择 MCP、API 或前端。

容器入口为 `docker compose up --build`，Compose 从项目 .env 读取配置；容器里同样打开 http://127.0.0.1:5173，API 映射在 8000。

- Embedding 使用 `OLLAMA_BASE_URL` 上的 bge-m3，请求为 `POST /api/embed`，正文是 `{"model":"bge-m3","input":"..."}`。当前地址是 http://192.168.1.100:11434。OLLAMA_MODEL_VERSION 记录模型版本。DashScope 使用 DASHSCOPE_API_KEY 和 DASHSCOPE_MODEL_VERSION。
- 自然语言检索需要 RERANKER_MODEL（本地 CrossEncoder 路径或模型 ID）。证据筛选使用 CHAT_BASE_URL（含 /v1）、CHAT_MODEL、CHAT_API_KEY。两个进程从 .env 或服务端环境变量读取配置。
- 导入演示选择 docs 下的 PDF。页面只上传原文；没有现成解析结果时，后端调用 DocMind，因此 PDF 直传需要服务凭证。
- 查看机制和验收接口可访问 http://127.0.0.1:8000/docs。未审核索引不可用于问答。没有证据时走固定拒答，依赖服务失败时单独报告错误。
- KNOWLEDGE_DIR 默认 data/knowledge。停止 API 与 MCP 后整体备份或恢复该目录，包括原文、解析产物、SQLite、Chroma。中断的构建在 API 重启时标为失败，可重新提交原始输入。当前采用单 API worker，本地演示会话保存在内存。
- 页面为单机演示管理员设计，审核与删除入口仅应绑定本机或通过受控入口访问。

## 前端

工作台是独立的 React 19 应用，源码在 `frontend/src`，由 Vite 构建。API 镜像不包含页面。使用问答和导入时打开前端地址。

| 页面 | Spec | 主要交互 |
| --- | --- | --- |
| 规程问答 | 001、002、003、004 | 九题入口、逐轮 SSE、确认参数、展开 MCP 记录、跳转引用原页、下载曲线和点值 |
| 导入文档 | 006、WEB-07/08 | 上传原文，选择切片和模型，预览后提交同一组配置 |

修改页面后执行：

```sh
cd frontend
npm install
npm test
npm run build
```

构建产物在 `frontend/dist`，由前端容器的 nginx 提供，并把 `/api` 转到 API。会话记录保存在当前标签页，服务重启后重新创建会话并提示上下文变化。

## 验证

```sh
python -m rag.manifest
python -m unittest discover -s tests -v
```

manifest 输出原文和解析产物哈希、52 页 DocMind 来源清单、章节/条款定位和待核验状态。集成测试使用仓库 PDF、真实 LlamaIndex 和持久化 Chroma，embedding 使用测试替身。测试目录使用临时数据，不发布实际规程。

## 尚待验收

未发布 RI/MI 或缺陷分值规则，Web 对计算请求返回核验状态。指数计算器能按已批准字段、权重和分档处理已确认因子；原始缺陷到分项系数的全链路、九题真实答卷、方案比较、真实规则曲线与现场截图仍待完成。文档审核由演示管理员逐项核对，排序阈值与模型选择还需人工标注集评测。
