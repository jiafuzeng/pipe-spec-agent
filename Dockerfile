FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY docmind_parse.py .
COPY rag/ rag/
COPY pipe_assessment_mcp/ pipe_assessment_mcp/
COPY agentEval/fixtures/ agentEval/fixtures/
COPY ragEval/ ragEval/
ENV KNOWLEDGE_DIR=/app/data/knowledge
ENV MCP_DATA_DIR=/app/data/mcp
CMD ["uvicorn","rag.web:app","--host","0.0.0.0","--port","8000","--workers","1"]
