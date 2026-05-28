# Use Python base image
FROM python:3.11-slim

# Install system dependencies including FFmpeg and Node.js (required by yt-dlp as a JS runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Copy rest of application files
COPY . .

# Expose the port (Railway/Render will bind dynamically)
EXPOSE 8080

# Run the server
CMD ["python", "server.py"]
