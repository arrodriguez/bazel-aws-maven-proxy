# bazel-aws-maven-proxy
# Bazel AWS Maven Proxy

[![GitHub License](https://img.shields.io/github/license/yourusername/bazel-aws-maven-proxy)](https://github.com/yourusername/bazel-aws-maven-proxy/blob/main/LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/yourusername/bazel-aws-maven-proxy)](https://hub.docker.com/r/yourusername/bazel-aws-maven-proxy)
[![GitHub stars](https://img.shields.io/github/stars/yourusername/bazel-aws-maven-proxy)](https://github.com/yourusername/bazel-aws-maven-proxy/stargazers)

A seamless integration layer between Bazel's Maven artifact system and private AWS S3 buckets that supports modern AWS authentication methods including SSO.

## The Problem

Using Bazel with private Maven repositories in AWS S3 face a significant challenge: most available tools were designed when static, long-lived AWS credentials were the norm. In today's security environment with short-lived credentials, SSO workflows, and regular credential rotation, these tools break frequently, forcing developers to:

- Restart build environments after credential refresh
- Manually update access keys whenever SSO sessions expire
- Choose between security best practices and developer productivity

## Solution

Bazel AWS Maven Proxy addresses these challenges by creating a local proxy server that:

1. **Automatically detects AWS credential changes** using efficient filesystem event monitoring
2. **Dynamically refreshes S3 authentication** when SSO tokens or credentials are updated
3. **Presents a simple HTTP interface** to Bazel that remains stable regardless of credential changes
4. **Caches artifacts locally** for improved build performance

![Architecture Overview](docs/architecture.png)

## Features

- **Zero-config AWS authentication**: Works with AWS SSO, IAM roles, environment variables, and static credentials
- **Real-time credential monitoring**: Using filesystem events (not polling) for immediate detection of credential changes
- **Proactive token management**: Detects expiring SSO tokens and refreshes them before they cause build failures
- **Container-based implementation**: Easy to deploy and integrate with existing workflows
- **Compatible with all Bazel versions**: No custom Bazel plugins or patching required

## Quick Start

### Prerequisites

- Docker and Docker Compose
- AWS CLI configured with SSO or other authentication method
- Bazel-based project with Maven dependencies

### Installation

1. Clone this repository:

```bash
git clone https://github.com/yourusername/bazel-aws-maven-proxy.git
cd bazel-aws-maven-proxy
```

2. Configure your S3 bucket settings:

```bash
cp .env.example .env
# Edit .env with your bucket details
```

3. Start the services:

```bash
docker-compose up -d
```

4. Configure your Bazel project to use the proxy:

Add to your `.bazelrc`:

```
# Use local proxy for Maven artifacts
build --define=maven_repo=http://localhost:9000/
```

Update your `WORKSPACE` file:

```python
load("@rules_jvm_external//:defs.bzl", "maven_install")

maven_install(
    name = "maven",
    artifacts = [
        # Your Maven dependencies here
    ],
    repositories = [
        "http://localhost:9000/",  # Our S3 proxy
        "https://repo1.maven.org/maven2",  # Fallback to Maven Central
    ],
)
```

That's it! Your Bazel builds will now use the proxy, which handles all the AWS credential management for you.

## How It Works

### Component Architecture

![Component Diagram](docs/components.png)

Bazel AWS Maven Proxy consists of three main components:

1. **Credential Monitor Service** (`credential-monitor`)
   - Watches AWS credential files and SSO token cache for changes
   - Uses filesystem events for efficient monitoring
   - Triggers credential refresh operations when changes are detected
   - Proactively checks for expiring tokens

2. **S3 Proxy Service** (`s3proxy`)
   - Acts as a bridge between Bazel and your S3 bucket
   - Handles authentication with AWS using current credentials
   - Provides a stable HTTP endpoint for Bazel
   - Implements artifact caching for performance

3. **Local Cache Volume** (`maven-cache`)
   - Persists Maven artifacts between builds
   - Improves build speed by reducing S3 requests
   - Avoids duplicate downloads across team members

### Authentication Flow

1. Developer runs `aws sso login` (or other AWS authentication)
2. Credential Monitor detects the new/updated credentials file
3. Proxy Service refreshes its AWS tokens
4. Bazel requests artifacts through the proxy
5. Proxy authenticates to S3 using current credentials
6. Artifacts are cached locally and served to Bazel

This flow continues working even as SSO tokens expire and are refreshed, ensuring uninterrupted builds.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_PROFILE` | AWS CLI profile to use | `default` |
| `AWS_REGION` | AWS region for S3 bucket | `us-west-2` |
| `S3_BUCKET_NAME` | Name of your Maven S3 bucket | (required) |
| `PROXY_PORT` | Local port for the proxy service | `9000` |
| `REFRESH_INTERVAL` | Token expiration check interval (ms) | `60000` |
| `LOG_LEVEL` | Logging verbosity | `info` |

### Advanced Configuration

For advanced scenarios such as multiple buckets, custom authentication flows, or enterprise environments, see our [Advanced Configuration Guide](docs/advanced-configuration.md).

## Performance Considerations

### Local Caching

The proxy maintains a local cache in the `maven-cache` Docker volume, which dramatically improves build times for repeatedly used artifacts. To clear this cache:

```bash
docker-compose down
docker volume rm bazel-aws-maven-proxy_maven-cache
docker-compose up -d
```

### Resource Usage

The system is designed to be extremely lightweight:

- **Credential Monitor**: ~20MB memory, negligible CPU (event-based)
- **S3 Proxy**: 50-100MB memory, light CPU usage during artifact retrieval
- **Disk Usage**: Varies based on your artifact size and count

## Troubleshooting

### Logs

View service logs:

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs credential-monitor
docker-compose logs s3proxy
```

### Common Issues

**Q: Bazel can't connect to the proxy**
A: Check that Docker Compose is running (`docker-compose ps`) and that port 9000 is not being used by another service.

**Q: Proxy shows authentication errors**
A: Verify that your AWS authentication is working with `aws s3 ls s3://your-bucket-name/`.

**Q: Artifacts aren't being found**
A: Ensure your S3 bucket is correctly configured in `.env` and that the path structure matches what Bazel expects.

For more troubleshooting tips, see our [Troubleshooting Guide](docs/troubleshooting.md).

## Implementation Details

### Credential Monitor Implementation

The Credential Monitor uses Node.js with the `chokidar` library to efficiently watch for filesystem changes:

```javascript
// Key parts of aws-sso-credential-monitor.js
const chokidar = require('chokidar');
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

// ... setup paths and configuration ...

// Initialize watchers using filesystem events
const watcher = chokidar.watch([credentialsFile, `${ssoCache}/*.json`], {
    persistent: true,
    awaitWriteFinish: {
        stabilityThreshold: 1000,
        pollInterval: 100
    }
});

// Add event listeners
watcher
    .on('add', path => {
        console.log(`AWS file added: ${path}`);
        triggerRefresh('new file');
    })
    .on('change', path => {
        console.log(`AWS file changed: ${path}`);
        triggerRefresh('file change');
    });

// Proactively check for expiring tokens
function checkSsoTokens() {
    // ... implementation that checks token expiration times ...
    // ... and triggers refresh before they expire ...
}

// Periodically check token expiration
setInterval(checkSsoTokens, refreshInterval);
```

This approach is significantly more efficient than polling solutions, responding immediately to credential changes while consuming minimal resources.

### S3 Proxy Implementation

The S3 Proxy uses MinIO client tools to provide a simple yet powerful interface to S3:

```bash
#!/bin/bash
# s3proxy-entrypoint.sh

refresh_credentials() {
    # ... implementation that obtains current AWS credentials ...
    # ... configures MinIO client with those credentials ...
}

start_proxy() {
    # ... implementation that starts HTTP server with S3 mirroring ...
}

# Main execution flow
while true; do
    refresh_credentials
    if [ $? -eq 0 ]; then
        start_proxy &
        wait $!
        echo "Proxy exited, restarting..."
    else
        echo "Failed to refresh credentials, retrying in 30 seconds..."
        sleep 30
    fi
done
```

## Security Considerations

### Credential Handling

- AWS credentials are never copied or stored outside your local `.aws` directory
- The containers only have read-only access to credential files
- No credentials are exposed in container environment variables or logs
- All credential handling follows AWS best practices

### Network Security

- The proxy only listens on localhost by default
- No inbound connections are required
- All S3 communication uses HTTPS with AWS signature v4 authentication

### Team Environments

For team environments, consider:

- Deploying the proxy as a service on your development servers
- Implementing proper access controls for shared caches
- Creating team-specific configuration guides

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on how to submit pull requests, report issues, or suggest enhancements.

### Development Setup

1. Fork and clone the repository
2. Install development dependencies:

```bash
npm install
```

3. Run tests:

```bash
npm test
```

4. Start services in development mode:

```bash
docker-compose -f docker-compose.dev.yml up
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- The [Bazel](https://bazel.build/) team for their amazing build system
- [MinIO](https://min.io/) for their excellent S3-compatible tools
- All contributors who have helped improve this project

## Project Maintainers

- [Your Name](https://github.com/yourusername) - Principal Engineer at [Your Company]
- [Contributor Name](https://github.com/contributor) - Senior Software Engineer at [Their Company]

---

**Bazel AWS Maven Proxy** | Making Bazel and AWS SSO work together seamlessly

Aws S3 Maven proxy for bazel
