FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt README.md /app/
COPY configs /app/configs
COPY src /app/src
RUN pip install --no-cache-dir -r requirements.txt
CMD ["python", "-m", "src.cli", "run", "--dataset", "run2012bc_doublemuparked", "--stage", "all"]
