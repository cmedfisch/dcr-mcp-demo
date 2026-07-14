# DCR Demo: MCP Servers + Duo SSO

A demo showing **OAuth 2.0 Dynamic Client Registration (RFC 7591)** with Duo SSO for MCP server authentication. Three MCP servers run over HTTP with full OAuth auth gates — both a chatbot web portal and Claude Code must authenticate via Duo before accessing any tools.

## Architecture

```
┌──────────────────────────┐      ┌────────────────────────┐
│   Chatbot Portal (:8080) │      │   Claude Code / Codex  │
│   (this web app)         │      │   (MCP client)         │
└──────────┬───────────────┘      └──────────┬─────────────┘
           │                                  │
           │  HTTP + Bearer token             │  HTTP + Bearer token
           │                                  │
    ┌──────┴──────┬──────────────┬────────────┴───────┐
    │             │              │                     │
    ▼             ▼              ▼                     │
┌────────┐  ┌──────────┐  ┌───────────┐              │
│Calendar│  │ Documents│  │ Analytics │              │
│  :3001 │  │   :3002  │  │   :3003   │              │
└───┬────┘  └────┬─────┘  └─────┬─────┘              │
    │             │              │                     │
    └─────────────┴──────────────┴─────────────────────┘
                         │
                    401 → RFC 9728
                    → Discover Duo AS
                    → DCR → PKCE → Token
                         │
                    ┌────▼────┐
                    │ Duo SSO │
                    │ (AS)    │
                    └─────────┘
```

## Quick start

```bash
git clone https://github.com/cmedfisch/dcr-mcp-demo.git
cd dcr-mcp-demo

# Setup
./setup.sh

# Configure issuers in config.json
# (or use the web UI at /config)

# Start MCP servers (all 3)
.venv/bin/python3 servers.py --all

# Start chatbot portal
.venv/bin/python3 app.py
```

## Configuration

Edit `config.json` to set the Duo SSO issuer for each server:

```json
{
  "calendar": {
    "issuer": "https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXXXXXXXX"
  },
  "documents": {
    "issuer": "https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXXXXXXXX"
  },
  "analytics": {
    "issuer": "https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXXXXXXXX"
  }
}
```

You can also configure issuers via the web UI at http://localhost:8080/config.

## Add to Claude Code

Once the MCP servers are running (`python3 servers.py --all`):

```bash
claude mcp add dcr-calendar --transport http http://localhost:3001/mcp
claude mcp add dcr-documents --transport http http://localhost:3002/mcp
claude mcp add dcr-analytics --transport http http://localhost:3003/mcp
```

Claude Code will automatically:
1. Hit the MCP server → get 401
2. Discover the authorization server via `/.well-known/oauth-protected-resource` (RFC 9728)
3. Register via DCR with Duo
4. Open a browser for user authentication
5. Exchange the code for a Bearer token
6. Retry with the token → tools are now visible

## Duo Admin Setup

This demo requires **3 SSO integrations** (one per MCP server) and **3 custom agents** registered in the Agent Directory. See the [Duo MCP OAuth guide](https://duo.com/docs/sso-oauth-server-mcp) for full setup instructions.

### Integrations (Duo Admin → Single Sign-On)

Create one SSO integration for each server. Each produces its own issuer URL (the IKEY at the end differs):

| Integration | Protects | Issuer pattern |
|-------------|----------|----------------|
| Calendar MCP Server | `:3001` | `https://sso-xxx.../oauth2/DI_CALENDAR_IKEY` |
| Documents MCP Server | `:3002` | `https://sso-xxx.../oauth2/DI_DOCUMENTS_IKEY` |
| Analytics MCP Server | `:3003` | `https://sso-xxx.../oauth2/DI_ANALYTICS_IKEY` |

### Agent Directory (Duo Admin → Agents)

Register 3 agents — one per server. The `client_name` sent during DCR must match the agent's DCR matching rule (EXACT or PARTIAL):

| Agent Name | DCR Match | Binds To |
|------------|-----------|----------|
| Calendar MCP Server | EXACT | Calendar integration |
| Documents MCP Server | EXACT | Documents integration |
| Analytics MCP Server | EXACT | Analytics integration |

### Redirect URIs

Add these to each integration's allowed redirect URIs:

**Chatbot portal (port 8080):**
```
http://localhost:8080/callback/calendar
http://localhost:8080/callback/documents
http://localhost:8080/callback/analytics
```

**Claude Code (MCP client SDK):**
```
http://localhost/callback
http://127.0.0.1/callback
```

## How DCR works

The `client_name` in the DCR registration payload is the agent's identity string. Duo admins configure **DCR matching rules** (EXACT or PARTIAL) that bind agents to Agent Classes based on this value.

```
Agent                               Duo SSO
  |                                    |
  |--- POST /register --------------->|  { "client_name": "Calendar MCP Server", ... }
  |<-- 201 { client_id } -------------|
  |                                    |
  |--- GET /authorize?client_id&pkce->|  (user authenticates in browser)
  |<-- redirect ?code ----------------|
  |                                    |
  |--- POST /token (code+verifier) -->|
  |<-- { access_token, id_token } ----|
  |                                    |
  |=== Bearer token → MCP tools ===   |
```

## The 3 MCP Servers

| Server | Port | Tools |
|--------|------|-------|
| Calendar | 3001 | list_events, get_event, create_event, check_availability |
| Documents | 3002 | list_documents, get_document, search_documents, upload_document, list_folders |
| Analytics | 3003 | get_metrics, get_audit_log, get_dashboard_summary, query_usage |

## Files

- `servers.py` — 3 HTTP MCP servers with OAuth auth gates
- `app.py` — Chatbot portal (Flask web app)
- `config.json` — Issuer configuration per server
- `setup.sh` — One-liner setup script
- `requirements.txt` — Python dependencies
- `mcp_server.py` — Legacy stdio MCP server (kept for reference)

## Stopping the servers

Use `Ctrl+C` in each terminal to stop cleanly. If ports are stuck:

```bash
# Find and kill processes on the demo ports
lsof -ti:3001,3002,3003,8080 | xargs kill -9
```

Or kill just the MCP servers:
```bash
lsof -ti:3001,3002,3003 | xargs kill -9
```

## Requirements

- Python 3.10+
- A Duo SSO instance with DCR enabled
