# Django API served by gunicorn. Build context is the repo root (requirements.txt
# lives there, and settings.py reads ../.env and ../data relative to backend/).
#   docker build -f backend/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ backend/

RUN useradd --create-home app && chown -R app /app
USER app

WORKDIR /app/backend
EXPOSE 8000

# Gemini turns can take a while, so allow long requests.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn conf.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 240 --access-logfile -"]
