FROM minio/mc:latest

# Install dependencies
RUN microdnf install -y \
    jq \
    curl \
    aws-cli \
    && microdnf clean all

# Create necessary directories
RUN mkdir -p /data /root/.aws

# Copy entrypoint script
COPY s3proxy-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/s3proxy-entrypoint.sh

# Set up health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8888/healthz || exit 1

# Expose the proxy port
EXPOSE 8888

# Run the entrypoint script
ENTRYPOINT ["/usr/local/bin/s3proxy-entrypoint.sh"]
