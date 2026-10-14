# llm_node/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir langgraph anthropic pika psycopg2-binary
COPY llm_node/main.py .
COPY db ./db
CMD ["python", "-u", "main.py"]