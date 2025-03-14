FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    docker.io \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install AWS CLI
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf awscliv2.zip aws

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install firefox --with-deps

# Copy application code
COPY authenticator_playwright.py authenticator.py
COPY run.sh .
RUN chmod +x run.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the authenticator
CMD ["/app/run.sh"]
