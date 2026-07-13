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

## Duo Admin Setup — Redirect URIs

DCR clients register their own redirect URIs, but you need to ensure the Duo SSO application allows these callback URLs. Add the following to your Duo SSO OAuth Server app's allowed redirect URIs:

**Web app (port 8080):**
```
http://localhost:8080/callback/calendar
http://localhost:8080/callback/documents
http://localhost:8080/callback/analytics
```

**MCP server via Claude Code (port 3000):**
```
http://localhost:3000/callback
```

These are the defaults. If you change the port (`PORT` env var) or use a custom redirect_uri in the MCP tools, update accordingly.

## Claude Code integration

Each MCP server can also run as a stdio MCP server for direct Claude Code integration:

```bash
claude mcp add dcr-calendar -e DUO_SSO_ISSUER="https://sso-xxx.sso.duosecurity.com/oauth2/DIXXXXXXXXXX" -- /path/to/.venv/bin/python3 /path/to/mcp_server.py --server calendar
claude mcp add dcr-documents -e DUO_SSO_ISSUER="https://sso-xxx.sso.duosecurity.com/oauth2/DIXXXXXXXXXX" -- /path/to/.venv/bin/python3 /path/to/mcp_server.py --server documents
claude mcp add dcr-analytics -e DUO_SSO_ISSUER="https://sso-xxx.sso.duosecurity.com/oauth2/DIXXXXXXXXXX" -- /path/to/.venv/bin/python3 /path/to/mcp_server.py --server analytics
```

The MCP server registers with a distinct `client_name` (appends `(MCP)`) and uses port 3000 for callbacks, so it won't collide with the web app's registrations.

### MCP server tools

| Tool | Description |
|------|-------------|
| `discover_duo_endpoints` | Fetch OIDC discovery document |
| `register_client` | Perform DCR registration |
| `get_registration` | Show current registration details |
| `generate_auth_url` | Generate authorize URL with PKCE |
| `reset_registration` | Clear registration state (start fresh) |
| `server_info` | Show server identity and status |

## The 3 MCP servers

| Server | Description | Web client_name | MCP client_name |
|--------|-------------|-----------------|-----------------|
| Calendar | Manages calendar events and scheduling | `Calendar MCP Server` | `Calendar MCP Server (MCP)` |
| Documents | File storage and document management | `Documents MCP Server` | `Documents MCP Server (MCP)` |
| Analytics | Usage metrics and reporting dashboard | `Analytics MCP Server` | `Analytics MCP Server (MCP)` |

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

## How Duo matches agents via DCR

The `client_name` in the DCR registration payload is what Duo uses to identify and bind the agent. In the Duo Admin Panel, admins configure **DCR matching rules** — either EXACT or PARTIAL string matches against the `client_name`. When an MCP server registers with a `client_name` like `"Calendar MCP Server"`, Duo matches it against these rules to determine which Agent Class it belongs to, which controls the permissions and policies applied to that agent.

This means the `client_name` you send in the DCR request is effectively the **agent's identity string** — it's how Duo knows what this thing is and what it's allowed to do.

## Session management

- **Web app:** "Clear All Sessions" in the nav bar resets everything. Per-server "Clear" buttons let you re-register individual servers.
- **MCP server:** Use the `reset_registration` tool to clear state and register fresh.

## Token Exchange (RFC 8693) — optional

The demo includes an optional token exchange flow where the Documents MCP server can exchange its access token for a `read:calendar` scoped token from the Calendar MCP server. This requires a **confidential client** (with `client_secret`) — DCR creates public clients only, so token exchange will return a 401 unless you use a static client configured in the Duo Admin Panel.

## Files

- `app.py` — Web dashboard (Flask). Configure, register, and authenticate.
- `mcp_server.py` — Stdio MCP server for Claude Code integration.
- `setup.sh` — One-liner setup script.
- `requirements.txt` — Python dependencies.

## Requirements

- Python 3.10+
- A Duo SSO instance with DCR enabled
