FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN addgroup --system app && adduser --system --ingroup app app
USER app

CMD ["python", "-m", "app.main", "run"]

