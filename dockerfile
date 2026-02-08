FROM python:3.11-slim

# Install system fonts for Pillow labels
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# SQLite is built into Python, no extra install needed
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-10000}"]
