FROM node:16-alpine

# Install Docker CLI for service restart capability
RUN apk add --no-cache docker-cli bash

WORKDIR /app

# Copy package definitions
COPY package.json ./
COPY package-lock.json ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY aws-sso-credential-monitor.js ./

# Run as non-root user for better security
USER node

# Set environment variables
ENV NODE_ENV=production

# Start the credential monitor
CMD ["node", "aws-sso-credential-monitor.js"]
