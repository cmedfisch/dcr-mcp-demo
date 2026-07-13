"""
DCR Demo - 3 Fake MCP Servers registering via OAuth Dynamic Client Registration.

Run:
    pip install flask requests
    python3 app.py

Then open http://localhost:8080 — configure each server's endpoints on the /config page.
"""

import os
import json
import secrets
import hashlib
import base64
from urllib.parse import urlencode

import requests
from flask import Flask, redirect, request, render_template_string, url_for

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

PORT = int(os.environ.get("PORT", "8080"))
BASE_URL = f"http://localhost:{PORT}"

# --- 3 Fake MCP Servers (each gets its own issuer) ---
SERVERS = {
    "calendar": {
        "name": "Calendar MCP Server",
        "description": "Manages calendar events and scheduling",
        "scopes": ["openid", "email", "profile"],
        "icon": "\U0001f4c5",
        "issuer": "",
    },
    "documents": {
        "name": "Documents MCP Server",
        "description": "File storage and document management",
        "scopes": ["openid", "email", "profile"],
        "icon": "\U0001f4c4",
        "issuer": "",
    },
    "analytics": {
        "name": "Analytics MCP Server",
        "description": "Usage metrics and reporting dashboard",
        "scopes": ["openid", "email", "profile"],
        "icon": "\U0001f4ca",
        "issuer": "",
    },
}


def derive_endpoints(issuer: str) -> dict:
    """Derive the 3 URLs from an issuer like https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXX"""
    issuer = issuer.rstrip("/")
    # Extract host and path parts
    # issuer: https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXX
    # oauth_metadata: https://sso-xxx.test.sso.duosecurity.com/.well-known/oauth-authorization-server/oauth2/DIXXXX
    # oidc_discovery: https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXX/.well-known/openid-configuration
    # registration: https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXX/register
    from urllib.parse import urlparse
    parsed = urlparse(issuer)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    return {
        "oauth_metadata_url": f"{base}/.well-known/oauth-authorization-server{path}",
        "oidc_discovery_url": f"{issuer}/.well-known/openid-configuration",
        "registration_endpoint": f"{issuer}/register",
    }

# In-memory registration state
registrations = {}


def fetch_metadata(url: str) -> dict:
    """Fetch a JSON metadata document."""
    if not url:
        return {"error": "URL not configured"}
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def do_dcr(server_id: str) -> dict:
    """Perform Dynamic Client Registration (RFC 7591)."""
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
    verifier = secrets.token_urlsafe(43)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def decode_jwt_unverified(token: str) -> dict:
    """Decode a JWT without signature verification (for display only)."""
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
def save_config(server_id):
    if server_id not in SERVERS:
        return "Unknown server", 404
    SERVERS[server_id]["issuer"] = request.form.get("issuer", "").strip()
    return redirect("/config")


@app.route("/connect/<server_id>", methods=["POST"])
def connect(server_id):
    """Single-click: DCR register (if needed) then redirect to Duo for auth."""
    if server_id not in SERVERS:
        return "Unknown server", 404

    server = SERVERS[server_id]
    if not server["issuer"]:
        return "Not configured. Go to <a href='/config'>/config</a> first.", 400

    # Step 1: Register via DCR if we don't already have a client_id
    if server_id not in registrations or not registrations[server_id].get("response", {}).get("client_id"):
        result = do_dcr(server_id)
        registrations[server_id] = result
        if not result.get("response", {}).get("client_id"):
            return redirect("/")  # show error on dashboard

    # Step 2: Build the authorize URL and redirect to Duo
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

        # Get token endpoint from metadata
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
                token_response = {
                    "status_code": resp.status_code,
                    "endpoint": token_endpoint,
                }
                try:
                    token_response["body"] = resp.json()
                except ValueError:
                    token_response["body_raw"] = resp.text

                # Store token response for use in token exchange
                registrations[server_id]["token_response"] = token_response

                # Decode JWTs (without verification — just for display)
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
    """
    RFC 8693 Token Exchange: source MCP server exchanges its access token
    for a new token scoped to the target MCP server.
    e.g., Documents exchanges its token for read:calendar on Calendar.
    """
    if source_id not in SERVERS or target_id not in SERVERS:
        return "Unknown server", 404

    source_server = SERVERS[source_id]
    target_server = SERVERS[target_id]
    source_reg = registrations.get(source_id, {})
    target_reg = registrations.get(target_id, {})

    # Need an access token from the source
    source_token = source_reg.get("token_response", {}).get("body", {}).get("access_token")
    if not source_token:
        return render_template_string(EXCHANGE_TEMPLATE,
            source=source_server, target=target_server,
            source_id=source_id, target_id=target_id,
            error="No access token for source server. Connect to it first.")

    # Target must be registered (need its client_id as audience)
    target_client_id = target_reg.get("response", {}).get("client_id", "")

    # Source needs client credentials for the exchange (confidential client)
    source_client_id = source_reg.get("response", {}).get("client_id", "")
    source_client_secret = source_reg.get("response", {}).get("client_secret", "")

    # Use source server's token endpoint
    endpoints = derive_endpoints(source_server["issuer"])
    metadata = fetch_metadata(endpoints["oauth_metadata_url"])
    token_endpoint = metadata.get("token_endpoint", "")

    if not token_endpoint:
        return render_template_string(EXCHANGE_TEMPLATE,
            source=source_server, target=target_server,
            source_id=source_id, target_id=target_id,
            error="Could not find token_endpoint in metadata")

    # Build RFC 8693 token exchange request
    exchange_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": source_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": "read:calendar",
        "client_id": source_client_id,
    }

    # Set audience to target's client_id if available
    if target_client_id:
        exchange_data["audience"] = target_client_id

    # Add client secret if we have one (confidential client)
    if source_client_secret:
        exchange_data["client_secret"] = source_client_secret

    exchange_result = {
        "endpoint": token_endpoint,
        "request": exchange_data.copy(),
    }

    try:
        resp = requests.post(token_endpoint, data=exchange_data, timeout=15)
        exchange_result["status_code"] = resp.status_code
        try:
            exchange_result["response"] = resp.json()
        except ValueError:
            exchange_result["response_raw"] = resp.text

        # Decode the exchanged token
        exchanged_decoded = {}
        body = exchange_result.get("response", {})
        if body.get("access_token") and "." in body["access_token"]:
            exchanged_decoded["access_token"] = decode_jwt_unverified(body["access_token"])
    except Exception as e:
        exchange_result["error"] = str(e)
        exchanged_decoded = {}

    return render_template_string(EXCHANGE_TEMPLATE,
        source=source_server, target=target_server,
        source_id=source_id, target_id=target_id,
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
    source = request.args.get("source", "oidc")
    url = endpoints["oidc_discovery_url"] if source == "oidc" else endpoints["oauth_metadata_url"]
    result = fetch_metadata(url)
    return render_template_string(JSON_TEMPLATE, title=f"{server['name']} - {source.upper()} Metadata", data=result)


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
        .card .icon { display: inline; margin-right: 0.5rem; }
        label { display: block; color: #8b949e; font-size: 0.8rem; margin-bottom: 0.25rem; margin-top: 0.75rem; }
        input[type="text"] { width: 100%; padding: 0.5rem; border-radius: 4px; border: 1px solid #30363d; background: #0d1117; color: #e1e4e8; font-family: monospace; font-size: 0.8rem; }
        input[type="text"]:focus { outline: none; border-color: #58a6ff; }
        .btn { display: inline-block; padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 500; text-decoration: none; margin-top: 1rem; }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .nav { margin-bottom: 1.5rem; }
        .nav a { color: #58a6ff; font-size: 0.85rem; text-decoration: none; }
        .derived { margin-top: 0.75rem; padding: 0.5rem; background: #0d1117; border-radius: 4px; }
        .derived-label { font-size: 0.75rem; color: #8b949e; margin-bottom: 0.25rem; }
        .derived-url { font-family: monospace; font-size: 0.7rem; color: #3fb950; }
    </style>
</head>
<body>
    <h1>Configure MCP Servers</h1>
    <p class="subtitle">Set the 3 OAuth/OIDC URLs for each MCP server</p>
    <div class="nav"><a href="/">&larr; Back to Dashboard</a></div>
    <div class="grid">
    {% for id, server in servers.items() %}
        <div class="card">
            <h2><span class="icon">{{ server.icon }}</span>{{ server.name }}</h2>
            <form method="POST" action="/config/{{ id }}">
                <label>Issuer URL</label>
                <input type="text" name="issuer" value="{{ server.issuer }}" placeholder="https://sso-xxx.test.sso.duosecurity.com/oauth2/DIXXXXXXXXXXXXXXXXXX">
                <button class="btn btn-primary" type="submit">Save</button>
            </form>
            {% if server.issuer %}
                <div class="derived">
                    <div class="derived-label">Derived endpoints:</div>
                    <div class="derived-url">.well-known/oauth-authorization-server</div>
                    <div class="derived-url">.well-known/openid-configuration</div>
                    <div class="derived-url">/register</div>
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
    <title>DCR Demo - MCP Servers</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; }
        h1 { margin-bottom: 0.5rem; font-size: 1.5rem; }
        .subtitle { color: #8b949e; margin-bottom: 2rem; font-size: 0.9rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 1.5rem; }
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 1.5rem; }
        .card h2 { font-size: 1.1rem; margin-bottom: 0.5rem; }
        .card .icon { font-size: 2rem; margin-bottom: 0.75rem; }
        .card .desc { color: #8b949e; font-size: 0.85rem; margin-bottom: 0.5rem; }
        .card .endpoints { font-size: 0.75rem; color: #6e7681; font-family: monospace; margin-bottom: 1rem; word-break: break-all; }
        .card .endpoints .configured { color: #3fb950; }
        .card .endpoints .missing { color: #da3633; }
        .btn { display: inline-block; padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 500; text-decoration: none; }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .btn-secondary { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
        .btn-secondary:hover { background: #30363d; }
        .btn-disabled { background: #21262d; color: #484f58; border: 1px solid #30363d; cursor: not-allowed; }
        .status { margin-top: 1rem; padding: 0.75rem; border-radius: 6px; font-size: 0.8rem; font-family: monospace; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow-y: auto; }
        .status-success { background: #0d1117; border: 1px solid #238636; }
        .status-error { background: #0d1117; border: 1px solid #da3633; }
        .status-pending { background: #0d1117; border: 1px solid #30363d; color: #8b949e; }
        .actions { display: flex; gap: 0.5rem; flex-wrap: wrap; }
        a.btn { display: inline-block; }
        .dcr-payload { margin: 0.75rem 0; }
        .dcr-label { font-size: 0.75rem; color: #8b949e; margin-bottom: 0.25rem; }
        .dcr-json { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 0.75rem; font-size: 0.75rem; color: #7ee787; white-space: pre; overflow-x: auto; margin: 0; }
        .nav { margin-bottom: 1rem; display: flex; gap: 1.5rem; }
        .nav a { color: #58a6ff; font-size: 0.85rem; text-decoration: none; }
    </style>
</head>
<body>
    <h1>DCR Demo: MCP Servers + Duo SSO</h1>
    <p class="subtitle">Dynamic Client Registration (RFC 7591) with PKCE public clients</p>
    <div class="nav">
        <a href="/config">Configure Servers</a>
        {% for id, server in servers.items() %}
            {% if server.issuer %}
                <a href="/metadata/{{ id }}?source=oauth">{{ server.icon }} Metadata</a>
            {% endif %}
        {% endfor %}
    </div>
    <div class="grid">
    {% for id, server in servers.items() %}
        <div class="card">
            <div class="icon">{{ server.icon }}</div>
            <h2>{{ server.name }}</h2>
            <p class="desc">{{ server.description }}</p>
            <div class="endpoints">
                {% if server.issuer %}
                    <span class="configured">{{ server.issuer }}</span>
                {% else %}
                    <span class="missing">Not configured &mdash; <a href="/config" style="color:#58a6ff">set issuer</a></span>
                {% endif %}
            </div>
            {% if server.issuer %}
                <div class="dcr-payload">
                    <div class="dcr-label">DCR Request Payload:</div>
                    <pre class="dcr-json">POST {{ server.issuer }}/register
Content-Type: application/json

{
  "client_name": "{{ server.name }}",
  "redirect_uris": ["{{ base_url }}/callback/{{ id }}"],
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none",
  "application_type": "web"
}</pre>
                </div>
            {% endif %}
            <div class="actions">
                {% if server.issuer %}
                    <form method="POST" action="/connect/{{ id }}" style="display:inline">
                        {% if id in registrations and registrations[id].get('response', {}).get('client_id') %}
                            <button class="btn btn-secondary" type="submit">Reconnect</button>
                        {% else %}
                            <button class="btn btn-primary" type="submit">Connect</button>
                        {% endif %}
                    </form>
                    {% if id == 'documents' and id in registrations and registrations[id].get('token_response', {}).get('body', {}).get('access_token') %}
                        <form method="POST" action="/token-exchange/documents/calendar" style="display:inline">
                            <button class="btn" style="background:#a371f7; color:white;" type="submit">Exchange &rarr; Calendar</button>
                        </form>
                    {% endif %}
                {% else %}
                    <span class="btn btn-disabled">Connect</span>
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
        .token-section { margin-top: 1.5rem; }
        .token-label { font-size: 0.85rem; font-weight: 600; color: #58a6ff; margin-bottom: 0.25rem; }
    </style>
</head>
<body>
    <h1>{{ server.get('icon', '') }} {{ server.get('name', server_id) }}</h1>
    {% if code %}
        <p class="success">Connected successfully via DCR + OAuth 2.1</p>
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
            {% else %}
                <div class="step step-fail">
                    <div class="step-title">4. Token Exchange</div>
                    <div class="step-detail">{{ token_response | tojson }}</div>
                </div>
            {% endif %}
        {% endif %}

        {% if decoded_tokens %}
            <div class="token-section">
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
        {% if server_id == 'documents' and token_response and token_response.get('body', {}).get('access_token') %}
            <div style="margin-top: 1.5rem; padding: 1rem; background: #161b22; border: 1px solid #a371f7; border-radius: 6px;">
                <div style="font-weight: 600; margin-bottom: 0.5rem; color: #a371f7;">RFC 8693 Token Exchange</div>
                <p style="font-size: 0.85rem; color: #8b949e; margin-bottom: 0.75rem;">
                    Exchange this access token for a <code>read:calendar</code> scoped token from the Calendar MCP Server.
                </p>
                <form method="POST" action="/token-exchange/documents/calendar" style="display:inline">
                    <button style="padding: 0.5rem 1rem; border-radius: 6px; border: none; cursor: pointer; font-size: 0.85rem; font-weight: 500; background: #a371f7; color: white;">Exchange Token &rarr; Calendar</button>
                </form>
            </div>
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
    <title>Token Exchange - {{ source.name }} &rarr; {{ target.name }}</title>
    <style>
        body { font-family: -apple-system, system-ui, sans-serif; background: #0f1117; color: #e1e4e8; padding: 2rem; max-width: 900px; }
        h1 { margin-bottom: 0.5rem; }
        .subtitle { color: #a371f7; font-size: 0.9rem; margin-bottom: 1.5rem; }
        h2 { font-size: 1rem; color: #8b949e; margin-top: 1.5rem; margin-bottom: 0.5rem; }
        pre { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; overflow-x: auto; font-size: 0.8rem; white-space: pre-wrap; word-break: break-all; }
        a { color: #58a6ff; }
        .error { color: #da3633; font-size: 1rem; margin-bottom: 1rem; }
        .success { color: #3fb950; }
        .step { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 1rem; margin-bottom: 0.75rem; }
        .step-title { font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem; }
        .step-detail { font-family: monospace; font-size: 0.8rem; color: #8b949e; word-break: break-all; }
        .step-ok { border-left: 3px solid #a371f7; }
        .step-fail { border-left: 3px solid #da3633; }
        .token-label { font-size: 0.85rem; font-weight: 600; color: #a371f7; margin-bottom: 0.25rem; }
        .flow { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1.5rem; padding: 1rem; background: #161b22; border-radius: 6px; }
        .flow-item { padding: 0.5rem 0.75rem; border-radius: 4px; font-size: 0.85rem; font-weight: 500; }
        .flow-source { background: #238636; color: white; }
        .flow-arrow { color: #8b949e; font-size: 1.2rem; }
        .flow-target { background: #1f6feb; color: white; }
        .flow-scope { background: #a371f7; color: white; font-family: monospace; font-size: 0.8rem; }
    </style>
</head>
<body>
    <h1>RFC 8693 Token Exchange</h1>
    <p class="subtitle">{{ source.icon }} {{ source.name }} &rarr; {{ target.icon }} {{ target.name }}</p>

    <div class="flow">
        <span class="flow-item flow-source">{{ source.icon }} {{ source.name }}</span>
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
    print(f"\n  DCR Demo running at {BASE_URL}")
    print(f"  Configure servers at {BASE_URL}/config\n")
    app.run(host="0.0.0.0", port=PORT, debug=True)
