FROM python:3.11-slim

# Thư mục làm việc trong container
WORKDIR /app

# Copy & cài thư viện
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ source
COPY . .

# Cloud Run sẽ set PORT, mặc định 8080
ENV PORT=8080

# Chạy FastAPI với uvicorn
CMD ["sh", "-c", "uvicorn main_2fa_full:app --host 0.0.0.0 --port ${PORT:-8080}"]
