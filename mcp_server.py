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


# =============================================================================
# Fake business tools per server identity
# =============================================================================

if args.server == "calendar":
    _events = [
        {"id": "evt-001", "title": "Sprint Planning", "date": "2026-07-14", "time": "09:00", "duration": "60m", "attendees": ["alice@acme.com", "bob@acme.com", "colin@acme.com"]},
        {"id": "evt-002", "title": "1:1 with Manager", "date": "2026-07-14", "time": "14:00", "duration": "30m", "attendees": ["colin@acme.com", "dana@acme.com"]},
        {"id": "evt-003", "title": "Security Review", "date": "2026-07-15", "time": "10:00", "duration": "45m", "attendees": ["colin@acme.com", "infosec@acme.com"]},
        {"id": "evt-004", "title": "Demo Day", "date": "2026-07-16", "time": "15:00", "duration": "60m", "attendees": ["team-all@acme.com"]},
        {"id": "evt-005", "title": "Vendor Sync - Duo SSO", "date": "2026-07-17", "time": "11:00", "duration": "30m", "attendees": ["colin@acme.com", "vendor@partner.io"]},
    ]

    @mcp.tool()
    def list_events(date: str = "") -> str:
        """List upcoming calendar events. Optionally filter by date (YYYY-MM-DD)."""
        if date:
            filtered = [e for e in _events if e["date"] == date]
        else:
            filtered = _events
        return json.dumps({"events": filtered, "count": len(filtered)}, indent=2)

    @mcp.tool()
    def get_event(event_id: str) -> str:
        """Get details of a specific calendar event by ID."""
        for e in _events:
            if e["id"] == event_id:
                return json.dumps(e, indent=2)
        return json.dumps({"error": f"Event {event_id} not found"})

    @mcp.tool()
    def create_event(title: str, date: str, time: str, duration: str = "30m", attendees: str = "") -> str:
        """Create a new calendar event. Attendees as comma-separated emails."""
        event = {
            "id": f"evt-{secrets.token_hex(3)}",
            "title": title,
            "date": date,
            "time": time,
            "duration": duration,
            "attendees": [a.strip() for a in attendees.split(",") if a.strip()],
        }
        _events.append(event)
        return json.dumps({"created": event}, indent=2)

    @mcp.tool()
    def check_availability(date: str, time: str) -> str:
        """Check if a time slot is available on a given date."""
        conflicts = [e for e in _events if e["date"] == date and e["time"] == time]
        return json.dumps({
            "date": date,
            "time": time,
            "available": len(conflicts) == 0,
            "conflicts": conflicts,
        }, indent=2)


elif args.server == "documents":
    _documents = [
        {"id": "doc-001", "name": "Q3 Product Roadmap.pdf", "folder": "/planning", "size": "2.4 MB", "modified": "2026-07-10", "owner": "colin@acme.com"},
        {"id": "doc-002", "name": "Architecture Decision Record - MCP Auth.md", "folder": "/engineering", "size": "18 KB", "modified": "2026-07-12", "owner": "colin@acme.com"},
        {"id": "doc-003", "name": "SSO Migration Runbook.docx", "folder": "/ops", "size": "156 KB", "modified": "2026-07-08", "owner": "dana@acme.com"},
        {"id": "doc-004", "name": "Vendor Security Assessment - 2026.xlsx", "folder": "/security", "size": "89 KB", "modified": "2026-07-11", "owner": "infosec@acme.com"},
        {"id": "doc-005", "name": "Team OKRs H2 2026.md", "folder": "/planning", "size": "5 KB", "modified": "2026-07-01", "owner": "dana@acme.com"},
    ]

    @mcp.tool()
    def list_documents(folder: str = "") -> str:
        """List documents. Optionally filter by folder path."""
        if folder:
            filtered = [d for d in _documents if d["folder"] == folder]
        else:
            filtered = _documents
        return json.dumps({"documents": filtered, "count": len(filtered)}, indent=2)

    @mcp.tool()
    def get_document(doc_id: str) -> str:
        """Get metadata for a specific document by ID."""
        for d in _documents:
            if d["id"] == doc_id:
                return json.dumps(d, indent=2)
        return json.dumps({"error": f"Document {doc_id} not found"})

    @mcp.tool()
    def search_documents(query: str) -> str:
        """Search documents by name (case-insensitive substring match)."""
        results = [d for d in _documents if query.lower() in d["name"].lower()]
        return json.dumps({"query": query, "results": results, "count": len(results)}, indent=2)

    @mcp.tool()
    def upload_document(name: str, folder: str = "/uploads") -> str:
        """Upload (create) a new document entry."""
        doc = {
            "id": f"doc-{secrets.token_hex(3)}",
            "name": name,
            "folder": folder,
            "size": "0 KB",
            "modified": "2026-07-13",
            "owner": "colin@acme.com",
        }
        _documents.append(doc)
        return json.dumps({"uploaded": doc}, indent=2)

    @mcp.tool()
    def list_folders() -> str:
        """List all folders that contain documents."""
        folders = sorted(set(d["folder"] for d in _documents))
        return json.dumps({"folders": folders}, indent=2)


elif args.server == "analytics":
    _metrics = {
        "daily_active_users": {"value": 1247, "change": "+3.2%", "period": "2026-07-13"},
        "auth_attempts_today": {"value": 8934, "change": "+12%", "period": "2026-07-13"},
        "mfa_success_rate": {"value": "98.7%", "change": "+0.1%", "period": "2026-07-13"},
        "avg_auth_latency_ms": {"value": 243, "change": "-8ms", "period": "2026-07-13"},
        "dcr_registrations_week": {"value": 23, "change": "+5", "period": "2026-07-07 to 2026-07-13"},
        "active_sessions": {"value": 892, "change": "-2%", "period": "2026-07-13"},
    }
    _audit_log = [
        {"timestamp": "2026-07-13T09:12:00Z", "event": "dcr_registration", "actor": "Calendar MCP Server", "result": "success"},
        {"timestamp": "2026-07-13T09:15:00Z", "event": "user_auth", "actor": "colin@acme.com", "result": "success"},
        {"timestamp": "2026-07-13T09:20:00Z", "event": "token_exchange", "actor": "Documents MCP Server", "result": "denied"},
        {"timestamp": "2026-07-13T10:01:00Z", "event": "dcr_registration", "actor": "Analytics MCP Server", "result": "success"},
        {"timestamp": "2026-07-13T10:45:00Z", "event": "user_auth", "actor": "alice@acme.com", "result": "mfa_timeout"},
        {"timestamp": "2026-07-13T11:30:00Z", "event": "policy_update", "actor": "admin@acme.com", "result": "success"},
    ]

    @mcp.tool()
    def get_metrics(metric: str = "") -> str:
        """Get current metrics. Specify a metric name or leave empty for all."""
        if metric:
            if metric in _metrics:
                return json.dumps({metric: _metrics[metric]}, indent=2)
            return json.dumps({"error": f"Unknown metric: {metric}", "available": list(_metrics.keys())})
        return json.dumps({"metrics": _metrics}, indent=2)

    @mcp.tool()
    def get_audit_log(event_type: str = "", limit: int = 10) -> str:
        """Get recent audit log entries. Optionally filter by event type."""
        if event_type:
            entries = [e for e in _audit_log if e["event"] == event_type]
        else:
            entries = _audit_log
        return json.dumps({"entries": entries[:limit], "total": len(entries)}, indent=2)

    @mcp.tool()
    def get_dashboard_summary() -> str:
        """Get a summary dashboard with key metrics and recent activity."""
        return json.dumps({
            "summary": {
                "users_today": _metrics["daily_active_users"]["value"],
                "auth_attempts": _metrics["auth_attempts_today"]["value"],
                "success_rate": _metrics["mfa_success_rate"]["value"],
                "latency": f"{_metrics['avg_auth_latency_ms']['value']}ms",
                "dcr_this_week": _metrics["dcr_registrations_week"]["value"],
            },
            "recent_events": _audit_log[:3],
        }, indent=2)

    @mcp.tool()
    def query_usage(group_by: str = "hour") -> str:
        """Query usage data grouped by time period (hour, day, week)."""
        fake_data = {
            "hour": [{"period": f"2026-07-13T{h:02d}:00Z", "requests": 300 + (h * 47) % 200} for h in range(8, 18)],
            "day": [{"period": f"2026-07-{d:02d}", "requests": 7000 + (d * 311) % 2000} for d in range(7, 14)],
            "week": [{"period": f"2026-W{w}", "requests": 45000 + (w * 1337) % 10000} for w in range(24, 29)],
        }
        if group_by not in fake_data:
            return json.dumps({"error": f"Invalid group_by: {group_by}", "valid": ["hour", "day", "week"]})
        return json.dumps({"group_by": group_by, "data": fake_data[group_by]}, indent=2)


# =============================================================================
# DCR management tools (shared across all server types)
# =============================================================================

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
