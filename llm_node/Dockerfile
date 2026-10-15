# llm_node/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir langgraph anthropic psycopg2-binary langgraph-checkpoint-postgres "psycopg[binary,pool]" aio_pika
COPY llm_node/main.py .
COPY llm_node/checkpoint.py .
COPY db ./db
COPY custom_logger ./custom_logger
CMD ["python", "-u", "main.py"]