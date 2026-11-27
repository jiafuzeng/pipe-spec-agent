FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py docmind_parse.py ./
COPY app/ app/
COPY ragEval/ ragEval/
COPY agentEval/*.json agentEval/
ENV KNOWLEDGE_DIR=/app/data/knowledge AGENT_DB=/app/data/agent/app.sqlite
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--workers","1"]
