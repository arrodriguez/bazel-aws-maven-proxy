import os
import time
import logging
import configparser
import subprocess
from playwright.sync_api import sync_playwright

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('sso-authenticator')

# Configuration from environment variables
AWS_PROFILE = os.environ.get('AWS_PROFILE', 'default')
SSO_USERNAME = os.environ.get('SSO_USERNAME')
SSO_PASSWORD = os.environ.get('SSO_PASSWORD')
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', '3'))
ENV_FILE = os.environ.get('ENV_FILE', '/.env')

def get_sso_config():
    """Extract SSO configuration from AWS config file."""
    config = configparser.ConfigParser()
    config.read(os.path.expanduser('~/.aws/config'))
    
    profile_section = f"profile {AWS_PROFILE}"
    if profile_section not in config:
        raise Exception(f"Profile {AWS_PROFILE} not found in AWS config")
    
    sso_start_url = config[profile_section].get("sso_start_url")
    sso_region = config[profile_section].get("sso_region")
    
    if not sso_start_url or not sso_region:
        raise Exception("SSO configuration missing in AWS profile")
    
    return sso_start_url, sso_region

def perform_sso_login():
    """Perform AWS SSO login using Playwright with Firefox."""
    if not SSO_USERNAME or not SSO_PASSWORD:
        raise Exception("SSO credentials not provided in environment variables")
    
    # Get SSO configuration
    sso_start_url, sso_region = get_sso_config()
    
    logger.info(f"Starting headless browser for SSO login (URL: {sso_start_url})")
    
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        
        try:
            # Navigate to SSO start URL
            page.goto(sso_start_url)
            logger.info("Navigated to SSO start URL")
            
            # Save screenshot for debugging
            page.screenshot(path="/tmp/login_page.png")
            logger.info("Login page screenshot saved to /tmp/login_page.png")
            
            # Wait for the login form and fill credentials
            # Note: Adjust these selectors based on your SSO provider's login page
            page.fill("#username", SSO_USERNAME)
            page.fill("#password", SSO_PASSWORD)
            page.click("#signin-button")
            
            logger.info("Credentials entered, waiting for authentication")
            
            # Wait for redirect after successful login
            page.wait_for_url("**/console*", timeout=30000)
            
            logger.info("SSO login completed successfully")
            page.screenshot(path="/tmp/post_login.png")
            
            # Allow time for AWS CLI to update token files
            time.sleep(5)
            
            return True
            
        except Exception as e:
            logger.error(f"Error during SSO login: {str(e)}")
            page.screenshot(path="/tmp/error.png")
            return False
        finally:
            browser.close()

def main():
    """Main function to perform SSO login and update credentials."""
    try:
        logger.info(f"Starting AWS SSO authentication for profile: {AWS_PROFILE}")
        
        success = perform_sso_login()
        if success:
            logger.info("AWS SSO login successful")
            return 0
        else:
            logger.error("AWS SSO login failed")
            return 1
    except Exception as e:
        logger.error(f"Unhandled exception in authenticator: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
