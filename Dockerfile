FROM python:3.12-slim

WORKDIR /service

# Install deps first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

EXPOSE 8081

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
