# Dùng Python 3.11 nhẹ và ổn định
FROM python:3.11-slim

# Tạo thư mục làm việc trong container
WORKDIR /app

# Copy file requirements và cài đặt dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy toàn bộ code vào container
COPY . .

# Chạy bot webhook bằng aiohttp
CMD ["python", "Bot_tk.py"]
