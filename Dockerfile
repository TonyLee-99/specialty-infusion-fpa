# Reproducible environment. Default command is the offline gate; run `make reproduce` inside the
# container (with network) to rebuild from public CMS/CDC/Census sources.
# Build: docker build -t specialty-infusion-fpa .
# Run:   docker run --rm specialty-infusion-fpa            # make check
#        docker run --rm specialty-infusion-fpa make reproduce
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends make git curl ca-certificates \
        libreoffice-calc-nogui \
    && rm -rf /var/lib/apt/lists/*
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv venv --python 3.12 .venv && uv sync --frozen && .venv/bin/playwright install --with-deps chromium
COPY . .
CMD ["make", "check"]
