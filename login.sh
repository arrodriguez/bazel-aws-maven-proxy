#!/bin/bash
# login.sh - Helper script for AWS SSO login

# Get AWS profile from command line or use default
AWS_PROFILE=${1:-default}

echo "===== AWS SSO Login Helper ====="
echo "Using AWS Profile: $AWS_PROFILE"

# Get SSO configuration from AWS profile
CONFIG_FILE="$HOME/.aws/config"
if [ -f "$CONFIG_FILE" ]; then
    # Extract SSO start URL and region
    SSO_START_URL=$(grep -A10 "^\[profile $AWS_PROFILE\]" "$CONFIG_FILE" | grep "sso_start_url" | head -1 | cut -d'=' -f2 | tr -d ' ')
    SSO_REGION=$(grep -A10 "^\[profile $AWS_PROFILE\]" "$CONFIG_FILE" | grep "sso_region" | head -1 | cut -d'=' -f2 | tr -d ' ')
    
    if [ -n "$SSO_START_URL" ] && [ -n "$SSO_REGION" ]; then
        echo "SSO Start URL: $SSO_START_URL"
        echo "SSO Region: $SSO_REGION"
    else
        echo "This doesn't appear to be an SSO profile. Continuing anyway..."
    fi
else
    echo "AWS config file not found at $CONFIG_FILE"
fi

# Perform SSO login
echo -e "\nStarting AWS SSO login process..."
aws sso login --profile "$AWS_PROFILE"

# Check if login was successful
if [ $? -eq 0 ]; then
    echo -e "\nAWS SSO login successful!"
    echo "The credential monitor will automatically detect the new credentials and update the proxy."
    echo "You can continue using Bazel with S3 proxy for Maven artifacts."
else
    echo -e "\nAWS SSO login failed."
    echo "Please check your AWS configuration and try again."
    exit 1
fi
