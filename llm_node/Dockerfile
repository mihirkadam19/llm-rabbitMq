# llm_node/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir langgraph anthropic pika
COPY main.py .
CMD ["python", "-u", "main.py"]