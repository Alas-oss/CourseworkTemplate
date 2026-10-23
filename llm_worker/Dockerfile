FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-c", "import time; print('llm-worker placeholder', flush=True); time.sleep(10**9)"]

