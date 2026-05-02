FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd -m -u 10001 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
# Tests live alongside the app so `pytest tests/` works inside the container
# (used by CI and by `docker compose exec api pytest tests/`). They are
# inert at runtime — uvicorn never imports them.
COPY tests ./tests
RUN chmod -R a+rX /app/alembic /app/alembic.ini /app/tests

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
