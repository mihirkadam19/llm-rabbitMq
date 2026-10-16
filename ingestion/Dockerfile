# ingestion/Dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pika psycopg2-binary "pyjwt[crypto]"
COPY ingestion/main.py .
COPY ingestion/controllers.py .
COPY ingestion/middleware.py .
COPY ingestion/helpers.py .
COPY db ./db
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]