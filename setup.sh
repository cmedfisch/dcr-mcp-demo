#!/bin/bash
# Quick setup for DCR demo
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Setting up DCR Demo..."
echo "======================"

# Create venv
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    python3 -m venv "$SCRIPT_DIR/.venv"
    echo "Created venv"
fi

# Install deps
"$SCRIPT_DIR/.venv/bin/pip" install --quiet flask requests httpx "mcp[cli]"
echo "Installed dependencies"

# Show what to do next
cat <<EOF

Done! Next steps:

1. Set your Duo SSO issuer:
   export DUO_SSO_ISSUER="https://sso-XXXX.sso.duosecurity.com/oidc/DIXXXXXXXXXXXXXXXXXX"

2. Run the web demo:
   $SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/app.py

3. Or connect all 3 to Claude Code:
   claude mcp add dcr-calendar -- $SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/mcp_server.py --server calendar
   claude mcp add dcr-documents -- $SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/mcp_server.py --server documents
   claude mcp add dcr-analytics -- $SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/mcp_server.py --server analytics

   Or add env vars:
   claude mcp add dcr-calendar -e DUO_SSO_ISSUER="your-issuer-url" -- $SCRIPT_DIR/.venv/bin/python3 $SCRIPT_DIR/mcp_server.py --server calendar

EOF
