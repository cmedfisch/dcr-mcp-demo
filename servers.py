"""
3 MCP Servers running over HTTP with OAuth auth gates backed by Duo SSO.

Each server:
- Runs on its own port (3001=calendar, 3002=documents, 3003=analytics)
- Requires Bearer token authentication (validated as Duo-issued JWT)
- Exposes /.well-known/oauth-protected-resource (RFC 9728) pointing to Duo
- Clients (Claude Code, Codex, chatbot) must DCR + auth before seeing tools

Usage:
    python3 servers.py --server calendar   # port 3001
    python3 servers.py --server documents  # port 3002
    python3 servers.py --server analytics  # port 3003
    python3 servers.py --all               # all three (for demo)

Config:
    Edit config.json to set issuers per server, or set DUO_SSO_ISSUER env var as fallback.
"""

import os
import sys
import json
import secrets
import base64
import argparse
import asyncio
import multiprocessing
from dataclasses import dataclass
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from mcp.server.auth.provider import TokenVerifier, AccessToken

# --- Config ---
CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config() -> dict:
    """Load config.json with per-server issuers."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def get_issuer(server_id: str) -> str:
    """Get the issuer for a server from config.json or env var fallback."""
    cfg = load_config()
    issuer = cfg.get(server_id, {}).get("issuer", "")
    if not issuer:
        issuer = os.environ.get("DUO_SSO_ISSUER", "")
    return issuer

SERVERS = {
    "calendar": {"port": 3001, "name": "Calendar MCP Server", "description": "Manages calendar events and scheduling"},
    "documents": {"port": 3002, "name": "Documents MCP Server", "description": "File storage and document management"},
    "analytics": {"port": 3003, "name": "Analytics MCP Server", "description": "Usage metrics and reporting dashboard"},
}


# --- Token Verifier (validates Duo-issued JWTs) ---

class DuoTokenVerifier(TokenVerifier):
    """Verify Bearer tokens issued by Duo SSO.
    For demo purposes, does basic JWT structure check and expiry validation.
    Production would verify signature against Duo's JWKS.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None

            def pad(s):
                return s + "=" * (4 - len(s) % 4)

            payload = json.loads(base64.urlsafe_b64decode(pad(parts[1])))

            # Check it has expected claims
            if not payload.get("sub") or not payload.get("iss"):
                return None

            # For demo: accept any well-formed JWT from the configured issuer
            # Production: verify signature against JWKS, check exp, aud, etc.
            import time
            exp = payload.get("exp", 0)
            if exp and exp < time.time():
                return None

            return AccessToken(
                token=token,
                client_id=payload.get("aud", ""),
                scopes=payload.get("scope", "openid").split(),
            )
        except Exception:
            return None


# --- Server factory ---

def create_server(server_id: str) -> FastMCP:
    """Create an MCP server with OAuth auth gate for the given identity."""
    config = SERVERS[server_id]
    port = config["port"]
    issuer = get_issuer(server_id)

    if not issuer:
        print(f"  WARNING: No issuer configured for '{server_id}'.")
        print(f"  Edit config.json or set DUO_SSO_ISSUER env var.")

    auth_settings = AuthSettings(
        issuer_url=issuer or "https://example.com",
        resource_server_url=f"http://localhost:{port}",
        required_scopes=["openid"],
    )

    mcp = FastMCP(
        config["name"],
        host="127.0.0.1",
        port=port,
        auth=auth_settings,
        token_verifier=DuoTokenVerifier(),
    )

    # --- Register tools based on server type ---
    if server_id == "calendar":
        _register_calendar_tools(mcp)
    elif server_id == "documents":
        _register_documents_tools(mcp)
    elif server_id == "analytics":
        _register_analytics_tools(mcp)

    return mcp


# --- Calendar tools ---

def _register_calendar_tools(mcp: FastMCP):
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
        return json.dumps({"date": date, "time": time, "available": len(conflicts) == 0, "conflicts": conflicts}, indent=2)


# --- Documents tools ---

def _register_documents_tools(mcp: FastMCP):
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


# --- Analytics tools ---

def _register_analytics_tools(mcp: FastMCP):
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


# --- Run ---

def run_server(server_id: str):
    """Run a single MCP server."""
    config = SERVERS[server_id]
    issuer = get_issuer(server_id)
    mcp = create_server(server_id)
    print(f"  {config['name']} listening on http://localhost:{config['port']}/mcp")
    print(f"  Auth issuer: {issuer or 'NOT CONFIGURED'}")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MCP servers with Duo SSO auth")
    parser.add_argument("--server", choices=SERVERS.keys(), help="Run a single server")
    parser.add_argument("--all", action="store_true", help="Run all 3 servers")
    parser.add_argument("--port", type=int, help="Override port (single server only)")
    args = parser.parse_args()

    cfg = load_config()
    any_configured = any(cfg.get(s, {}).get("issuer") for s in SERVERS)
    if not any_configured and not os.environ.get("DUO_SSO_ISSUER"):
        print("\n  WARNING: No issuers configured!")
        print("  Edit config.json or set DUO_SSO_ISSUER env var.\n")

    if args.all:
        print(f"\n  Starting all MCP servers...")
        print(f"  Config: {CONFIG_PATH}\n")
        processes = []
        for sid in SERVERS:
            p = multiprocessing.Process(target=run_server, args=(sid,))
            p.start()
            processes.append(p)
        try:
            for p in processes:
                p.join()
        except KeyboardInterrupt:
            for p in processes:
                p.terminate()
    elif args.server:
        if args.port:
            SERVERS[args.server]["port"] = args.port
        print(f"\n  Starting {SERVERS[args.server]['name']}...")
        run_server(args.server)
    else:
        parser.print_help()
