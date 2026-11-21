FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements-web.txt ./
RUN pip install -r requirements-web.txt && useradd --uid 10001 --create-home appuser
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "-m", "app.container_start"]
