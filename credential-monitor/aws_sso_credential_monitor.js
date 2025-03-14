/**
 * AWS SSO Credential Monitor
 * 
 * This service monitors AWS credential files and SSO token cache for changes,
 * triggering refresh operations when necessary to maintain continuous access
 * to S3 resources for Bazel builds.
 * 
 * Features:
 * - Filesystem event-based monitoring (not polling)
 * - Proactive SSO token expiration detection
 * - Docker service management integration
 */

const chokidar = require('chokidar');
const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');
const winston = require('winston');

// Configuration from environment variables
const profile = process.env.AWS_PROFILE || 'default';
const refreshInterval = parseInt(process.env.REFRESH_INTERVAL || '60000', 10);
const logLevel = process.env.LOG_LEVEL || 'info';

// Configure logger
const logger = winston.createLogger({
  level: logLevel,
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.printf(({ level, message, timestamp }) => {
      return `${timestamp} ${level.toUpperCase()}: ${message}`;
    })
  ),
  transports: [
    new winston.transports.Console()
  ]
});

// Determine paths based on environment
const homeDir = process.env.HOME || process.env.USERPROFILE;
const awsDir = path.join(homeDir, '.aws');
const credentialsFile = process.env.AWS_SHARED_CREDENTIALS_FILE || path.join(awsDir, 'credentials');
const configFile = path.join(awsDir, 'config');
const ssoCache = path.join(awsDir, 'sso', 'cache');

logger.info(`Starting AWS credential monitor for profile: ${profile}`);
logger.info(`Monitoring credentials file: ${credentialsFile}`);
logger.info(`Monitoring config file: ${configFile}`);
logger.info(`Monitoring SSO cache directory: ${ssoCache}`);
logger.info(`Token refresh interval: ${refreshInterval}ms`);

// Create directories if they don't exist
if (!fs.existsSync(ssoCache)) {
    logger.info(`SSO cache directory doesn't exist, creating: ${ssoCache}`);
    fs.mkdirSync(ssoCache, { recursive: true });
}

// Restarts the S3 proxy service to pick up new credentials
function restartProxyService() {
    logger.info('Restarting s3proxy service to apply new credentials');
    
    exec('docker-compose restart s3proxy', (error, stdout, stderr) => {
        if (error) {
            logger.error(`Error restarting s3proxy: ${error.message}`);
            return;
        }
        
        logger.debug(`s3proxy restart stdout: ${stdout}`);
        
        if (stderr) {
            logger.warn(`s3proxy restart stderr: ${stderr}`);
        }
        
        logger.info('s3proxy service restarted successfully');
    });
}

// Throttle function to prevent multiple rapid restarts
function throttle(func, limit) {
    let lastRun = 0;
    let timeout = null;
    
    return function() {
        const now = Date.now();
        const context = this;
        const args = arguments;
        
        if (now - lastRun < limit) {
            clearTimeout(timeout);
            timeout = setTimeout(function() {
                lastRun = now;
                func.apply(context, args);
            }, limit - (now - lastRun));
        } else {
            lastRun = now;
            func.apply(context, args);
        }
    };
}

// Throttled restart function (at most once every 5 seconds)
const throttledRestart = throttle(restartProxyService, 5000);

// Trigger refresh when a change is detected
function triggerRefresh(reason, path) {
    logger.info(`Credential change detected: ${reason} in ${path}`);
    throttledRestart();
}

// Check for SSO token expiration
function checkSsoTokens() {
    try {
        if (!fs.existsSync(ssoCache)) {
            return;
        }
        
        const files = fs.readdirSync(ssoCache);
        let tokenRefreshNeeded = false;
        let earliestExpiringToken = Infinity;
        
        files.forEach(file => {
            if (file.endsWith('.json')) {
                const filePath = path.join(ssoCache, file);
                
                try {
                    const content = fs.readFileSync(filePath, 'utf8');
                    const token = JSON.parse(content);
                    
                    // Check for token expiration
                    if (token.expiresAt) {
                        const expiresAt = new Date(token.expiresAt);
                        const now = new Date();
                        const timeUntilExpiration = expiresAt - now;
                        const fifteenMinutes = 15 * 60 * 1000;
                        
                        // Update earliest expiring token
                        if (timeUntilExpiration < earliestExpiringToken) {
                            earliestExpiringToken = timeUntilExpiration;
                        }
                        
                        // If token expires within 15 minutes, we should refresh
                        if (timeUntilExpiration < fifteenMinutes) {
                            logger.info(`SSO token in ${file} is expiring in ${Math.floor(timeUntilExpiration / 60000)} minutes`);
                            tokenRefreshNeeded = true;
                        }
                    }
                } catch (err) {
                    logger.warn(`Error parsing SSO token ${file}: ${err.message}`);
                }
            }
        });
        
        if (tokenRefreshNeeded) {
            triggerRefresh('SSO token expiration', 'scheduled check');
        } else if (earliestExpiringToken !== Infinity) {
            logger.debug(`Earliest token expires in ${Math.floor(earliestExpiringToken / 60000)} minutes`);
        }
    } catch (err) {
        logger.error(`Error checking SSO tokens: ${err.message}`);
    }
}

// Initialize file watchers with appropriate configuration
const watcher = chokidar.watch(
    [
        credentialsFile,
        configFile,
        `${ssoCache}/*.json`
    ],
    {
        persistent: true,
        ignoreInitial: false, // Process existing files on startup
        awaitWriteFinish: {
            stabilityThreshold: 1000, // Wait 1s after file stops changing
            pollInterval: 100        // Check every 100ms
        },
        atomic: true // For handling atomic writes (some AWS CLI operations)
    }
);

// Add event listeners for file changes
watcher
    .on('add', path => {
        logger.debug(`File added: ${path}`);
        // Only trigger on initial load if the file is not empty
        if (fs.statSync(path).size > 0) {
            triggerRefresh('new file', path);
        }
    })
    .on('change', path => {
        logger.debug(`File changed: ${path}`);
        triggerRefresh('file change', path);
    })
    .on('unlink', path => {
        logger.debug(`File removed: ${path}`);
        triggerRefresh('file removal', path);
    })
    .on('error', error => {
        logger.error(`Watcher error: ${error}`);
    });

// Periodically check token expiration
logger.info(`Starting token expiration checker (interval: ${refreshInterval}ms)`);
setInterval(checkSsoTokens, refreshInterval);

// Handle shutdown gracefully
process.on('SIGINT', () => {
    logger.info('Shutting down credential monitor...');
    watcher.close().then(() => {
        logger.info('File watchers closed');
        process.exit(0);
    });
});

logger.info('AWS credential monitor started successfully');
