# credential-monitor/monitor.py
import os
import time
import logging
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('credential-monitor')

# Configuration
AWS_PROFILE = os.environ.get('AWS_PROFILE', 'default')
AWS_DIR = os.path.expanduser('~/.aws')
CREDENTIAL_FILE = os.path.join(AWS_DIR, 'credentials')
CONFIG_FILE = os.path.join(AWS_DIR, 'config')
SSO_CACHE_DIR = os.path.join(AWS_DIR, 'sso/cache')

class CredentialEventHandler(FileSystemEventHandler):
    """Handles file system events related to AWS credentials."""
    
    def __init__(self):
        self.last_event_time = 0
        self.cooldown_period = 5  # seconds
    
    def on_modified(self, event):
        """Called when a file or directory is modified."""
        # Apply cooldown to prevent multiple restarts for related changes
        current_time = time.time()
        if current_time - self.last_event_time < self.cooldown_period:
            logger.debug(f"Ignoring event due to cooldown: {event.src_path}")
            return
        
        self.last_event_time = current_time
        
        # Process the event
        if event.is_directory:
            return
            
        # If the change is to the credentials file, config file, or SSO cache
        if (event.src_path == CREDENTIAL_FILE or
                event.src_path == CONFIG_FILE or
                event.src_path.startswith(SSO_CACHE_DIR)):
                
            logger.info(f"Detected change in AWS credentials: {event.src_path}")
            self._restart_s3proxy()
    
    def _restart_s3proxy(self):
        """Restart the S3 proxy container."""
        logger.info("Restarting s3proxy container...")
        try:
            subprocess.run(
                ["docker-compose", "restart", "s3proxy"], 
                check=True
            )
            logger.info("Successfully restarted s3proxy container")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart s3proxy: {e}")

def start_monitoring():
    """Start monitoring AWS credential files for changes."""
    # Create handler and observer
    event_handler = CredentialEventHandler()
    observer = Observer()
    
    # Set up directories to watch
    paths_to_watch = [
        CREDENTIAL_FILE,
        CONFIG_FILE,
        SSO_CACHE_DIR
    ]
    
    # Ensure SSO cache directory exists
    os.makedirs(SSO_CACHE_DIR, exist_ok=True)
    
    # Schedule monitoring
    for path in paths_to_watch:
        if os.path.exists(path):
            if os.path.isdir(path):
                observer.schedule(event_handler, path, recursive=True)
                logger.info(f"Monitoring directory: {path}")
            else:
                parent_dir = os.path.dirname(path)
                observer.schedule(event_handler, parent_dir, recursive=False)
                logger.info(f"Monitoring file: {path}")
    
    # Start the observer
    observer.start()
    logger.info(f"Started credential monitoring for profile: {AWS_PROFILE}")
    
    try:
        # Keep running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    start_monitoring()
