# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# تنظیم متغیر محیطی برای locale (در صورت نیاز)
ENV LANG C.UTF-8

# بارگذاری env در زمان اجرا
ENV PYTHONUNBUFFERED=1

EXPOSE 8443

CMD ["python", "main.py"] 