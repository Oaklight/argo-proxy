#!/bin/bash

# Configuration
REMOTE_HOST="homes.cels.anl.gov"
JUMP_HOST="logins.cels.anl.gov"
USER="ngetty"
PORT=50906

echo "Setting up SSH tunnel to $REMOTE_HOST via $JUMP_HOST..."
echo "Local port $PORT -> Remote port $PORT"

# Check if port is already in use
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
    echo "Port $PORT is already in use locally. Assuming tunnel is active."
else
    # Start the tunnel in the background
    # -f: go to background
    # -N: do not execute a remote command
    # -L: port forwarding
    # -J: jump host
    ssh -f -N -L $PORT:127.0.0.1:$PORT -J $USER@$JUMP_HOST $USER@$REMOTE_HOST
    
    if [ $? -eq 0 ]; then
        echo "Tunnel established successfully!"
    else
        echo "Failed to establish tunnel."
        exit 1
    fi
fi

echo ""
echo "IMPORTANT: You must ensure 'argo-proxy' is running on $REMOTE_HOST."
echo "1. SSH into $REMOTE_HOST: ssh -J $USER@$JUMP_HOST $USER@$REMOTE_HOST"
echo "2. Run: argo-proxy"
echo "   (Make sure ~/.local/bin is in your PATH)"
