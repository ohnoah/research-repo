FROM python:3.11-slim-bookworm

# Install system dependencies for PDF tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        mupdf-tools \
        poppler-utils \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directories for sample PDFs and results
RUN mkdir -p /app/sample_pdfs /app/results

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command
CMD ["python", "benchmark.py"]
