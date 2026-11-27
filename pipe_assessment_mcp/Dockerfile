FROM python:3.11-slim
WORKDIR /service
COPY . pipe_assessment_mcp/
RUN pip install --no-cache-dir ./pipe_assessment_mcp
ENV MCP_HOST=0.0.0.0 MCP_DATA_DIR=/data
CMD ["pipe-assessment-mcp"]
