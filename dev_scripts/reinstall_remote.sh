#!/bin/bash
# Minimal script to reinstall argo-proxy from your fork on the remote machine (homes-01)

set -e  # Exit on error

# Define variables
FORK_URL="https://github.com/n-getty/argo-proxy.git"
INSTALL_DIR="$HOME/argo-proxy-opencode"

echo ">>> Cleaning up previous install directory..."
rm -rf "$INSTALL_DIR"

echo ">>> Cloning updated fork..."
git clone "$FORK_URL" "$INSTALL_DIR"

echo ">>> Installing argo-proxy..."
cd "$INSTALL_DIR"
# Install in user mode to update ~/.local/lib/...
pip install --upgrade --user .

echo ">>> Installation complete!"
echo "Please restart argo-proxy now to load the changes:"
echo "   1. Hit Ctrl+C to stop the current process"
echo "   2. Run 'argo-proxy' to start it"
