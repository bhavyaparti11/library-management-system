# ---------------------------------------------------------------
# Dockerfile for the Library Management System
# Builds a small Linux image that runs the Flask app with Gunicorn
# ---------------------------------------------------------------

# 1. Start from an official, lightweight Python image
FROM python:3.12-slim

# 2. Python settings: no .pyc files, print logs immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/library.db

# 3. All following commands run inside /app in the container
WORKDIR /app

# 4. Install dependencies first (this layer is cached between builds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the application code
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# 6. Create a non-root user and a folder for the SQLite database
RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app/data
USER appuser

# 7. Document the port the app listens on
EXPOSE 5000

# 8. Let Docker check that the app is healthy
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:5000/health')"

# 9. Start the app with Gunicorn (a production-grade Python web server)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", \
     "--access-logfile", "-", "app:create_app()"]
