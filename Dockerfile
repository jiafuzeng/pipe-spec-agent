FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY docmind_parse.py .
COPY rag/ rag/
COPY kb/ kb/
ENV KNOWLEDGE_DIR=/app/data/knowledge
CMD ["uvicorn","rag.web:app","--host","0.0.0.0","--port","8000","--workers","1"]
