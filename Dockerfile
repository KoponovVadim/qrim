FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY credentials.json ./credentials.json

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
