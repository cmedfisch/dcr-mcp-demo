"""
DCR Demo - Chatbot Portal

A web app ("fake chatbot") that connects to 3 MCP servers over HTTP.
Each MCP server requires OAuth authentication via Duo SSO before tools are visible.

Architecture:
  - This app (port 8080): chatbot portal / dashboard
  - MCP servers (ports 3001-3003): HTTP servers with OAuth auth gates
  - Duo SSO: the authorization server for all flows

Both this chatbot and Claude Code go through the same auth ceremony:
  1. Hit MCP server → 401 + WWW-Authenticate
  2. Discover Duo AS via /.well-known/oauth-protected-resource
  3. DCR register with Duo (client_name = agent identity)
  4. Browser redirect → user authenticates
  5. Bearer token → MCP tools unlocked

Run:
    python3 servers.py --all   # start 3 MCP servers
    python3 app.py             # start chatbot portal
"""

import os
import json
import secrets
import hashlib
import base64
from pathlib import Path
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, render_template_string, url_for

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

PORT = int(os.environ.get("PORT", "8080"))
BASE_URL = f"http://localhost:{PORT}"
CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")

# --- MCP Server config ---
SERVERS = {
    "calendar": {
        "name": "Calendar MCP Server",
        "description": "Manages calendar events and scheduling",
        "scopes": ["openid", "email", "profile"],
        "icon": "\U0001f4c5",
        "mcp_port": 3001,
        "issuer": "",
    },
    "documents": {
        "name": "Documents MCP Server",
        "description": "File storage and document management",
        "scopes": ["openid", "email", "profile"],
        "icon": "\U0001f4c4",
        "mcp_port": 3002,
        "issuer": "",
    },
    "analytics": {
        "name": "Analytics MCP Server",
        "description": "Usage metrics and reporting dashboard",
        "scopes": ["openid", "email", "profile"],
        "icon": "\U0001f4ca",
        "mcp_port": 3003,
        "issuer": "",
    },
}

# Load issuers from config.json on startup
_cfg = load_config()
for sid in SERVERS:
    if sid in _cfg and _cfg[sid].get("issuer"):
        SERVERS[sid]["issuer"] = _cfg[sid]["issuer"]


def derive_endpoints(issuer: str) -> dict:
    """Derive Duo's 3 OAuth URLs from an issuer like https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXX"""
    issuer = issuer.rstrip("/")
    from urllib.parse import urlparse
    parsed = urlparse(issuer)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    return {
        "oauth_metadata_url": f"{base}/.well-known/oauth-authorization-server{path}",
        "oidc_discovery_url": f"{issuer}/.well-known/openid-configuration",
        "registration_endpoint": f"{issuer}/register",
    }


registrations = {}


def fetch_metadata(url: str) -> dict:
    if not url:
        return {"error": "URL not configured"}
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def do_dcr(server_id: str) -> dict:
    """Perform Dynamic Client Registration (RFC 7591) with Duo."""
    server = SERVERS[server_id]
    redirect_uri = f"{BASE_URL}/callback/{server_id}"

    if not server["issuer"]:
        return {"error": "Issuer not configured. Go to /config first."}

    endpoints = derive_endpoints(server["issuer"])
    reg_endpoint = endpoints["registration_endpoint"]

    payload = {
        "client_name": server["name"],
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "web",
    }

    try:
        resp = requests.post(reg_endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        result = {"status_code": resp.status_code, "endpoint_used": reg_endpoint, "request_payload": payload}
        try:
            result["response"] = resp.json()
        except ValueError:
            result["response_text"] = resp.text
        return result
    except Exception as e:
        return {"error": str(e), "endpoint_attempted": reg_endpoint, "request_payload": payload}


def generate_pkce():
    verifier = secrets.token_urlsafe(43)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def decode_jwt_unverified(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {"error": "Not a valid JWT"}
    def pad_b64(s):
        return s + "=" * (4 - len(s) % 4)
    try:
        header = json.loads(base64.urlsafe_b64decode(pad_b64(parts[0])))
        payload = json.loads(base64.urlsafe_b64decode(pad_b64(parts[1])))
        return {"header": header, "payload": payload}
    except Exception as e:
        return {"error": str(e), "raw": token[:100]}


# --- Routes ---

@app.route("/")
def dashboard():
    return render_template_string(TEMPLATE, servers=SERVERS, registrations=registrations, base_url=BASE_URL)


@app.route("/config")
def config_page():
    return render_template_string(CONFIG_TEMPLATE, servers=SERVERS)


@app.route("/config/<server_id>", methods=["POST"])
def save_server_config(server_id):
    if server_id not in SERVERS:
        return "Unknown server", 404
    issuer = request.form.get("issuer", "").strip()
    SERVERS[server_id]["issuer"] = issuer
    # Persist to config.json
    cfg = load_config()
    if server_id not in cfg:
        cfg[server_id] = {}
    cfg[server_id]["issuer"] = issuer
    save_config(cfg)
    return redirect("/config")


@app.route("/clear", methods=["POST"])
def clear_all():
    registrations.clear()
    return redirect("/")


@app.route("/clear/<server_id>", methods=["POST"])
def clear_server(server_id):
    registrations.pop(server_id, None)
    return redirect("/")


@app.route("/connect/<server_id>", methods=["POST"])
def connect(server_id):
    """Single-click: DCR register (if needed) then redirect to Duo for auth."""
    if server_id not in SERVERS:
        return "Unknown server", 404

    server = SERVERS[server_id]
    if not server["issuer"]:
        return "Not configured. Go to <a href='/config'>/config</a> first.", 400

    if server_id not in registrations or not registrations[server_id].get("response", {}).get("client_id"):
        result = do_dcr(server_id)
        registrations[server_id] = result
        if not result.get("response", {}).get("client_id"):
            return redirect("/")

    reg = registrations[server_id]
    client_id = reg["response"]["client_id"]

    endpoints = derive_endpoints(server["issuer"])
    metadata = fetch_metadata(endpoints["oauth_metadata_url"])
    auth_endpoint = metadata.get("authorization_endpoint", "")
    if not auth_endpoint:
        return "Could not find authorization_endpoint in metadata", 500

    verifier, challenge = generate_pkce()
    registrations[server_id]["pkce_verifier"] = verifier

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": f"{BASE_URL}/callback/{server_id}",
        "scope": " ".join(server["scopes"]),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(16),
    }
    return redirect(f"{auth_endpoint}?{urlencode(params)}")


@app.route("/callback/<server_id>")
def callback(server_id):
    code = request.args.get("code")
    error = request.args.get("error")
    token_response = None
    decoded_tokens = {}

    if code and server_id in SERVERS and server_id in registrations:
        server = SERVERS[server_id]
        reg = registrations[server_id]
        client_id = reg.get("response", {}).get("client_id", "")
        client_secret = reg.get("response", {}).get("client_secret", "")
        verifier = reg.get("pkce_verifier", "")

        endpoints = derive_endpoints(server["issuer"])
        metadata = fetch_metadata(endpoints["oauth_metadata_url"])
        token_endpoint = metadata.get("token_endpoint", "")

        if token_endpoint and verifier:
            token_data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{BASE_URL}/callback/{server_id}",
                "code_verifier": verifier,
                "client_id": client_id,
            }
            if client_secret:
                token_data["client_secret"] = client_secret

            try:
                resp = requests.post(token_endpoint, data=token_data, timeout=15)
                token_response = {"status_code": resp.status_code, "endpoint": token_endpoint}
                try:
                    token_response["body"] = resp.json()
                except ValueError:
                    token_response["body_raw"] = resp.text

                registrations[server_id]["token_response"] = token_response

                body = token_response.get("body", {})
                for key in ("access_token", "id_token"):
                    token = body.get(key, "")
                    if token and "." in token:
                        decoded_tokens[key] = decode_jwt_unverified(token)
            except Exception as e:
                token_response = {"error": str(e)}

    return render_template_string(CALLBACK_TEMPLATE,
        server_id=server_id,
        server=SERVERS.get(server_id, {}),
        code=code, error=error,
        params=dict(request.args),
        token_response=token_response,
        decoded_tokens=decoded_tokens)


@app.route("/token-exchange/<source_id>/<target_id>", methods=["POST"])
def token_exchange(source_id, target_id):
    """RFC 8693 Token Exchange (optional, requires confidential client)."""
    if source_id not in SERVERS or target_id not in SERVERS:
        return "Unknown server", 404

    source_server = SERVERS[source_id]
    target_server = SERVERS[target_id]
    source_reg = registrations.get(source_id, {})
    target_reg = registrations.get(target_id, {})

    source_token = source_reg.get("token_response", {}).get("body", {}).get("access_token")
    if not source_token:
        return render_template_string(EXCHANGE_TEMPLATE,
            src=source_server, target=target_server,
            src_id=source_id, target_id=target_id,
            error="No access token for source server. Connect to it first.")

    target_client_id = target_reg.get("response", {}).get("client_id", "")
    source_client_id = source_reg.get("response", {}).get("client_id", "")
    source_client_secret = source_reg.get("response", {}).get("client_secret", "")

    endpoints = derive_endpoints(source_server["issuer"])
    metadata = fetch_metadata(endpoints["oauth_metadata_url"])
    token_endpoint = metadata.get("token_endpoint", "")

    if not token_endpoint:
        return render_template_string(EXCHANGE_TEMPLATE,
            src=source_server, target=target_server,
            src_id=source_id, target_id=target_id,
            error="Could not find token_endpoint in metadata")

    exchange_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": source_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "read:calendar",
        "client_id": source_client_id,
    }
    if target_client_id:
        exchange_data["audience"] = target_client_id
    if source_client_secret:
        exchange_data["client_secret"] = source_client_secret

    exchange_result = {"endpoint": token_endpoint, "request": exchange_data.copy()}

    try:
        resp = requests.post(token_endpoint, data=exchange_data, timeout=15)
        exchange_result["status_code"] = resp.status_code
        try:
            exchange_result["response"] = resp.json()
        except ValueError:
            exchange_result["response_raw"] = resp.text
        exchanged_decoded = {}
        body = exchange_result.get("response", {})
        if body.get("access_token") and "." in body["access_token"]:
            exchanged_decoded["access_token"] = decode_jwt_unverified(body["access_token"])
    except Exception as e:
        exchange_result["error"] = str(e)
        exchanged_decoded = {}

    return render_template_string(EXCHANGE_TEMPLATE,
        src=source_server, target=target_server,
        src_id=source_id, target_id=target_id,
        exchange_result=exchange_result,
        exchanged_decoded=exchanged_decoded,
        error=None)


@app.route("/metadata/<server_id>")
def show_metadata(server_id):
    if server_id not in SERVERS:
        return "Unknown server", 404
    server = SERVERS[server_id]
    if not server["issuer"]:
        return "Issuer not configured", 400
    endpoints = derive_endpoints(server["issuer"])
    src = request.args.get("source", "oidc")
    url = endpoints["oidc_discovery_url"] if src == "oidc" else endpoints["oauth_metadata_url"]
    result = fetch_metadata(url)
    return render_template_string(JSON_TEMPLATE, title=f"{server['name']} - {src.upper()} Metadata", data=result)


# --- Templates ---

CONFIG_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Configure MCP Servers</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; }
        h1 { margin-bottom: 0.5rem; font-size: 1.5rem; }
        .subtitle { color: #8b949e; margin-bottom: 2rem; font-size: 0.9rem; }
        .grid { display: grid; grid-template-columns: 1fr; gap: 1.5rem; max-width: 800px; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; }
        .card h2 { font-size: 1.1rem; margin-bottom: 1rem; }
        label { display: block; color: #8b949e; font-size: 0.8rem; margin-bottom: 0.25rem; margin-top: 0.75rem; }
        input[type="text"] { width: 100%; padding: 0.5rem; border-radius: 4px; border: 1px solid #30363d; background: #0d1117; color: #e1e4e8; font-family: monospace; font-size: 0.8rem; }
        input[type="text"]:focus { outline: none; border-color: #58a6ff; }
        .btn { display: inline-block; padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 500; margin-top: 1rem; }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .nav { margin-bottom: 1.5rem; }
        .nav a { color: #58a6ff; font-size: 0.85rem; text-decoration: none; }
        .derived { margin-top: 0.75rem; padding: 0.5rem; background: #0d1117; border-radius: 4px; font-size: 0.75rem; }
        .derived-url { font-family: monospace; font-size: 0.7rem; color: #3fb950; }
        .note { margin-top: 0.5rem; font-size: 0.75rem; color: #8b949e; }
    </style>
</head>
<body>
    <h1>Configure MCP Servers</h1>
    <p class="subtitle">Set the Duo SSO issuer URL for each MCP server. This same issuer is used by both the chatbot and Claude Code.</p>
    <div class="nav"><a href="/">&larr; Back to Dashboard</a></div>
    <div class="grid">
    {% for id, server in servers.items() %}
        <div class="card">
            <h2>{{ server.icon }} {{ server.name }}</h2>
            <p class="note">MCP endpoint: <code>http://localhost:{{ server.mcp_port }}/mcp</code></p>
            <form method="POST" action="/config/{{ id }}">
                <label>Duo SSO Issuer URL</label>
                <input type="text" name="issuer" value="{{ server.issuer }}" placeholder="https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXXXXXXXXXXXXXXXX">
                <button class="btn btn-primary" type="submit">Save</button>
            </form>
            {% if server.issuer %}
                <div class="derived">
                    <div class="derived-url">OAuth Metadata: .well-known/oauth-authorization-server/...</div>
                    <div class="derived-url">OIDC Discovery: .well-known/openid-configuration</div>
                    <div class="derived-url">DCR Endpoint: /register</div>
                </div>
            {% endif %}
        </div>
    {% endfor %}
    </div>
</body>
</html>"""

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>DCR Demo - MCP + Duo SSO</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; }
        h1 { margin-bottom: 0.5rem; font-size: 1.5rem; }
        .subtitle { color: #8b949e; margin-bottom: 2rem; font-size: 0.9rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 1.5rem; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; }
        .card h2 { font-size: 1.1rem; margin-bottom: 0.5rem; }
        .card .desc { color: #8b949e; font-size: 0.85rem; margin-bottom: 0.75rem; }
        .card .mcp-url { font-family: monospace; font-size: 0.75rem; color: #3fb950; margin-bottom: 0.75rem; }
        .btn { display: inline-block; padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 500; text-decoration: none; }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .btn-secondary { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
        .btn-secondary:hover { background: #30363d; }
        .btn-disabled { background: #21262d; color: #484f58; border: 1px solid #30363d; cursor: not-allowed; }
        .status { margin-top: 0.75rem; padding: 0.75rem; border-radius: 6px; font-size: 0.75rem; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 180px; overflow-y: auto; }
        .status-success { background: #0d1117; border: 1px solid #238636; }
        .status-error { background: #0d1117; border: 1px solid #da3633; }
        .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center; }
        .nav { margin-bottom: 1rem; display: flex; gap: 1.5rem; align-items: center; }
        .nav a { color: #58a6ff; font-size: 0.85rem; text-decoration: none; }
        .agent-section { border: 1px solid #30363d; border-radius: 6px; overflow: hidden; margin: 0.75rem 0; }
        .agent-header { padding: 0.4rem 0.75rem; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .agent-header.chatbot { background: #1f6feb; color: white; }
        .agent-header.claude { background: #da7756; color: white; }
        .agent-body { padding: 0.75rem; background: #0d1117; }
        .agent-note { font-size: 0.75rem; color: #8b949e; margin-bottom: 0.5rem; }
        .agent-detail { font-size: 0.7rem; color: #c9d1d9; margin-bottom: 0.25rem; }
        .agent-detail code { background: #161b22; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.65rem; }
        .claude-cmd { background: #161b22; border: 1px solid #30363d; border-radius: 4px; padding: 0.5rem; font-size: 0.6rem; color: #7ee787; white-space: pre-wrap; word-break: break-all; margin: 0.25rem 0 0 0; }
        .dcr-payload { margin: 0.75rem 0; }
        .dcr-label { font-size: 0.75rem; color: #8b949e; margin-bottom: 0.25rem; }
        .dcr-json { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 0.75rem; font-size: 0.7rem; color: #7ee787; white-space: pre; overflow-x: auto; margin: 0; }
        .arch-note { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1rem; margin-bottom: 1.5rem; font-size: 0.8rem; line-height: 1.5; }
        .arch-note code { background: #0d1117; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.75rem; }
    </style>
</head>
<body>
    <h1>DCR Demo: MCP Servers + Duo SSO</h1>
    <p class="subtitle">Dynamic Client Registration (RFC 7591) &mdash; OAuth 2.1 with PKCE for AI agent authentication</p>
    <div class="nav">
        <a href="/config">Configure Issuers</a>
        {% for id, server in servers.items() %}
            {% if server.issuer %}
                <a href="/metadata/{{ id }}?source=oauth">{{ server.icon }} Metadata</a>
            {% endif %}
        {% endfor %}
        {% if registrations %}
            <form method="POST" action="/clear" style="display:inline; margin-left: auto;">
                <button style="background:none; border:none; color:#da3633; cursor:pointer; font-size:0.85rem;">Clear All Sessions</button>
            </form>
        {% endif %}
    </div>

    <div class="arch-note">
        <strong>Architecture:</strong> 3 MCP servers run on ports 3001-3003 with OAuth auth gates.
        Both this chatbot portal and Claude Code must authenticate via Duo SSO (DCR + PKCE) before accessing any tools.
        The <code>client_name</code> in the DCR payload is the agent's identity &mdash; Duo matches it against admin-configured rules.
    </div>

    <div class="arch-note" style="border-color: #da7756;">
        <strong style="color: #da7756;">Add all servers to Claude Code:</strong>
        <pre style="background:#0d1117; color:#7ee787; font-size:0.7rem; padding:0.75rem; border-radius:4px; margin:0.5rem 0 0 0; overflow-x:auto; white-space:pre-wrap; word-break:break-all;">claude mcp add dcr-calendar --transport http http://localhost:3001/mcp
claude mcp add dcr-documents --transport http http://localhost:3002/mcp
claude mcp add dcr-analytics --transport http http://localhost:3003/mcp</pre>
        <div style="font-size:0.7rem; color:#8b949e; margin-top:0.5rem;">
            Claude Code will automatically discover the auth requirements (401 &rarr; RFC 9728 &rarr; Duo DCR &rarr; browser auth &rarr; token).
            Make sure MCP servers are running: <code>python3 servers.py --all</code>
        </div>
    </div>

    <div class="grid">
    {% for id, server in servers.items() %}
        <div class="card">
            <h2>{{ server.icon }} {{ server.name }}</h2>
            <p class="desc">{{ server.description }}</p>
            <div class="mcp-url">http://localhost:{{ server.mcp_port }}/mcp</div>

            {% if server.issuer %}
            <!-- ChatBot Agent -->
            <div class="agent-section">
                <div class="agent-header chatbot">ChatBot Agent (this portal)</div>
                <div class="agent-body">
                    <div class="agent-note">Browser-based. This web app registers via DCR then bounces you to Duo for authentication.</div>
                    <div class="agent-detail"><strong>client_name:</strong> <code>{{ server.name }}</code></div>
                    <div class="agent-detail"><strong>Redirect URI:</strong> <code>{{ base_url }}/callback/{{ id }}</code></div>
                    <div class="actions" style="margin-top:0.5rem;">
                        <form method="POST" action="/connect/{{ id }}" style="display:inline">
                            {% if id in registrations and registrations[id].get('token_response', {}).get('body', {}).get('access_token') %}
                                <button class="btn btn-secondary" type="submit">Reconnect</button>
                            {% elif id in registrations and registrations[id].get('response', {}).get('client_id') %}
                                <button class="btn btn-secondary" type="submit">Authenticate</button>
                            {% else %}
                                <button class="btn btn-primary" type="submit">Connect</button>
                            {% endif %}
                        </form>
                        {% if id == 'documents' and id in registrations and registrations[id].get('token_response', {}).get('body', {}).get('access_token') %}
                            <form method="POST" action="/token-exchange/documents/calendar" style="display:inline">
                                <button class="btn" style="background:#a371f7; color:white;" type="submit">Token Exchange &rarr; Calendar</button>
                            </form>
                        {% endif %}
                    </div>
                </div>
            </div>

            <!-- DCR Payload -->
            <div class="dcr-payload">
                <div class="dcr-label">DCR Registration Payload (sent to Duo):</div>
                <pre class="dcr-json">{
  "client_name": "{{ server.name }}",
  "redirect_uris": ["{{ base_url }}/callback/{{ id }}"],
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none"
}</pre>
                <div style="font-size:0.7rem; color:#8b949e; margin-top:0.25rem;">
                    The <code>client_name</code> is the agent identity string. Duo admins configure DCR matching rules (EXACT/PARTIAL) against this value.
                </div>
            </div>

            <!-- Claude Code Agent -->
            <div class="agent-section">
                <div class="agent-header claude">Claude Code / Codex Agent</div>
                <div class="agent-body">
                    <div class="agent-note">
                        Connects directly to the MCP server URL. Gets 401 &rarr; discovers Duo via RFC 9728 &rarr; DCR &rarr; browser auth &rarr; tools unlocked.
                    </div>
                    <div class="agent-detail"><strong>MCP URL:</strong> <code>http://localhost:{{ server.mcp_port }}/mcp</code></div>
                    <div class="agent-detail"><strong>Auth flow:</strong> Automatic (handled by MCP client SDK)</div>
                    <div class="agent-detail" style="margin-top:0.5rem;"><strong>Add to Claude Code:</strong></div>
                    <pre class="claude-cmd">claude mcp add dcr-{{ id }} --transport http http://localhost:{{ server.mcp_port }}/mcp</pre>
                    <div style="font-size:0.65rem; color:#8b949e; margin-top:0.25rem;">
                        Duo redirect URI for this flow: <code>http://127.0.0.1/callback</code> or <code>http://localhost/callback</code>
                    </div>
                </div>
            </div>
            {% else %}
            <div class="actions">
                <span class="btn btn-disabled">Not configured &mdash; <a href="/config" style="color:#58a6ff; font-size:0.8rem;">set issuer</a></span>
            </div>
            {% endif %}

            {% if id in registrations %}
                {% set reg = registrations[id] %}
                <div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.75rem;">
                    <span style="font-size:0.7rem; color:#8b949e;">
                        {% if reg.get('token_response', {}).get('body', {}).get('access_token') %}
                            <span style="color:#3fb950;">Authenticated</span> &mdash; client_id: {{ reg.get('response', {}).get('client_id', '?')[:12] }}...
                        {% elif reg.get('response', {}).get('client_id') %}
                            Registered &mdash; client_id: {{ reg.get('response', {}).get('client_id', '?')[:12] }}...
                        {% else %}
                            Pending
                        {% endif %}
                    </span>
                    <form method="POST" action="/clear/{{ id }}" style="display:inline;">
                        <button style="background:none; border:none; color:#da3633; cursor:pointer; font-size:0.7rem;">Clear</button>
                    </form>
                </div>
                {% if reg.get('error') %}
                    <div class="status status-error">{{ reg.error }}</div>
                {% endif %}
            {% endif %}
        </div>
    {% endfor %}
    </div>
</body>
</html>"""

CALLBACK_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>OAuth Callback - {{ server.get('name', server_id) }}</title>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; max-width: 900px; }
        h1 { margin-bottom: 1rem; }
        h2 { font-size: 1rem; color: #8b949e; margin-top: 1.5rem; margin-bottom: 0.5rem; }
        pre { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; overflow-x: auto; font-size: 0.8rem; white-space: pre-wrap; word-break: break-all; }
        a { color: #58a6ff; }
        .success { color: #3fb950; font-size: 1.1rem; margin-bottom: 1rem; }
        .error { color: #da3633; font-size: 1.1rem; margin-bottom: 1rem; }
        .step { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; margin-bottom: 0.75rem; }
        .step-title { font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem; }
        .step-detail { font-family: monospace; font-size: 0.8rem; color: #8b949e; word-break: break-all; }
        .step-ok { border-left: 3px solid #3fb950; }
        .step-fail { border-left: 3px solid #da3633; }
        .token-label { font-size: 0.85rem; font-weight: 600; color: #58a6ff; margin-bottom: 0.25rem; }
    </style>
</head>
<body>
    <h1>{{ server.get('icon', '') }} {{ server.get('name', server_id) }}</h1>
    {% if code %}
        <p class="success">Authenticated via DCR + OAuth 2.1 (PKCE)</p>
        <div class="step step-ok">
            <div class="step-title">1. Dynamic Client Registration (RFC 7591)</div>
            <div class="step-detail">POST /register &rarr; got client_id</div>
        </div>
        <div class="step step-ok">
            <div class="step-title">2. Authorization Code + PKCE (S256)</div>
            <div class="step-detail">Redirected to Duo SSO &rarr; user authenticated</div>
        </div>
        <div class="step step-ok">
            <div class="step-title">3. Callback received</div>
            <div class="step-detail">code: {{ code[:20] }}...</div>
        </div>
        {% if token_response %}
            {% if token_response.get('body', {}).get('access_token') %}
                <div class="step step-ok">
                    <div class="step-title">4. Token Exchange (code + code_verifier)</div>
                    <div class="step-detail">POST {{ token_response.endpoint }} &rarr; {{ token_response.status_code }}</div>
                </div>
                <div class="step step-ok">
                    <div class="step-title">5. Bearer token ready for MCP server</div>
                    <div class="step-detail">Can now call tools on http://localhost:{{ server.get('mcp_port', '?') }}/mcp with this token</div>
                </div>
            {% else %}
                <div class="step step-fail">
                    <div class="step-title">4. Token Exchange</div>
                    <div class="step-detail">{{ token_response | tojson }}</div>
                </div>
            {% endif %}
        {% endif %}

        {% if decoded_tokens %}
            <div style="margin-top: 1.5rem;">
            {% for token_name, decoded in decoded_tokens.items() %}
                <h2>{{ token_name }} (decoded)</h2>
                {% if decoded.get('header') %}
                    <div class="token-label">Header</div>
                    <pre>{{ decoded.header | tojson(indent=2) }}</pre>
                    <div class="token-label">Payload</div>
                    <pre>{{ decoded.payload | tojson(indent=2) }}</pre>
                {% else %}
                    <pre>{{ decoded | tojson(indent=2) }}</pre>
                {% endif %}
            {% endfor %}
            </div>
        {% endif %}

        {% if token_response and token_response.get('body') %}
            <h2>Raw token response</h2>
            <pre>{{ token_response.body | tojson(indent=2) }}</pre>
        {% endif %}

    {% elif error %}
        <p class="error">Connection failed: {{ error }}</p>
        <pre>{{ params | tojson(indent=2) }}</pre>
    {% endif %}
    <p style="margin-top: 1.5rem;"><a href="/">&larr; Back to Dashboard</a></p>
</body>
</html>"""

JSON_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
    <style>
        body { font-family: monospace; background: #0f1117; color: #e1e4e8; padding: 2rem; }
        pre { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; white-space: pre-wrap; }
        a { color: #58a6ff; }
    </style>
</head>
<body>
    <h2>{{ title }}</h2>
    <pre>{{ data | tojson(indent=2) }}</pre>
    <p style="margin-top: 1rem;"><a href="/">&larr; Back</a></p>
</body>
</html>"""


EXCHANGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Token Exchange - {{ src.name }} &rarr; {{ target.name }}</title>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; max-width: 900px; }
        h1 { margin-bottom: 0.5rem; }
        .subtitle { color: #a371f7; font-size: 0.9rem; margin-bottom: 1.5rem; }
        h2 { font-size: 1rem; color: #8b949e; margin-top: 1.5rem; margin-bottom: 0.5rem; }
        pre { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; overflow-x: auto; font-size: 0.8rem; white-space: pre-wrap; word-break: break-all; }
        a { color: #58a6ff; }
        .error { color: #da3633; font-size: 1rem; margin-bottom: 1rem; }
        .step { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; margin-bottom: 0.75rem; }
        .step-title { font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem; }
        .step-detail { font-family: monospace; font-size: 0.8rem; color: #8b949e; word-break: break-all; }
        .step-ok { border-left: 3px solid #a371f7; }
        .step-fail { border-left: 3px solid #da3633; }
        .token-label { font-size: 0.85rem; font-weight: 600; color: #a371f7; margin-bottom: 0.25rem; }
        .flow { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem; padding: 1rem; background: #161b22; border-radius: 6px; flex-wrap: wrap; }
        .flow-item { padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.85rem; font-weight: 500; }
        .flow-source { background: #238636; color: white; }
        .flow-arrow { color: #8b949e; font-size: 1.2rem; }
        .flow-target { background: #1f6feb; color: white; }
        .flow-scope { background: #a371f7; color: white; font-family: monospace; font-size: 0.8rem; }
    </style>
</head>
<body>
    <h1>RFC 8693 Token Exchange</h1>
    <p class="subtitle">{{ src.icon }} {{ src.name }} &rarr; {{ target.icon }} {{ target.name }}</p>

    <div class="flow">
        <span class="flow-item flow-source">{{ src.icon }} {{ src.name }}</span>
        <span class="flow-arrow">&rarr;</span>
        <span class="flow-item flow-scope">read:calendar</span>
        <span class="flow-arrow">&rarr;</span>
        <span class="flow-item flow-target">{{ target.icon }} {{ target.name }}</span>
    </div>

    {% if error %}
        <p class="error">{{ error }}</p>
    {% elif exchange_result %}
        <div class="step step-ok">
            <div class="step-title">Token Exchange Request</div>
            <div class="step-detail">POST {{ exchange_result.endpoint }}</div>
        </div>

        <h2>Request payload</h2>
        <pre>{{ exchange_result.request | tojson(indent=2) }}</pre>

        {% if exchange_result.get('status_code') %}
            {% if exchange_result.get('response', {}).get('access_token') %}
                <div class="step step-ok">
                    <div class="step-title">Exchange successful ({{ exchange_result.status_code }})</div>
                    <div class="step-detail">Got new access_token scoped to {{ target.name }}</div>
                </div>
            {% else %}
                <div class="step step-fail">
                    <div class="step-title">Exchange returned {{ exchange_result.status_code }}</div>
                    <div class="step-detail">{{ exchange_result.get('response', exchange_result.get('response_raw', '')) | tojson }}</div>
                </div>
            {% endif %}

            {% if exchange_result.get('response') %}
                <h2>Response</h2>
                <pre>{{ exchange_result.response | tojson(indent=2) }}</pre>
            {% endif %}
        {% endif %}

        {% if exchanged_decoded and exchanged_decoded.get('access_token') %}
            <h2>Exchanged access_token (decoded)</h2>
            <div class="token-label">Header</div>
            <pre>{{ exchanged_decoded.access_token.header | tojson(indent=2) }}</pre>
            <div class="token-label">Payload</div>
            <pre>{{ exchanged_decoded.access_token.payload | tojson(indent=2) }}</pre>
        {% endif %}
    {% endif %}

    <p style="margin-top: 1.5rem;"><a href="/">&larr; Back to Dashboard</a></p>
</body>
</html>"""


if __name__ == "__main__":
    print(f"\n  Chatbot Portal running at {BASE_URL}")
    print(f"  Configure issuers at {BASE_URL}/config")
    print(f"\n  Make sure MCP servers are running: python3 servers.py --all\n")
    app.run(host="0.0.0.0", port=PORT, debug=True)
