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
COPY --from=builder /usr/local/bin/whispercrawl /usr/local/bin/whispercrawl

RUN useradd -r -u 1000 -s /bin/false appuser

# Mount points — host dirs are bind-mounted here at runtime
VOLUME ["/audio", "/logs"]

USER appuser

ENTRYPOINT ["whispercrawl", "--config", "/config.yaml"]
