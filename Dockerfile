FROM python:3.11-slim

# Metadata
LABEL maintainer="Satya Sai Ganesh Yerramsetti <satyasaiganeshyerramsetti@my.unt.edu>"
LABEL description="LLM Observability Polling Pipeline"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/       ./src/
COPY config/    ./config/
COPY main.py    .

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s \
    CMD python -c "import src.poller; print('OK')" || exit 1

EXPOSE $PORT

CMD ["python", "main.py"]
