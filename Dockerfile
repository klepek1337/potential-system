FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY ma_alert_bot ./ma_alert_bot

CMD ["python", "-m", "ma_alert_bot"]
