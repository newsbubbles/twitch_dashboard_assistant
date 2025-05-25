#!/bin/bash

# Set up the remote repository
git remote add origin git@github.com:newsbubbles/twitch_dashboard_assistant.git

# Verify the remote was added
git remote -v

# Push the code to the remote repository
git push -u origin master

echo "Remote setup complete and code pushed to GitHub."
