#!/usr/bin/env python
import os
import shutil
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('setup_obs')

def setup_obs_integration():
    # Check if we're in the correct directory
    if not os.path.exists('client/integrations'):
        logger.error("This script must be run from the project root directory")
        return False
    
    # Check if enhanced adapter exists
    if not os.path.exists('client/integrations/obs_adapter_enhanced.py'):
        logger.error("Enhanced OBS adapter not found. Make sure you've created it first.")
        return False
    
    # Backup the original file if it exists
    if os.path.exists('client/integrations/obs_adapter.py'):
        backup_path = 'client/integrations/obs_adapter.py.bak'
        shutil.copy2('client/integrations/obs_adapter.py', backup_path)
        logger.info(f"Backed up original OBS adapter to {backup_path}")
    
    # Copy the enhanced adapter to replace the original
    shutil.copy2('client/integrations/obs_adapter_enhanced.py', 'client/integrations/obs_adapter.py')
    logger.info("Successfully updated OBS adapter with enhanced version")
    
    # Check if test directory exists, create if not
    if not os.path.exists('tests'):
        os.makedirs('tests')
        logger.info("Created tests directory")
    
    # Check if workflows directory exists, create if not
    if not os.path.exists('workflows'):
        os.makedirs('workflows')
        logger.info("Created workflows directory")
    
    # Check if .env file exists, create from template if not
    if not os.path.exists('.env') and os.path.exists('.env.template'):
        shutil.copy2('.env.template', '.env')
        logger.info("Created .env file from template. Please update it with your credentials.")
    
    logger.info("\nSetup complete!")
    logger.info("\nNext steps:")
    logger.info("1. Make sure OBS Studio is running with WebSocket server enabled")
    logger.info("2. Update your .env file with the correct OBS WebSocket password")
    logger.info("3. Run the test connection script: python tests/test_obs_connection.py")
    logger.info("4. Try running one of the workflows using the Dashboard Assistant")
    
    return True

if __name__ == "__main__":
    if setup_obs_integration():
        sys.exit(0)
    else:
        sys.exit(1)
