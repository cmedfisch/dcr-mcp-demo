"""
DCR Demo - 3 Fake MCP Servers registering via OAuth Dynamic Client Registration.

Run:
    pip install flask requests
    export DUO_SSO_ISSUER="https://sso-XXXX.sso.duosecurity.com/oidc/DIXXXXXXXXXXXXXXXXXX"
    python3 app.py

Then open http://localhost:8080
"""

import os
import json
import secrets
import hashlib
import base64
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, render_template_string

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# --- Config ---
DUO_SSO_ISSUER = os.environ.get("DUO_SSO_ISSUER", "https://sso-XXXX.sso.duosecurity.com/oidc/DIXXXXXXXXXXXXXXXXXX")
PORT = int(os.environ.get("PORT", "8080"))
BASE_URL = f"http://localhost:{PORT}"

# --- 3 Fake MCP Servers ---
SERVERS = {
    "calendar": {
        "name": "Calendar MCP Server",
        "description": "Manages calendar events and scheduling",
        "scopes": ["openid", "email", "profile"],
        "icon": "📅",
    },
    "documents": {
        "name": "Documents MCP Server",
        "description": "File storage and document management",
        "scopes": ["openid", "email", "profile"],
        "icon": "📄",
    },
    "analytics": {
        "name": "Analytics MCP Server",
        "description": "Usage metrics and reporting dashboard",
        "scopes": ["openid", "email", "profile"],
        "icon": "📊",
    },
}

# In-memory registration state
registrations = {}


def discover_endpoints(issuer: str) -> dict:
    """Fetch OIDC discovery document."""
    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def do_dcr(server_id: str) -> dict:
    """Perform Dynamic Client Registration (RFC 7591) against Duo SSO."""
    server = SERVERS[server_id]
    redirect_uri = f"{BASE_URL}/callback/{server_id}"

    # Try discovery first
    discovery = discover_endpoints(DUO_SSO_ISSUER)
    reg_endpoint = discovery.get("registration_endpoint")

    # Fallback: common convention
    if not reg_endpoint:
        reg_endpoint = f"{DUO_SSO_ISSUER.rstrip('/')}/register"

    payload = {
        "client_name": server["name"],
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",  # public client
        "application_type": "web",
    }

    try:
        resp = requests.post(
            reg_endpoint,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        result = {
            "status_code": resp.status_code,
            "endpoint_used": reg_endpoint,
            "request_payload": payload,
        }
        try:
            result["response"] = resp.json()
        except ValueError:
            result["response_text"] = resp.text
        return result
    except Exception as e:
        return {
            "error": str(e),
            "endpoint_attempted": reg_endpoint,
            "request_payload": payload,
        }


def generate_pkce():
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(43)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# --- Routes ---

@app.route("/")
def dashboard():
    return render_template_string(TEMPLATE, servers=SERVERS, registrations=registrations, issuer=DUO_SSO_ISSUER)


@app.route("/register/<server_id>", methods=["POST"])
def register(server_id):
    if server_id not in SERVERS:
        return "Unknown server", 404
    result = do_dcr(server_id)
    registrations[server_id] = result
    return redirect("/")


@app.route("/authorize/<server_id>")
def authorize(server_id):
    """Start an authorization code flow with PKCE after DCR."""
    if server_id not in registrations:
        return "Register first", 400

    reg = registrations[server_id]
    client_id = reg.get("response", {}).get("client_id")
    if not client_id:
        return "No client_id from registration", 400

    discovery = discover_endpoints(DUO_SSO_ISSUER)
    auth_endpoint = discovery.get("authorization_endpoint", f"{DUO_SSO_ISSUER}/authorize")

    verifier, challenge = generate_pkce()
    # Store verifier for token exchange (in-memory demo)
    registrations[server_id]["pkce_verifier"] = verifier

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": f"{BASE_URL}/callback/{server_id}",
        "scope": " ".join(SERVERS[server_id]["scopes"]),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(16),
    }
    return redirect(f"{auth_endpoint}?{urlencode(params)}")


@app.route("/callback/<server_id>")
def callback(server_id):
    """OAuth callback - shows what came back."""
    code = request.args.get("code")
    error = request.args.get("error")
    return render_template_string(CALLBACK_TEMPLATE,
        server_id=server_id,
        server=SERVERS.get(server_id, {}),
        code=code, error=error,
        params=dict(request.args))


@app.route("/discovery")
def show_discovery():
    """Show raw OIDC discovery document."""
    result = discover_endpoints(DUO_SSO_ISSUER)
    return render_template_string(JSON_TEMPLATE, title="OIDC Discovery", data=result)


# --- Templates ---

TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <title>DCR Demo - MCP Servers</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; }
        h1 { margin-bottom: 0.5rem; font-size: 1.5rem; }
        .subtitle { color: #8b949e; margin-bottom: 2rem; font-size: 0.9rem; }
        .issuer { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 2rem; font-family: monospace; font-size: 0.8rem; word-break: break-all; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; }
        .card h2 { font-size: 1.1rem; margin-bottom: 0.5rem; }
        .card .icon { font-size: 2rem; margin-bottom: 0.75rem; }
        .card .desc { color: #8b949e; font-size: 0.85rem; margin-bottom: 1rem; }
        .btn { display: inline-block; padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 500; text-decoration: none; }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .btn-secondary { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
        .btn-secondary:hover { background: #30363d; }
        .status { margin-top: 1rem; padding: 0.75rem; border-radius: 6px; font-size: 0.8rem; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
        .status-success { background: #0d1117; border: 1px solid #238636; }
        .status-error { background: #0d1117; border: 1px solid #da3633; }
        .status-pending { background: #0d1117; border: 1px solid #30363d; color: #8b949e; }
        .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        a.btn { display: inline-block; }
        .nav { margin-bottom: 1rem; }
        .nav a { color: #58a6ff; font-size: 0.85rem; }
    </style>
</head>
<body>
    <h1>DCR Demo: MCP Servers + Duo SSO</h1>
    <p class="subtitle">Dynamic Client Registration (RFC 7591) with PKCE public clients</p>
    <div class="issuer">Issuer: {{ issuer }}</div>
    <div class="nav"><a href="/discovery">View OIDC Discovery Document</a></div>
    <div class="grid">
    {% for id, server in servers.items() %}
        <div class="card">
            <div class="icon">{{ server.icon }}</div>
            <h2>{{ server.name }}</h2>
            <p class="desc">{{ server.description }}</p>
            <div class="actions">
                <form method="POST" action="/register/{{ id }}" style="display:inline">
                    <button class="btn btn-primary" type="submit">Register via DCR</button>
                </form>
                {% if id in registrations and registrations[id].get('response', {}).get('client_id') %}
                    <a href="/authorize/{{ id }}" class="btn btn-secondary">Test Auth Flow</a>
                {% endif %}
            </div>
            {% if id in registrations %}
                {% set reg = registrations[id] %}
                {% if reg.get('response', {}).get('client_id') %}
                    <div class="status status-success">{{ reg | tojson }}</div>
                {% elif reg.get('error') %}
                    <div class="status status-error">{{ reg | tojson }}</div>
                {% else %}
                    <div class="status status-pending">{{ reg | tojson }}</div>
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
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; }
        h1 { margin-bottom: 1rem; }
        pre { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; overflow-x: auto; }
        a { color: #58a6ff; }
    </style>
</head>
<body>
    <h1>{{ server.get('icon', '') }} Callback: {{ server.get('name', server_id) }}</h1>
    {% if code %}
        <p style="color: #3fb950;">Authorization code received.</p>
        <pre>code: {{ code }}</pre>
    {% elif error %}
        <p style="color: #da3633;">Error: {{ error }}</p>
    {% endif %}
    <pre>{{ params | tojson }}</pre>
    <p style="margin-top: 1rem;"><a href="/">← Back to Dashboard</a></p>
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
    <p style="margin-top: 1rem;"><a href="/">← Back</a></p>
</body>
</html>"""


if __name__ == "__main__":
    print(f"\n  DCR Demo running at {BASE_URL}")
    print(f"  Duo SSO Issuer: {DUO_SSO_ISSUER}\n")
    app.run(host="0.0.0.0", port=PORT, debug=True)
