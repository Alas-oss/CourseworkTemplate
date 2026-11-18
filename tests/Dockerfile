FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir requests==2.32.3

COPY test_system.py .

CMD ["python", "-m", "unittest", "-v", "test_system"]