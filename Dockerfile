FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    playwright install --with-deps chromium

COPY soho_appt_monitor.py .

CMD ["python", "soho_appt_monitor.py"]
