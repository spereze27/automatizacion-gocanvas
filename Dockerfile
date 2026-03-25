FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Cuando el contenedor inicie, simplemente corre el script
CMD ["python", "main.py"]