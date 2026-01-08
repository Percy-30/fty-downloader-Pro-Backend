# =========================================================
# Dockerfile para SnapNosh Backend (FastAPI + Playwright)
# Producción optimizada para Render
# =========================================================

FROM python:3.11-slim

# Establecer directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para Playwright, ffmpeg y fuentes
RUN apt-get update && apt-get install -y \
    ffmpeg \
    wget \
    curl \
    fonts-unifont \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libwayland-client0 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# ✅ INSTALAR DENO (Robust configuration)
ENV DENO_INSTALL=/root/.deno
RUN curl -fsSL https://deno.land/install.sh | sh
ENV PATH="$DENO_INSTALL/bin:$PATH"
RUN ln -sf /root/.deno/bin/deno /usr/local/bin/deno && chmod +x /usr/local/bin/deno

# Copiar requirements.txt primero para aprovechar cache
COPY requirements.txt ./

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium para Playwright
RUN python -m playwright install chromium

# Copiar código fuente
COPY app/ ./app/

# Crear directorios necesarios
RUN mkdir -p /app/cookies /app/cache/yt_dlp && \
    touch /app/cookies/cookies.txt && \
    chmod -R 777 /app/cache

# Variables de entorno
ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000
ENV YOUTUBE_COOKIES_PATH=/app/cookies/cookies.txt

# Exponer puerto
EXPOSE 8000

# Healthcheck para Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Comando por defecto para producción (Gunicorn + Uvicorn workers)
CMD gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT --timeout 300

#CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "300"]
