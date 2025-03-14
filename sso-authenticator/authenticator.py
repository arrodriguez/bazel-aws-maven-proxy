import os
import time
import json
import logging
import configparser
import subprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

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
    """Perform AWS SSO login using headless Chrome."""
    if not SSO_USERNAME or not SSO_PASSWORD:
        raise Exception("SSO credentials not provided in environment variables")
    
    # Get SSO configuration
    sso_start_url, sso_region = get_sso_config()
    
    logger.info(f"Starting headless browser for SSO login (URL: {sso_start_url})")
    
    # Configure Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Initialize browser with retry logic
    for attempt in range(MAX_RETRIES):
        try:
            browser = webdriver.Chrome(options=chrome_options)
            break
        except WebDriverException as e:
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"Browser initialization failed (attempt {attempt + 1}): {e}")
                time.sleep(2)
            else:
                logger.error(f"Failed to initialize browser after {MAX_RETRIES} attempts: {e}")
                raise
    
    try:
        # Start AWS SSO login
        browser.get(sso_start_url)
        logger.info("Browser navigated to SSO start URL")
        
        # Wait for login form - this may vary depending on your SSO provider
        try:
            username_field = WebDriverWait(browser, 20).until(
                EC.presence_of_element_located((By.ID, "username"))
            )
            
            # Save screenshot for debugging
            browser.save_screenshot("/tmp/login_page.png")
            logger.info("Login page loaded, screenshot saved to /tmp/login_page.png")
            
            # Enter credentials
            username_field.send_keys(SSO_USERNAME)
            browser.find_element(By.ID, "password").send_keys(SSO_PASSWORD)
            browser.find_element(By.ID, "signin-button").click()
            
            logger.info("Credentials entered, clicked sign-in button")
            
            # Wait for authentication to complete
            WebDriverWait(browser, 30).until(
                EC.url_contains("console")  # Adjust based on your SSO provider's redirect pattern
            )
            
            logger.info("SSO login completed successfully in browser")
            browser.save_screenshot("/tmp/post_login.png")
            
            # Allow some time for the AWS CLI to update token files
            time.sleep(5)
            
            return True
            
        except TimeoutException:
            logger.error("Timed out waiting for login form or redirect")
            browser.save_screenshot("/tmp/timeout_error.png")
            return False
            
    except Exception as e:
        logger.error(f"Error during SSO login: {str(e)}")
        return False
    finally:
        browser.quit()

def extract_and_update_credentials():
    """Extract AWS credentials and update environment file."""
    try:
        logger.info("Extracting AWS credentials from profile")
        
        # Use AWS CLI to get credentials
        aws_access_key = subprocess.check_output(
            ['aws', 'configure', 'get', 'aws_access_key_id', '--profile', AWS_PROFILE],
            text=True
        ).strip()
        
        aws_secret_key = subprocess.check_output(
            ['aws', 'configure', 'get', 'aws_secret_access_key', '--profile', AWS_PROFILE],
            text=True
        ).strip()
        
        # Session token might not exist for some credential types
        try:
            aws_session_token = subprocess.check_output(
                ['aws', 'configure', 'get', 'aws_session_token', '--profile', AWS_PROFILE],
                text=True
            ).strip()
        except subprocess.CalledProcessError:
            aws_session_token = ""
        
        # Verify we have valid credentials
        if not aws_access_key or not aws_secret_key:
            logger.error("Failed to extract valid AWS credentials")
            return False
        
        # Update environment file
        logger.info(f"Updating environment file: {ENV_FILE}")
        
        # Read existing environment file
        env_lines = []
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE, 'r') as f:
                env_lines = f.readlines()
        
        # Filter out existing AWS credential entries
        env_lines = [line for line in env_lines if not (
            line.startswith('AWS_ACCESS_KEY_ID=') or
            line.startswith('AWS_SECRET_ACCESS_KEY=') or
            line.startswith('AWS_SESSION_TOKEN=')
        )]
        
        # Add new credentials
        env_lines.append(f"AWS_ACCESS_KEY_ID={aws_access_key}\n")
        env_lines.append(f"AWS_SECRET_ACCESS_KEY={aws_secret_key}\n")
        if aws_session_token:
            env_lines.append(f"AWS_SESSION_TOKEN={aws_session_token}\n")
        
        # Write updated environment file
        with open(ENV_FILE, 'w') as f:
            f.writelines(env_lines)
        
        logger.info("Successfully updated environment file with new credentials")
        
        # Check if docker-compose is available and restart the s3proxy
        try:
            logger.info("Attempting to restart s3proxy to use new credentials")
            subprocess.run(
                ['docker-compose', 'restart', 's3proxy'],
                check=False
            )
        except Exception as e:
            logger.warning(f"Could not restart s3proxy: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Error extracting and updating credentials: {str(e)}")
        return False

def main():
    """Main function to perform SSO login and update credentials."""
    try:
        logger.info(f"Starting AWS SSO authentication for profile: {AWS_PROFILE}")
        
        success = perform_sso_login()
        if success:
            logger.info("AWS SSO login successful")
            
            # Extract and update credentials
            if extract_and_update_credentials():
                logger.info("Credential extraction and update successful")
                return 0
            else:
                logger.error("Credential extraction failed after successful login")
                return 1
        else:
            logger.error("AWS SSO login failed")
            return 1
    except Exception as e:
        logger.error(f"Unhandled exception in authenticator: {str(e)}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
