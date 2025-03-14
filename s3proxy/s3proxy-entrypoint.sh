#!/bin/bash
##############################################################
# S3 Proxy Entrypoint
# 
# Provides a stable HTTP endpoint for Bazel to access Maven artifacts
# stored in private S3 buckets, handling AWS authentication transparently.
##############################################################

set -e

# Configuration
S3_BUCKET_NAME=${S3_BUCKET_NAME:-"maven.recargapay.com"}
AWS_PROFILE=${AWS_PROFILE:-"default"}
AWS_REGION=${AWS_REGION:-"sa-east-1"}
LOG_LEVEL=${LOG_LEVEL:-"info"}

# Function to log with timestamp and level
log() {
    local level=$1
    local message=$2
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    
    # Only log if level is appropriate
    case $LOG_LEVEL in
        debug)
            echo "[$timestamp] $level: $message"
            ;;
        info)
            if [[ "$level" != "DEBUG" ]]; then
                echo "[$timestamp] $level: $message"
            fi
            ;;
        warn|warning)
            if [[ "$level" != "DEBUG" && "$level" != "INFO" ]]; then
                echo "[$timestamp] $level: $message"
            fi
            ;;
        error)
            if [[ "$level" == "ERROR" ]]; then
                echo "[$timestamp] $level: $message"
            fi
            ;;
    esac
}

log "INFO" "Starting S3 proxy for bucket: $S3_BUCKET_NAME"
log "INFO" "Using AWS profile: $AWS_PROFILE"
log "INFO" "Using AWS region: $AWS_REGION"

# Function to refresh AWS credentials from various sources
refresh_credentials() {
    log "INFO" "Refreshing AWS credentials..."
    
    # First try environment variables
    if [[ -n "$AWS_ACCESS_KEY_ID" && -n "$AWS_SECRET_ACCESS_KEY" ]]; then
        log "INFO" "Using AWS credentials from environment variables"
        # No need to do anything, MC will use these automatically
        return 0
    fi
    
    # Try using SSO or role-based credentials
    log "DEBUG" "Attempting to get credentials from AWS CLI session..."
    
    # Use the specified profile if provided
    local profile_arg=""
    if [[ -n "$AWS_PROFILE" ]]; then
        profile_arg="--profile $AWS_PROFILE"
    fi
    
    # Try getting session token first (works for regular IAM users)
    AWS_CREDS=$(aws sts get-session-token $profile_arg 2>/dev/null || echo "")
    
    # If that failed, try get-caller-identity (works for SSO and roles)
    if [[ -z "$AWS_CREDS" || "$AWS_CREDS" == "{}" ]]; then
        log "DEBUG" "Session token unavailable, trying caller identity..."
        AWS_IDENTITY=$(aws sts get-caller-identity $profile_arg 2>/dev/null || echo "")
        
        if [[ -z "$AWS_IDENTITY" ]]; then
            log "ERROR" "Failed to obtain valid AWS credentials"
            log "ERROR" "Please ensure you're logged in with 'aws sso login' or have valid credentials"
            return 1
        else
            log "INFO" "Successfully verified AWS identity"
            # We need to extract credentials from the shared credentials file
            if [[ -f ~/.aws/credentials ]]; then
                log "DEBUG" "Reading credentials from shared credentials file"
                export AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id $profile_arg)
                export AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key $profile_arg)
                export AWS_SESSION_TOKEN=$(aws configure get aws_session_token $profile_arg)
            else
                log "ERROR" "Could not find AWS credentials file"
                return 1
            fi
        fi
    else
        # Extract credentials from the session token response
        log "DEBUG" "Extracting credentials from session token"
        export AWS_ACCESS_KEY_ID=$(echo $AWS_CREDS | jq -r '.Credentials.AccessKeyId')
        export AWS_SECRET_ACCESS_KEY=$(echo $AWS_CREDS | jq -r '.Credentials.SecretAccessKey')
        export AWS_SESSION_TOKEN=$(echo $AWS_CREDS | jq -r '.Credentials.SessionToken')
    fi
    
    # Verify we have the necessary credentials
    if [[ -z "$AWS_ACCESS_KEY_ID" || "$AWS_ACCESS_KEY_ID" == "null" ]]; then
        log "ERROR" "Failed to obtain valid AWS access key"
        return 1
    fi
    
    # Configure MinIO client with the credentials
    log "INFO" "Configuring MinIO client with AWS credentials"
    mc alias set aws-s3 https://s3.amazonaws.com "$AWS_ACCESS_KEY_ID" "$AWS_SECRET_ACCESS_KEY" --api S3v4
    
    if [[ $? -ne 0 ]]; then
        log "ERROR" "Failed to configure MinIO client"
        return 1
    fi
    
    # Test access to the bucket
    log "DEBUG" "Testing access to S3 bucket: $S3_BUCKET_NAME"
    mc ls aws-s3/$S3_BUCKET_NAME > /dev/null
    
    if [[ $? -ne 0 ]]; then
        log "ERROR" "Failed to access S3 bucket: $S3_BUCKET_NAME"
        log "ERROR" "Please check your permissions or bucket name"
        return 1
    fi
    
    log "INFO" "Successfully refreshed AWS credentials"
    return 0
}

# Function to create a health check endpoint
setup_health_endpoint() {
    log "INFO" "Setting up health check endpoint"
    mkdir -p /data/healthz
    echo "OK" > /data/healthz/index.html
}

# Function to start the proxy server
start_proxy() {
    log "INFO" "Starting proxy server on port 9000"
    
    # Ensure data directory exists
    mkdir -p /data
    
    # Set up health check endpoint
    setup_health_endpoint
    
    # Start MinIO mirror in background - this keeps the local cache in sync with S3
    log "DEBUG" "Starting MinIO mirror process"
    mc mirror --watch --overwrite aws-s3/$S3_BUCKET_NAME /data &
    MIRROR_PID=$!
    
    # Start HTTP server to serve the content
    log "INFO" "Starting HTTP server"
    mc server /data --address ":9000" &
    SERVER_PID=$!
    
    # Wait for either process to exit
    wait -n $MIRROR_PID $SERVER_PID
    
    log "WARN" "One of the background processes exited unexpectedly"
    return 1
}

# Main execution loop
while true; do
    # Refresh credentials
    refresh_credentials
    
    if [[ $? -eq 0 ]]; then
        # Start proxy with current credentials
        start_proxy
        
        if [[ $? -ne 0 ]]; then
            log "WARN" "Proxy server exited, restarting..."
            sleep 5
        fi
    else
        log "ERROR" "Failed to refresh credentials, retrying in 30 seconds..."
        sleep 30
    fi
done
