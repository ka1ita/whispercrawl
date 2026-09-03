# Stage 1: install dependencies and package
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

# Stage 2: minimal runtime image
FROM python:3.11-slim AS runtime

# Copy installed package and entry point from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/asr-crawler /usr/local/bin/asr-crawler

RUN useradd -r -u 1000 -s /bin/false appuser

# Mount points — host dirs are bind-mounted here at runtime
VOLUME ["/audio", "/logs", "/db"]

USER appuser

ENTRYPOINT ["asr-crawler", "--config", "/config.yaml"]
