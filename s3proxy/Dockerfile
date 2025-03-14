# First stage: Use MinIO client image to get the MC binary
FROM minio/mc:latest as mc

# Second stage: Build our final image
FROM alpine:3.17

# Install dependencies
RUN apk add --no-cache \
    bash \
    jq \
    curl \
    aws-cli

# Copy MC binary from the first stage
COPY --from=mc /usr/bin/mc /usr/local/bin/mc
RUN chmod +x /usr/local/bin/mc

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
