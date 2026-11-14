FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml ./
COPY switchboard ./switchboard
RUN pip install --no-cache-dir . && useradd -r -u 10001 app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
CMD ["python", "-m", "switchboard"]
