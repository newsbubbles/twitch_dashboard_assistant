#!/bin/bash

echo "Running git remote -v to verify remote origin..."
git remote -v

echo -e "\nIf you don't see 'origin git@github.com:newsbubbles/twitch_dashboard_assistant.git' listed above, run:\ngit remote add origin git@github.com:newsbubbles/twitch_dashboard_assistant.git\n"

echo -e "To push to GitHub, run:\ngit push -u origin master\n"

echo -e "Project is located at:\n$(pwd)\n"
