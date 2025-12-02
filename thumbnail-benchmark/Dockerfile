FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Poppler utilities for pdf2image
    poppler-utils \
    # Build tools (may be needed for some packages)
    build-essential \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy benchmark code
COPY . .

# Create directories for PDFs and results
RUN mkdir -p sample_pdfs results

# Default command
CMD ["python", "benchmark.py", "--help"]
