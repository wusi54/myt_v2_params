FROM python:3.11-slim

WORKDIR /app

# 系统依赖（最小）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 持久化目录
RUN mkdir -p /app/web/data /app/output /app/templates/cell_pools

ENV PYTHONUNBUFFERED=1
EXPOSE 5000

CMD ["python", "web/app.py"]