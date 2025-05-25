#!/bin/bash

# Update Git repository with Twitch Integration changes

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Initialize git repository if not already initialized
if [ ! -d .git ]; then
  echo "Initializing git repository..."
  git init
  echo "Git repository initialized."
fi

# Add all files
git add .

# Commit the changes
git commit -m "Complete Twitch API integration with channel management, chat, and stream features"

# Display status
echo "\nGit repository updated. Current status:\n"
git status

echo "\nCommit history:\n"
git log --oneline -n 5

echo "\nTo push changes to a remote repository, run:\n"
echo "git remote add origin <your-repository-url>"
echo "git push -u origin main"
