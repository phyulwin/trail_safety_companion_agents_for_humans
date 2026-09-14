# Dockerfile - Run the local SQLite API as an unprivileged container user.
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home trail && mkdir /data && chown trail:trail /data
COPY app ./app
USER trail
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=25s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
# The API has no published port; only the same-host proxy may supply forwarded headers.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
