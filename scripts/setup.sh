#!/usr/bin/env bash
# Quick setup script for git-auto-push
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================================="
echo "    🚀 Setting up Git Auto Push (GitHub Heatmap Engine)  "
echo "=========================================================="

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is required but not installed. Please install python3."
    exit 1
fi

# Check Git
if ! command -v git &> /dev/null; then
    echo "❌ Git is required but not installed."
    exit 1
fi

echo "✅ Python3 and Git found."

# Test GitHub SSH connection
echo "Checking GitHub SSH connection..."
ssh -T -o StrictHostKeyChecking=accept-new git@github.com 2>&1 | grep -i "successfully authenticated" && echo "✅ GitHub SSH Authentication successful!" || {
    echo "⚠️ Warning: GitHub SSH authentication check returned unexpected message. Make sure your SSH keys are added to GitHub."
}

# Ensure auto_push.py is executable
chmod +x auto_push.py

# Check remote
CURRENT_REMOTE=$(git remote get-url origin 2>/dev/null || true)
if [ -z "$CURRENT_REMOTE" ]; then
    echo ""
    echo "Configuring default remote: git@github.com:Chiranjibee18/git-auto-push.git"
    python3 auto_push.py set-remote "git@github.com:Chiranjibee18/git-auto-push.git"
else
    echo "Current remote: $CURRENT_REMOTE"
fi

# Install systemd user service
echo ""
echo "Installing systemd user service..."
python3 auto_push.py install-service

echo ""
echo "=========================================================="
echo "    🎉 Setup Complete! Your Heatmap Engine is Running!   "
echo "=========================================================="
python3 auto_push.py status
