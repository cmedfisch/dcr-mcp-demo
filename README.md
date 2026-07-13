# DCR Demo: MCP Servers + Duo SSO

A lightweight demo showing **OAuth 2.0 Dynamic Client Registration (RFC 7591)** with Duo SSO. Three fake MCP servers each register themselves as public OAuth clients, then authenticate users via Authorization Code + PKCE.

## What it does

1. You configure an **issuer URL** per MCP server (e.g., `https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXXXXXXXX`)
2. The app derives the 3 endpoints automatically:
   - `.well-known/oauth-authorization-server/...` (OAuth metadata)
   - `.well-known/openid-configuration` (OIDC discovery)
   - `/register` (DCR endpoint)
3. Click **Connect** — the app registers via DCR, then bounces you to Duo for auth
4. After authentication, it exchanges the code for tokens and **decodes the JWT** (access_token + id_token)

## Quick start

```bash
# Clone
git clone https://github.com/cmedfisch/dcr-mcp-demo.git
cd dcr-mcp-demo

# Setup (creates venv, installs deps)
./setup.sh

# Run
.venv/bin/python3 app.py
```

Open http://localhost:8080 → go to `/config` → paste your issuer URL → hit Connect.

## Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask requests httpx "mcp[cli]"
python3 app.py
```

## Claude Code integration

Each MCP server can also run as a stdio MCP server for direct Claude Code integration:

```bash
claude mcp add dcr-calendar -- /path/to/.venv/bin/python3 /path/to/mcp_server.py --server calendar
claude mcp add dcr-documents -- /path/to/.venv/bin/python3 /path/to/mcp_server.py --server documents
claude mcp add dcr-analytics -- /path/to/.venv/bin/python3 /path/to/mcp_server.py --server analytics
```

Set the issuer via env var:

```bash
claude mcp add dcr-calendar -e DUO_SSO_ISSUER="https://sso-xxx.sso.duosecurity.com/oauth2/DIXXXXXXXXXX" -- ...
```

## The 3 MCP servers

| Server | Description |
|--------|-------------|
| Calendar | Manages calendar events and scheduling |
| Documents | File storage and document management |
| Analytics | Usage metrics and reporting dashboard |

## How DCR works in this demo

```
MCP Server                          Duo SSO
    |                                  |
    |--- POST /register -------------->|  (client_name, redirect_uris)
    |<-- 201 {client_id} --------------|
    |                                  |
    |--- GET /authorize?client_id&pkce>|  (redirect user to Duo)
    |       [user authenticates]       |
    |<-- redirect callback?code -------|
    |                                  |
    |--- POST /token (code+verifier)-->|
    |<-- {access_token, id_token} -----|
```

## Files

- `app.py` — Web dashboard (Flask). Configure, register, and authenticate.
- `mcp_server.py` — Stdio MCP server for Claude Code integration.
- `setup.sh` — One-liner setup script.
- `requirements.txt` — Python dependencies.

## Requirements

- Python 3.10+
- A Duo SSO instance with DCR enabled
