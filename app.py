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
        "resource_uri": "http://localhost:3001/",
        "redirect_uri": "http://localhost:8080/callback/calendar",
        "icon": "\U0001f4c5",
        "mcp_port": 3001,
        "issuer": "",
    },
    "documents": {
        "name": "Documents MCP Server",
        "description": "File storage and document management",
        "scopes": ["openid", "email", "profile"],
        "resource_uri": "http://localhost:3002/",
        "redirect_uri": "http://localhost:8080/callback/documents",
        "icon": "\U0001f4c4",
        "mcp_port": 3002,
        "issuer": "",
    },
    "analytics": {
        "name": "Analytics MCP Server",
        "description": "Usage metrics and reporting dashboard",
        "scopes": ["openid", "email", "profile"],
        "resource_uri": "http://localhost:3003/",
        "redirect_uri": "http://localhost:8080/callback/analytics",
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
    <title>Settings - MCP Agent Portal</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'CiscoSans', -apple-system, system-ui, sans-serif; background: #f5f6f7; color: #1b2733; min-height: 100vh; }
        .layout { display: flex; min-height: 100vh; }
        .sidebar { width: 240px; background: #1b2733; padding: 0; flex-shrink: 0; display: flex; flex-direction: column; }
        .sidebar-brand { padding: 1.25rem 1.5rem; border-bottom: 1px solid #2a3a4a; }
        .sidebar-brand h2 { font-size: 0.9rem; color: #fff; font-weight: 600; letter-spacing: -0.2px; }
        .sidebar-brand span { font-size: 0.7rem; color: #7b8fa3; }
        .sidebar-nav { padding: 0.75rem 0.75rem; flex: 1; }
        .sidebar-nav a { display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.75rem; border-radius: 6px; color: #b0bec5; text-decoration: none; font-size: 0.82rem; margin-bottom: 0.2rem; transition: all 0.15s; }
        .sidebar-nav a:hover { background: #2a3a4a; color: #fff; }
        .sidebar-nav a.active { background: #049fd9; color: #fff; }
        .sidebar-nav a svg { width: 16px; height: 16px; fill: currentColor; }
        .main { flex: 1; padding: 2rem 2.5rem; overflow-y: auto; }
        h1 { font-size: 1.5rem; font-weight: 600; color: #1b2733; margin-bottom: 0.25rem; }
        .subtitle { color: #5a6872; margin-bottom: 2rem; font-size: 0.85rem; }
        .section-title { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 1.2px; color: #5a6872; margin-bottom: 0.75rem; font-weight: 600; }
        .setting-card { background: #fff; border: 1px solid #e0e5e9; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
        .setting-card h3 { font-size: 0.95rem; margin-bottom: 0.4rem; color: #1b2733; font-weight: 600; }
        .setting-card .meta { font-size: 0.75rem; color: #5a6872; margin-bottom: 1rem; }
        .setting-card .meta code { background: #f0f4f8; padding: 0.15rem 0.5rem; border-radius: 3px; color: #049fd9; font-size: 0.7rem; border: 1px solid #e0e5e9; }
        label { display: block; font-size: 0.78rem; color: #5a6872; margin-bottom: 0.3rem; font-weight: 500; }
        input[type="text"] { width: 100%; padding: 0.6rem 0.75rem; border-radius: 4px; border: 1px solid #d2d8de; background: #fff; color: #1b2733; font-family: 'SF Mono', 'Menlo', monospace; font-size: 0.78rem; transition: border 0.15s; }
        input[type="text"]:focus { outline: none; border-color: #049fd9; box-shadow: 0 0 0 2px #049fd922; }
        .btn { padding: 0.5rem 1.25rem; border-radius: 4px; border: none; cursor: pointer; font-size: 0.8rem; font-weight: 600; transition: all 0.15s; }
        .btn-save { background: #049fd9; color: #fff; margin-top: 0.75rem; }
        .btn-save:hover { background: #037fb3; }
        .info-block { background: #f7f9fb; border: 1px solid #e0e5e9; border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.75rem; }
        .info-block .info-label { font-size: 0.65rem; color: #049fd9; font-weight: 700; margin-bottom: 0.4rem; text-transform: uppercase; letter-spacing: 0.5px; }
        .info-block .info-row { font-family: 'SF Mono', monospace; font-size: 0.7rem; color: #5a6872; margin-bottom: 0.2rem; word-break: break-all; }
        .redirect-block { background: #fff8f0; border: 1px solid #f5a623; border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.75rem; }
        .redirect-block h4 { font-size: 0.72rem; color: #c77a00; margin-bottom: 0.5rem; font-weight: 600; }
        .redirect-block code { display: block; font-size: 0.7rem; color: #1b2733; margin-bottom: 0.2rem; font-family: 'SF Mono', monospace; }
        .redirect-block .note { font-size: 0.65rem; color: #8a6d3b; margin-top: 0.15rem; margin-bottom: 0.3rem; }
    </style>
</head>
<body>
<div class="layout">
    <div class="sidebar">
        <div class="sidebar-brand">
            <h2>MCP Agent Portal</h2>
            <span>Duo SSO + DCR Demo</span>
        </div>
        <div class="sidebar-nav">
            <a href="/">
                <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
                Chat
            </a>
            <a href="/config" class="active">
                <svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
                Settings
            </a>
        </div>
    </div>
    <div class="main">
        <h1>Settings</h1>
        <p class="subtitle">Configure Duo SSO issuers for each MCP server. Changes are saved to config.json.</p>

        <div class="section-title">MCP Server Connections</div>
        {% for id, server in servers.items() %}
        <div class="setting-card">
            <h3>{{ server.icon }} {{ server.name }}</h3>
            <div class="meta">
                MCP Endpoint: <code>http://localhost:{{ server.mcp_port }}/mcp</code>
                &nbsp;&bull;&nbsp;
                Resource URI: <code>{{ server.resource_uri }}</code>
                &nbsp;&bull;&nbsp;
                Scopes: <code>{{ server.scopes | join(' ') }}</code>
            </div>
            <form method="POST" action="/config/{{ id }}">
                <label>Duo SSO Issuer URL</label>
                <input type="text" name="issuer" value="{{ server.issuer }}" placeholder="https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXXXXXXXXXXXXXXXX">
                <button class="btn btn-save" type="submit">Save</button>
            </form>
            {% if server.issuer %}
            <div class="info-block">
                <div class="info-label">Endpoints &amp; URIs</div>
                <div class="info-row">Resource URI: {{ server.resource_uri }}</div>
                <div class="info-row">Discovery: http://localhost:{{ server.mcp_port }}/.well-known/oauth-protected-resource</div>
                <div class="info-row">DCR: {{ server.issuer }}/register</div>
                <div class="info-row">Authorize: {{ server.issuer }}/authorize</div>
                <div class="info-row">Token: {{ server.issuer }}/token</div>
                <div class="info-row">Scopes: {{ server.scopes | join(' ') }}</div>
            </div>
            <div class="redirect-block">
                <h4>Required Redirect URIs for {{ server.name }} (Duo Admin Panel)</h4>
                <code>http://localhost:8080/callback/{{ id }}</code>
                <div class="note">Chatbot portal redirect for {{ server.name }} (port {{ server.mcp_port }})</div>
                <code>http://127.0.0.1/callback</code>
                <code>http://localhost/callback</code>
                <div class="note">Claude Code / MCP SDK redirect (shared across all servers)</div>
            </div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</div>
</body>
</html>"""

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>MCP Agent Portal</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'CiscoSans', -apple-system, system-ui, sans-serif; background: #f5f6f7; color: #1b2733; min-height: 100vh; }
        .layout { display: flex; min-height: 100vh; }
        .sidebar { width: 240px; background: #1b2733; padding: 0; flex-shrink: 0; display: flex; flex-direction: column; }
        .sidebar-brand { padding: 1.25rem 1.5rem; border-bottom: 1px solid #2a3a4a; }
        .sidebar-brand h2 { font-size: 0.9rem; color: #fff; font-weight: 600; }
        .sidebar-brand span { font-size: 0.7rem; color: #7b8fa3; }
        .sidebar-nav { padding: 0.75rem 0.75rem; }
        .sidebar-nav a { display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.75rem; border-radius: 6px; color: #b0bec5; text-decoration: none; font-size: 0.82rem; margin-bottom: 0.2rem; transition: all 0.15s; }
        .sidebar-nav a:hover { background: #2a3a4a; color: #fff; }
        .sidebar-nav a.active { background: #049fd9; color: #fff; }
        .sidebar-nav a svg { width: 16px; height: 16px; fill: currentColor; }
        .server-list { padding: 0.75rem; flex: 1; }
        .server-list h3 { font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1.2px; color: #7b8fa3; margin-bottom: 0.6rem; padding: 0 0.5rem; }
        .server-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.6rem; border-radius: 6px; margin-bottom: 0.3rem; font-size: 0.78rem; }
        .server-item:hover { background: #2a3a4a; }
        .server-item .dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
        .server-item .dot.connected { background: #00c853; }
        .server-item .dot.disconnected { background: #ff5252; }
        .server-item .dot.unconfigured { background: #7b8fa3; }
        .server-item .sname { color: #b0bec5; }
        .sidebar-footer { padding: 0.75rem; border-top: 1px solid #2a3a4a; }
        .chat-area { flex: 1; display: flex; flex-direction: column; }
        .chat-header { padding: 0.85rem 2rem; border-bottom: 1px solid #e0e5e9; background: #fff; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
        .chat-header h1 { font-size: 1rem; color: #1b2733; font-weight: 600; }
        .chat-header .badge { font-size: 0.65rem; background: #e8f7fd; color: #049fd9; padding: 0.2rem 0.6rem; border-radius: 10px; font-weight: 600; border: 1px solid #b8e6f9; }
        .chat-messages { flex: 1; padding: 1.5rem 2rem; overflow-y: auto; background: #f5f6f7; }
        .msg { max-width: 680px; margin-bottom: 1.25rem; }
        .msg-bubble { padding: 1rem 1.25rem; border-radius: 10px; font-size: 0.83rem; line-height: 1.6; }
        .msg.system .msg-bubble { background: #fff; border: 1px solid #e0e5e9; color: #5a6872; box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
        .msg.user { display: flex; flex-direction: column; align-items: flex-end; }
        .msg.user .msg-bubble { background: #049fd9; color: #fff; border-radius: 10px 10px 4px 10px; display: inline-block; }
        .msg.user .msg-label { text-align: right; }
        .msg.bot .msg-bubble { background: #fff; border: 1px solid #e0e5e9; color: #1b2733; box-shadow: 0 1px 2px rgba(0,0,0,0.03); border-left: 3px solid #049fd9; }
        .msg-label { font-size: 0.65rem; color: #7b8fa3; margin-bottom: 0.3rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .connect-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.75rem; margin: 1rem 0; }
        .connect-card { background: #fff; border: 1px solid #e0e5e9; border-radius: 10px; padding: 1.25rem 1rem; text-align: center; transition: all 0.15s; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
        .connect-card:hover { border-color: #049fd9; box-shadow: 0 2px 8px rgba(4,159,217,0.1); }
        .connect-card .icon { font-size: 1.75rem; margin-bottom: 0.5rem; }
        .connect-card .name { font-size: 0.82rem; color: #1b2733; margin-bottom: 0.3rem; font-weight: 600; }
        .connect-card .status { font-size: 0.7rem; margin-bottom: 0.6rem; }
        .connect-card .status.ok { color: #00c853; font-weight: 600; }
        .connect-card .status.pending { color: #5a6872; }
        .connect-card .status.error { color: #ff5252; }
        .btn { padding: 0.4rem 1rem; border-radius: 4px; border: none; cursor: pointer; font-size: 0.75rem; font-weight: 600; transition: all 0.15s; }
        .btn-connect { background: #049fd9; color: #fff; }
        .btn-connect:hover { background: #037fb3; }
        .btn-reconnect { background: transparent; color: #049fd9; border: 1px solid #049fd9; }
        .btn-reconnect:hover { background: #049fd911; }
        .btn-danger { background: transparent; color: #ff5252; border: 1px solid #ff525244; font-size: 0.7rem; margin-top: 0.3rem; }
        .btn-danger:hover { background: #ff525211; }
        .chat-input { padding: 1rem 2rem; border-top: 1px solid #e0e5e9; background: #fff; }
        .input-row { display: flex; gap: 0.75rem; max-width: 680px; }
        .input-row input { flex: 1; padding: 0.7rem 1rem; border-radius: 8px; border: 1px solid #d2d8de; background: #f5f6f7; color: #1b2733; font-size: 0.85rem; }
        .input-row input:focus { outline: none; border-color: #049fd9; background: #fff; }
        .input-row input::placeholder { color: #9aa5b1; }
        .input-row button { padding: 0.7rem 1.5rem; border-radius: 8px; border: none; background: #049fd9; color: #fff; font-weight: 600; cursor: pointer; font-size: 0.85rem; }
        .input-row button:hover { background: #037fb3; }
        .input-row button:disabled { background: #d2d8de; color: #9aa5b1; cursor: not-allowed; }
        .input-row input:disabled { background: #eef1f3; }
        .info-section { margin: 0.5rem 0; padding: 0.7rem; background: #f7f9fb; border: 1px solid #e0e5e9; border-radius: 6px; }
        .info-section pre { font-size: 0.7rem; color: #1b2733; line-height: 1.6; white-space: pre-wrap; word-break: break-all; font-family: 'SF Mono', monospace; margin: 0; }
        .connect-card .port { font-size: 0.68rem; color: #7b8fa3; margin-bottom: 0.3rem; font-family: 'SF Mono', monospace; }
        .sample-questions { display: flex; gap: 0.5rem; flex-wrap: wrap; max-width: 680px; margin: 0.75rem 0; }
        .sample-q { padding: 0.5rem 1rem; border-radius: 18px; border: 1px solid #049fd9; background: #fff; color: #049fd9; font-size: 0.8rem; cursor: pointer; transition: all 0.15s; font-weight: 500; }
        .sample-q:hover { background: #049fd9; color: #fff; }
        .sample-q.asked { background: #049fd9; color: #fff; opacity: 0.7; cursor: default; }
        .answer-block { animation: fadeIn 0.3s ease; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
        .reference-panel { max-width: 680px; margin: 0.75rem 0; background: #fff; border: 1px solid #e0e5e9; border-radius: 8px; font-size: 0.78rem; }
        .reference-panel summary { padding: 0.7rem 1rem; cursor: pointer; color: #049fd9; font-weight: 600; font-size: 0.78rem; }
        .reference-panel summary:hover { background: #f7f9fb; }
        .reference-panel[open] summary { border-bottom: 1px solid #e0e5e9; }
        .ref-table { width: 100%; border-collapse: collapse; padding: 0.5rem; }
        .ref-table th { text-align: left; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.5px; color: #5a6872; padding: 0.5rem 0.75rem; border-bottom: 1px solid #eef1f3; }
        .ref-table td { padding: 0.4rem 0.75rem; font-size: 0.72rem; border-bottom: 1px solid #f5f6f7; }
        .ref-table code { background: #f0f4f8; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.68rem; }
        .ref-note { padding: 0.5rem 0.75rem; font-size: 0.7rem; color: #5a6872; border-top: 1px solid #eef1f3; }
        .ref-note code { background: #f0f4f8; padding: 0.1rem 0.4rem; border-radius: 3px; font-size: 0.68rem; }
    </style>
</head>
<body>
<div class="layout">
    <div class="sidebar">
        <div class="sidebar-brand">
            <h2>MCP Agent Portal</h2>
            <span>Duo SSO + DCR Demo</span>
        </div>
        <div class="sidebar-nav">
            <a href="/" class="active">
                <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
                Chat
            </a>
            <a href="/config">
                <svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.49.49 0 00-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
                Settings
            </a>
        </div>
        <div class="server-list">
            <h3>Servers</h3>
            {% for id, server in servers.items() %}
            <div class="server-item">
                {% if id in registrations and registrations[id].get('token_response', {}).get('body', {}).get('access_token') %}
                    <div class="dot connected"></div>
                {% elif server.issuer %}
                    <div class="dot disconnected"></div>
                {% else %}
                    <div class="dot unconfigured"></div>
                {% endif %}
                <span class="sname">{{ server.icon }} {{ server.name.replace(' MCP Server', '') }}</span>
            </div>
            {% endfor %}
        </div>
        <div class="sidebar-footer">
            {% if registrations %}
            <form method="POST" action="/clear" style="display:inline">
                <button class="btn btn-danger" type="submit" style="width:100%;">Clear All Sessions</button>
            </form>
            {% endif %}
        </div>
    </div>
    <div class="chat-area">
        <div class="chat-header">
            <h1>MCP Agent Chat</h1>
            <span class="badge">DCR + Duo SSO</span>
        </div>
        <div class="chat-messages">
            <div class="msg system">
                <div class="msg-label">System</div>
                <div class="msg-bubble">
                    Connect to an MCP server below. Both this portal and Claude Code authenticate through Duo SSO via Dynamic Client Registration.
                </div>
            </div>

            <div class="connect-cards">
                {% for id, server in servers.items() %}
                <div class="connect-card">
                    <div class="icon">{{ server.icon }}</div>
                    <div class="name">{{ server.name.replace(' MCP Server', '') }}</div>
                    <div class="port">:{{ server.mcp_port }}</div>
                    {% if id in registrations and registrations[id].get('token_response', {}).get('body', {}).get('access_token') %}
                        <div class="status ok">Connected</div>
                        <form method="POST" action="/connect/{{ id }}" style="display:inline">
                            <button class="btn btn-reconnect" type="submit">Reconnect</button>
                        </form>
                    {% elif server.issuer %}
                        <div class="status pending">Ready</div>
                        <form method="POST" action="/connect/{{ id }}" style="display:inline">
                            <button class="btn btn-connect" type="submit">Connect</button>
                        </form>
                    {% else %}
                        <div class="status error">Not configured</div>
                        <a href="/config" class="btn btn-reconnect">Configure</a>
                    {% endif %}
                    {% if id in registrations %}
                    <form method="POST" action="/clear/{{ id }}">
                        <button class="btn btn-danger" type="submit">Disconnect</button>
                    </form>
                    {% endif %}
                </div>
                {% endfor %}
            </div>

            <div class="msg bot">
                <div class="msg-label">Claude Code Setup</div>
                <div class="msg-bubble">
                    <div class="info-section">
                        <pre>claude mcp add dcr-calendar --transport http http://localhost:3001/mcp
claude mcp add dcr-documents --transport http http://localhost:3002/mcp
claude mcp add dcr-analytics --transport http http://localhost:3003/mcp</pre>
                    </div>
                </div>
            </div>

            <details class="reference-panel">
                <summary>Duo Admin Reference (Redirect URIs, Resources, Scopes)</summary>
                <table class="ref-table">
                    <thead><tr><th>Server</th><th>Resource URI</th><th>Portal Redirect</th><th>Scopes</th></tr></thead>
                    <tbody>
                        {% for id, server in servers.items() %}
                        <tr>
                            <td>{{ server.icon }} {{ server.name.replace(' MCP Server', '') }} (:{{ server.mcp_port }})</td>
                            <td><code>http://localhost:{{ server.mcp_port }}/</code></td>
                            <td><code>http://localhost:8080/callback/{{ id }}</code></td>
                            <td><code>openid email profile</code></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                <div class="ref-note">
                    Claude Code redirect (all servers): <code>http://127.0.0.1/callback</code> &amp; <code>http://localhost/callback</code>
                </div>
            </details>

            {% set connected_count = [] %}
            {% for id, reg in registrations.items() if reg.get('token_response', {}).get('body', {}).get('access_token') %}
                {% if connected_count.append(1) %}{% endif %}
            {% endfor %}

            {% if connected_count | length == 3 %}
            <div class="msg system">
                <div class="msg-label">System</div>
                <div class="msg-bubble">All 3 servers connected. Try a question:</div>
            </div>
            <div class="sample-questions">
                <button class="sample-q" onclick="askQuestion(this)" data-target="answer-calendar">What's on my calendar this week?</button>
                <button class="sample-q" onclick="askQuestion(this)" data-target="answer-docs">Find any docs about MCP auth</button>
                <button class="sample-q" onclick="askQuestion(this)" data-target="answer-analytics">Show me today's auth metrics</button>
            </div>

            <div id="answer-calendar" class="answer-block" style="display:none;">
                <div class="msg user">
                    <div class="msg-label">You</div>
                    <div class="msg-bubble">What's on my calendar this week?</div>
                </div>
                <div class="msg bot">
                    <div class="msg-label">via Calendar MCP</div>
                    <div class="msg-bubble">
                        <div class="info-section"><pre>{
  "events": [
    {"id": "evt-001", "title": "Sprint Planning", "date": "2026-07-14", "time": "09:00", "duration": "60m", "attendees": ["alice@acme.com", "bob@acme.com", "colin@acme.com"]},
    {"id": "evt-002", "title": "1:1 with Manager", "date": "2026-07-14", "time": "14:00", "duration": "30m", "attendees": ["colin@acme.com", "dana@acme.com"]},
    {"id": "evt-003", "title": "Security Review", "date": "2026-07-15", "time": "10:00", "duration": "45m", "attendees": ["colin@acme.com", "infosec@acme.com"]},
    {"id": "evt-004", "title": "Demo Day", "date": "2026-07-16", "time": "15:00", "duration": "60m", "attendees": ["team-all@acme.com"]},
    {"id": "evt-005", "title": "Vendor Sync - Duo SSO", "date": "2026-07-17", "time": "11:00", "duration": "30m", "attendees": ["colin@acme.com", "vendor@partner.io"]}
  ],
  "count": 5
}</pre></div>
                        You have 5 meetings this week. Busiest day is Monday with Sprint Planning and your 1:1.
                    </div>
                </div>
            </div>

            <div id="answer-docs" class="answer-block" style="display:none;">
                <div class="msg user">
                    <div class="msg-label">You</div>
                    <div class="msg-bubble">Find any docs about MCP auth</div>
                </div>
                <div class="msg bot">
                    <div class="msg-label">via Documents MCP</div>
                    <div class="msg-bubble">
                        <div class="info-section"><pre>{
  "query": "MCP auth",
  "results": [
    {"id": "doc-002", "name": "Architecture Decision Record - MCP Auth.md", "folder": "/engineering", "size": "18 KB", "modified": "2026-07-12", "owner": "colin@acme.com"}
  ],
  "count": 1
}</pre></div>
                        Found 1 result: <strong>Architecture Decision Record - MCP Auth.md</strong> in /engineering, last modified July 12.
                    </div>
                </div>
            </div>

            <div id="answer-analytics" class="answer-block" style="display:none;">
                <div class="msg user">
                    <div class="msg-label">You</div>
                    <div class="msg-bubble">Show me today's auth metrics</div>
                </div>
                <div class="msg bot">
                    <div class="msg-label">via Analytics MCP</div>
                    <div class="msg-bubble">
                        <div class="info-section"><pre>{
  "summary": {
    "users_today": 1247,
    "auth_attempts": 8934,
    "success_rate": "98.7%",
    "latency": "243ms",
    "dcr_this_week": 23
  },
  "recent_events": [
    {"timestamp": "2026-07-13T09:12:00Z", "event": "dcr_registration", "actor": "Calendar MCP Server", "result": "success"},
    {"timestamp": "2026-07-13T09:15:00Z", "event": "user_auth", "actor": "colin@acme.com", "result": "success"},
    {"timestamp": "2026-07-13T09:20:00Z", "event": "token_exchange", "actor": "Documents MCP Server", "result": "denied"}
  ]
}</pre></div>
                        1,247 active users today with 98.7% MFA success rate. 23 DCR registrations this week. Latency is 243ms avg.
                    </div>
                </div>
            </div>
            {% endif %}

            {% if registrations %}
            {% for id, reg in registrations.items() %}
                {% if reg.get('error') %}
                <div class="msg system">
                    <div class="msg-label">{{ servers[id].icon }} {{ servers[id].name }}</div>
                    <div class="msg-bubble" style="border-left: 3px solid #ff5252; color: #c62828;">
                        Error: {{ reg.error }}
                    </div>
                </div>
                {% endif %}
            {% endfor %}
            {% endif %}
        </div>
        <div class="chat-input">
            <div class="input-row">
                <input type="text" placeholder="Ask the agent something... (connect to a server first)" disabled>
                <button disabled>Send</button>
            </div>
        </div>
    </div>
</div>
<script>
function askQuestion(btn) {
    if (btn.classList.contains('asked')) return;
    btn.classList.add('asked');
    var target = document.getElementById(btn.getAttribute('data-target'));
    if (target) {
        target.style.display = 'block';
        target.scrollIntoView({behavior: 'smooth', block: 'nearest'});
    }
}
</script>
</body>
</html>"""

CALLBACK_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Connected - {{ server.get('name', server_id) }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'CiscoSans', -apple-system, system-ui, sans-serif; background: #f5f6f7; color: #1b2733; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .card { background: #fff; border: 1px solid #e0e5e9; border-radius: 12px; padding: 2.5rem; max-width: 700px; width: 100%; margin: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        h1 { font-size: 1.3rem; color: #1b2733; margin-bottom: 0.5rem; font-weight: 600; }
        .success { color: #00c853; font-size: 0.85rem; margin-bottom: 1.5rem; font-weight: 500; }
        .error { color: #ff5252; font-size: 0.85rem; margin-bottom: 1.5rem; font-weight: 500; }
        .steps { margin-bottom: 1.5rem; }
        .step { display: flex; align-items: flex-start; gap: 0.75rem; padding: 0.75rem 0; border-bottom: 1px solid #eef1f3; }
        .step:last-child { border-bottom: none; }
        .step-num { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 700; flex-shrink: 0; }
        .step-num.ok { background: #049fd9; color: #fff; }
        .step-num.fail { background: #ff5252; color: white; }
        .step-text { flex: 1; }
        .step-title { font-size: 0.83rem; color: #1b2733; font-weight: 500; }
        .step-detail { font-size: 0.72rem; color: #5a6872; font-family: 'SF Mono', monospace; margin-top: 0.2rem; word-break: break-all; }
        .token-section { margin-top: 1.5rem; }
        .token-section h2 { font-size: 0.75rem; color: #049fd9; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.5rem; font-weight: 700; }
        pre { background: #f7f9fb; border: 1px solid #e0e5e9; border-radius: 6px; padding: 1rem; font-size: 0.72rem; color: #1b2733; overflow-x: auto; white-space: pre-wrap; word-break: break-all; margin-bottom: 1rem; font-family: 'SF Mono', monospace; }
        .back { display: inline-block; margin-top: 1.5rem; color: #049fd9; text-decoration: none; font-size: 0.85rem; font-weight: 500; }
        .back:hover { text-decoration: underline; }
    </style>
</head>
<body>
<div class="card">
    <h1>{{ server.get('icon', '') }} {{ server.get('name', server_id) }}</h1>
    {% if code %}
        <p class="success">Authenticated via DCR + OAuth 2.1 (PKCE)</p>
        <div class="steps">
            <div class="step"><div class="step-num ok">1</div><div class="step-text"><div class="step-title">Dynamic Client Registration</div><div class="step-detail">POST /register &rarr; got client_id</div></div></div>
            <div class="step"><div class="step-num ok">2</div><div class="step-text"><div class="step-title">Authorization Code + PKCE</div><div class="step-detail">Redirected to Duo SSO &rarr; user authenticated</div></div></div>
            <div class="step"><div class="step-num ok">3</div><div class="step-text"><div class="step-title">Callback</div><div class="step-detail">code: {{ code[:20] }}...</div></div></div>
            {% if token_response %}
                {% if token_response.get('body', {}).get('access_token') %}
                    <div class="step"><div class="step-num ok">4</div><div class="step-text"><div class="step-title">Token Exchange</div><div class="step-detail">POST {{ token_response.endpoint }} &rarr; {{ token_response.status_code }}</div></div></div>
                    <div class="step"><div class="step-num ok">5</div><div class="step-text"><div class="step-title">Bearer Token Ready</div><div class="step-detail">MCP tools on :{{ server.get('mcp_port', '?') }} are now accessible</div></div></div>
                {% else %}
                    <div class="step"><div class="step-num fail">4</div><div class="step-text"><div class="step-title">Token Exchange Failed</div><div class="step-detail">{{ token_response | tojson }}</div></div></div>
                {% endif %}
            {% endif %}
        </div>

        {% if decoded_tokens %}
        <div class="token-section">
            {% for token_name, decoded in decoded_tokens.items() %}
                <h2>{{ token_name }}</h2>
                {% if decoded.get('payload') %}
                    <pre>{{ decoded.payload | tojson(indent=2) }}</pre>
                {% else %}
                    <pre>{{ decoded | tojson(indent=2) }}</pre>
                {% endif %}
            {% endfor %}
        </div>
        {% endif %}

        {% if token_response and token_response.get('body') %}
            <h2 style="font-size:0.75rem; color:#5a6872; margin-bottom:0.5rem; font-weight:600;">Raw Response</h2>
            <pre>{{ token_response.body | tojson(indent=2) }}</pre>
        {% endif %}

    {% elif error %}
        <p class="error">Connection failed: {{ error }}</p>
        <pre>{{ params | tojson(indent=2) }}</pre>
    {% endif %}
    <a class="back" href="/">&larr; Back to Chat</a>
</div>
</body>
</html>"""

JSON_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>{{ title }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'CiscoSans', -apple-system, system-ui, sans-serif; background: #f5f6f7; color: #1b2733; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .card { background: #fff; border: 1px solid #e0e5e9; border-radius: 12px; padding: 2rem; max-width: 800px; width: 100%; margin: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        h2 { font-size: 1.1rem; color: #1b2733; margin-bottom: 1rem; font-weight: 600; }
        pre { background: #f7f9fb; border: 1px solid #e0e5e9; border-radius: 6px; padding: 1rem; font-size: 0.78rem; color: #1b2733; overflow-x: auto; white-space: pre-wrap; font-family: 'SF Mono', monospace; }
        a { color: #049fd9; text-decoration: none; font-size: 0.85rem; font-weight: 500; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
<div class="card">
    <h2>{{ title }}</h2>
    <pre>{{ data | tojson(indent=2) }}</pre>
    <p style="margin-top: 1rem;"><a href="/">&larr; Back</a></p>
</div>
</body>
</html>"""


EXCHANGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>Token Exchange - {{ src.name }} &rarr; {{ target.name }}</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'CiscoSans', -apple-system, system-ui, sans-serif; background: #f5f6f7; color: #1b2733; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .card { background: #fff; border: 1px solid #e0e5e9; border-radius: 12px; padding: 2.5rem; max-width: 700px; width: 100%; margin: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
        h1 { font-size: 1.25rem; color: #1b2733; margin-bottom: 0.25rem; font-weight: 600; }
        .subtitle { color: #5a6872; font-size: 0.85rem; margin-bottom: 1.5rem; }
        .flow { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; padding: 1rem; background: #f7f9fb; border: 1px solid #e0e5e9; border-radius: 8px; flex-wrap: wrap; justify-content: center; }
        .flow-item { padding: 0.5rem 1rem; border-radius: 4px; font-size: 0.82rem; font-weight: 600; }
        .flow-source { background: #e8f7fd; color: #049fd9; border: 1px solid #b8e6f9; }
        .flow-arrow { color: #9aa5b1; font-size: 1.2rem; }
        .flow-target { background: #e8f5e9; color: #2e7d32; border: 1px solid #a5d6a7; }
        .flow-scope { background: #f3e8fd; color: #7b1fa2; border: 1px solid #ce93d8; font-family: 'SF Mono', monospace; }
        h2 { font-size: 0.75rem; color: #049fd9; text-transform: uppercase; letter-spacing: 0.5px; margin: 1rem 0 0.5rem; font-weight: 700; }
        pre { background: #f7f9fb; border: 1px solid #e0e5e9; border-radius: 6px; padding: 1rem; font-size: 0.72rem; color: #1b2733; overflow-x: auto; white-space: pre-wrap; word-break: break-all; margin-bottom: 0.75rem; font-family: 'SF Mono', monospace; }
        .error { color: #ff5252; margin-bottom: 1rem; font-weight: 500; }
        .result-ok { color: #00c853; font-size: 0.85rem; margin-bottom: 0.5rem; font-weight: 500; }
        .result-fail { color: #ff5252; font-size: 0.85rem; margin-bottom: 0.5rem; font-weight: 500; }
        a { color: #049fd9; text-decoration: none; font-size: 0.85rem; font-weight: 500; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
<div class="card">
    <h1>Token Exchange</h1>
    <p class="subtitle">RFC 8693: {{ src.icon }} {{ src.name }} &rarr; {{ target.icon }} {{ target.name }}</p>

    <div class="flow">
        <span class="flow-item flow-source">{{ src.icon }} {{ src.name.replace(' MCP Server', '') }}</span>
        <span class="flow-arrow">&rarr;</span>
        <span class="flow-item flow-scope">read:calendar</span>
        <span class="flow-arrow">&rarr;</span>
        <span class="flow-item flow-target">{{ target.icon }} {{ target.name.replace(' MCP Server', '') }}</span>
    </div>

    {% if error %}
        <p class="error">{{ error }}</p>
    {% elif exchange_result %}
        <h2>Request</h2>
        <pre>{{ exchange_result.request | tojson(indent=2) }}</pre>

        {% if exchange_result.get('status_code') %}
            {% if exchange_result.get('response', {}).get('access_token') %}
                <p class="result-ok">Exchange successful ({{ exchange_result.status_code }})</p>
            {% else %}
                <p class="result-fail">Exchange returned {{ exchange_result.status_code }}</p>
            {% endif %}

            {% if exchange_result.get('response') %}
                <h2>Response</h2>
                <pre>{{ exchange_result.response | tojson(indent=2) }}</pre>
            {% endif %}
        {% endif %}

        {% if exchanged_decoded and exchanged_decoded.get('access_token') %}
            <h2>Decoded Token</h2>
            <pre>{{ exchanged_decoded.access_token.payload | tojson(indent=2) }}</pre>
        {% endif %}
    {% endif %}

    <p style="margin-top: 1.5rem;"><a href="/">&larr; Back to Chat</a></p>
</div>
</body>
</html>"""


if __name__ == "__main__":
    print(f"\n  Chatbot Portal running at {BASE_URL}")
    print(f"  Configure issuers at {BASE_URL}/config")
    print(f"\n  Make sure MCP servers are running: python3 servers.py --all\n")
    app.run(host="0.0.0.0", port=PORT, debug=True)
