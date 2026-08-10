FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system stockoutops && adduser --system --ingroup stockoutops stockoutops

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY migrations ./migrations
COPY fixtures ./fixtures

USER stockoutops
EXPOSE 8000

CMD ["uvicorn", "stockoutops.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
