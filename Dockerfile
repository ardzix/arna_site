FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libpq-dev \
    build-essential \
    python3-dev \
    libpcre2-dev \
    libssl-dev \
    libffi-dev \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=config.settings

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Arna SSO RS256 public key — diinject oleh CI sebelum docker build
# Lokal: letakkan public.pem di root project
# SSO_JWT_PUBLIC_KEY_PATH=public.pem di .env (di-resolve relatif ke BASE_DIR=/app)
COPY public.pem /app/public.pem

EXPOSE 8001

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
