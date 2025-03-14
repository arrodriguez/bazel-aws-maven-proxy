# credential-renewer/renewer.py
import os
import time
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('credential-renewer')

# Configuration
AWS_PROFILE = os.environ.get('AWS_PROFILE', 'default')
SSO_CACHE_DIR = os.path.expanduser('~/.aws/sso/cache')
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', '900'))  # 15 minutes by default
RENEWAL_THRESHOLD = int(os.environ.get('RENEWAL_THRESHOLD', '3600'))  # 1 hour by default

def find_sso_token_file():
    """Find the latest SSO token file in the cache directory."""
    if not os.path.exists(SSO_CACHE_DIR):
        logger.warning(f"SSO cache directory does not exist: {SSO_CACHE_DIR}")
        return None
    
    # Find all JSON files in the SSO cache directory
    json_files = list(Path(SSO_CACHE_DIR).glob('*.json'))
    if not json_files:
        logger.warning("No SSO token files found in cache directory")
        return None
    
    # Get the most recently modified file
    latest_file = max(json_files, key=lambda f: f.stat().st_mtime)
    return latest_file

def check_token_expiration():
    """Check if the SSO token is nearing expiration."""
    token_file = find_sso_token_file()
    if not token_file:
        logger.info("No token file found, initiating login")
        return True
    
    try:
        with open(token_file, 'r') as f:
            token_data = json.load(f)
        
        # Check if the token has an expiration time
        if 'expiresAt' in token_data:
            expires_at = datetime.fromisoformat(token_data['expiresAt'].replace('Z', '+00:00'))
            now = datetime.now(expires_at.tzinfo)
            
            # Calculate time until expiration
            time_until_expiry = (expires_at - now).total_seconds()
            
            logger.info(f"Token expires in {time_until_expiry:.0f} seconds")
            
            # If token will expire soon, renew it
            if time_until_expiry < RENEWAL_THRESHOLD:
                logger.info(f"Token will expire soon ({time_until_expiry:.0f}s), initiating renewal")
                return True
            else:
                logger.info(f"Token still valid for {time_until_expiry:.0f} seconds")
                return False
        else:
            logger.warning("Token file does not contain expiration time")
            return True
    except Exception as e:
        logger.error(f"Error checking token expiration: {str(e)}")
        return True

def perform_sso_login():
    """Perform AWS SSO login using the configured profile."""
    try:
        logger.info(f"Performing AWS SSO login for profile {AWS_PROFILE}")
        
        # Ensure SSO cache directory exists
        os.makedirs(SSO_CACHE_DIR, exist_ok=True)
        
        # Run AWS SSO login command
        result = subprocess.run(
            ["aws", "sso", "login", "--profile", AWS_PROFILE],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            logger.info("AWS SSO login successful")
            return True
        else:
            logger.error(f"AWS SSO login failed: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Error during AWS SSO login: {str(e)}")
        return False

def main():
    """Main function to periodically check and renew AWS SSO credentials."""
    logger.info(f"Starting credential renewal service for profile: {AWS_PROFILE}")
    logger.info(f"Checking every {CHECK_INTERVAL} seconds")
    logger.info(f"Renewal threshold: {RENEWAL_THRESHOLD} seconds before expiration")
    
    while True:
        try:
            # Check if token needs renewal
            if check_token_expiration():
                perform_sso_login()
            
            # Sleep until next check
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"Error in renewal cycle: {str(e)}")
            time.sleep(60)  # Sleep for a minute on error

if __name__ == "__main__":
    main()
