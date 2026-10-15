# Veritas Engine backend - multi-stage image with full media forensics.
#   build:  docker build -t veritas-engine ./backend
#   run:    docker compose up   (from the repository root)

# ---------------------------------------------------------------- builder: Python dependencies
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt requirements-media.txt ./
# Full forensics in the container: yt-dlp, Pillow and c2pa-python. FFmpeg comes from the OS
# (runtime stage), so the bundled imageio-ffmpeg binary is not needed but harmless.
RUN pip install -r requirements-media.txt

# ---------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

# ffmpeg: audio/keyframe extraction · exiftool: video/audio/image metadata · libmagic1: MIME sniffing
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libimage-exiftool-perl libmagic1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VERITAS_MEDIA_TMP_DIR=/tmp/veritas-media

COPY --from=builder /opt/venv /opt/venv

RUN useradd --create-home --uid 10001 veritas \
    && mkdir -p /tmp/veritas-media \
    && chown veritas:veritas /tmp/veritas-media

WORKDIR /app
COPY --chown=veritas:veritas app ./app
COPY --chown=veritas:veritas .env.example ./.env.example

USER veritas
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
