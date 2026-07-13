"""
MCP Server with OAuth DCR - connects to Claude Code via stdio.

Usage:
    python3 mcp_server.py --server calendar
    python3 mcp_server.py --server documents
    python3 mcp_server.py --server analytics

Env:
    DUO_SSO_ISSUER - Your Duo SSO issuer URL
"""

import os
import sys
import json
import secrets
import hashlib
import base64
import argparse
from urllib.parse import urlencode

import httpx
from mcp.server.fastmcp import FastMCP

# --- Server identities ---
IDENTITIES = {
    "calendar": {"name": "Calendar MCP Server", "description": "Manages calendar events and scheduling"},
    "documents": {"name": "Documents MCP Server", "description": "File storage and document management"},
    "analytics": {"name": "Analytics MCP Server", "description": "Usage metrics and reporting dashboard"},
}

# Parse args before creating the server
parser = argparse.ArgumentParser()
parser.add_argument("--server", choices=IDENTITIES.keys(), default="calendar")
args, _ = parser.parse_known_args()

identity = IDENTITIES[args.server]
DUO_SSO_ISSUER = os.environ.get("DUO_SSO_ISSUER", "https://sso-XXXX.sso.duosecurity.com/oidc/DIXXXXXXXXXXXXXXXXXX")

mcp = FastMCP(f"dcr-{args.server}")

# State
_registration: dict | None = None
_discovery: dict | None = None


@mcp.tool()
async def discover_duo_endpoints() -> str:
    """Fetch the OIDC discovery document from the configured Duo SSO issuer. Shows all available endpoints."""
    global _discovery
    url = f"{DUO_SSO_ISSUER.rstrip('/')}/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
        _discovery = resp.json()
        return json.dumps(_discovery, indent=2)


@mcp.tool()
async def register_client(redirect_uri: str = "http://localhost:3000/callback") -> str:
    """
    Perform Dynamic Client Registration (RFC 7591) against Duo SSO.
    Registers this MCP server as a public OAuth client with PKCE support.
    Uses a DIFFERENT redirect_uri than the web app (port 3000 vs 8080) so
    registrations don't collide.

    Args:
        redirect_uri: The redirect URI for this client (default: http://localhost:3000/callback)
    """
    global _registration, _discovery

    # Discover endpoints if not already done
    if not _discovery:
        url = f"{DUO_SSO_ISSUER.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10)
            _discovery = resp.json()

    reg_endpoint = _discovery.get("registration_endpoint", f"{DUO_SSO_ISSUER.rstrip('/')}/register")

    payload = {
        "client_name": f"{identity['name']} (MCP)",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "application_type": "web",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(reg_endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        result = {
            "server_identity": identity["name"],
            "dcr_endpoint": reg_endpoint,
            "request": payload,
            "status_code": resp.status_code,
        }
        try:
            result["response"] = resp.json()
            _registration = resp.json()
        except Exception:
            result["response_raw"] = resp.text

    return json.dumps(result, indent=2)


@mcp.tool()
def get_registration() -> str:
    """Return the current DCR registration details for this server, or indicate none exists."""
    if not _registration:
        return json.dumps({"status": "not_registered", "server": identity["name"]})
    return json.dumps({"server": identity["name"], "registration": _registration}, indent=2)


@mcp.tool()
def generate_auth_url() -> str:
    """
    Generate an authorization URL with PKCE for testing the OAuth flow
    after DCR registration. Returns the URL and the PKCE verifier.
    """
    if not _registration:
        return json.dumps({"error": "No registration. Run register_client first."})
    if not _discovery:
        return json.dumps({"error": "No discovery. Run discover_duo_endpoints first."})

    client_id = _registration.get("client_id")
    if not client_id:
        return json.dumps({"error": "Registration has no client_id"})

    verifier = secrets.token_urlsafe(43)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()

    auth_endpoint = _discovery.get("authorization_endpoint", f"{DUO_SSO_ISSUER}/authorize")
    redirect_uri = _registration.get("redirect_uris", ["http://localhost:8080/callback"])[0]

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": secrets.token_urlsafe(16),
    }

    url = f"{auth_endpoint}?{urlencode(params)}"
    return json.dumps({
        "authorization_url": url,
        "pkce_verifier": verifier,
        "note": "Open this URL in a browser to test the auth flow",
    }, indent=2)


@mcp.tool()
def reset_registration() -> str:
    """Clear the current DCR registration so you can register fresh."""
    global _registration, _discovery
    _registration = None
    _discovery = None
    return json.dumps({"status": "cleared", "server": identity["name"]})


@mcp.tool()
def server_info() -> str:
    """Return info about this MCP server's identity and configuration."""
    return json.dumps({
        "server_id": args.server,
        "name": identity["name"],
        "description": identity["description"],
        "duo_issuer": DUO_SSO_ISSUER,
        "registered": _registration is not None,
        "client_id": _registration.get("client_id") if _registration else None,
    }, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
