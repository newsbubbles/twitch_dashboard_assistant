#!/bin/bash

# Remove any existing origin remote
git remote remove origin 2>/dev/null

# Add the GitHub repository as remote origin
git remote add origin git@github.com:newsbubbles/twitch_dashboard_assistant.git

# Verify remote was added
echo "Remote configuration:"
git remote -v

# Push to GitHub
echo "\nNow attempting to push to GitHub..."
git push -u origin master
