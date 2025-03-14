#!/bin/bash
# run.sh - Wrapper script for SSO authenticator

# Set up error handling
set -e

echo "Starting AWS SSO Authenticator"

# Run the Python authentication script
python /app/authenticator.py

# Check exit status
status=$?
if [ $status -eq 0 ]; then
    echo "SSO authentication completed successfully"
    exit 0
else
    echo "SSO authentication failed with status $status"
    exit $status
fi
