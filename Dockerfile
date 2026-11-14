FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml ./
COPY switchboard ./switchboard
RUN pip install --no-cache-dir . && mkdir -p /data
EXPOSE 8000
CMD ["python", "-m", "switchboard"]
