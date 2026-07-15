"""Tests for MCP server health endpoints and portal status."""

import json
import subprocess
import time
import pytest
import requests


SERVERS = {
    "calendar": 3001,
    "documents": 3002,
    "analytics": 3003,
}
PORTAL_PORT = 8080


def _wait_for_port(port, timeout=10):
    """Wait until a port is responding."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"http://localhost:{port}/health", timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def running_servers():
    """Start all MCP servers for testing, stop them after."""
    proc = subprocess.Popen(
        [".venv/bin/python3", "servers.py", "--all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for port in SERVERS.values():
        assert _wait_for_port(port), f"Server on :{port} did not start"
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture(scope="module")
def running_portal():
    """Start the chatbot portal for testing."""
    proc = subprocess.Popen(
        [".venv/bin/python3", "app.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    start = time.time()
    while time.time() - start < 10:
        try:
            r = requests.get(f"http://localhost:{PORTAL_PORT}/", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


class TestHealthEndpoints:
    """Test /health endpoint on each MCP server."""

    def test_calendar_health(self, running_servers):
        r = requests.get("http://localhost:3001/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["port"] == 3001
        assert "server" in data
        assert "issuer_configured" in data
        assert "uptime_seconds" in data

    def test_documents_health(self, running_servers):
        r = requests.get("http://localhost:3002/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["port"] == 3002

    def test_analytics_health(self, running_servers):
        r = requests.get("http://localhost:3003/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["port"] == 3003

    def test_health_no_auth_required(self, running_servers):
        """Health endpoint should NOT require a Bearer token."""
        r = requests.get("http://localhost:3001/health")
        assert r.status_code == 200

    def test_mcp_requires_auth(self, running_servers):
        """MCP endpoint should return 401 without a token."""
        r = requests.get("http://localhost:3001/mcp")
        assert r.status_code == 401


class TestResourceMetadata:
    """Test RFC 9728 resource metadata endpoints."""

    def test_calendar_metadata(self, running_servers):
        r = requests.get("http://localhost:3001/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        data = r.json()
        assert "resource" in data
        assert "authorization_servers" in data

    def test_documents_metadata(self, running_servers):
        r = requests.get("http://localhost:3002/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        data = r.json()
        assert "resource" in data

    def test_analytics_metadata(self, running_servers):
        r = requests.get("http://localhost:3003/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        data = r.json()
        assert "resource" in data


class TestPortalStatus:
    """Test portal /status endpoint."""

    def test_status_returns_json(self, running_servers, running_portal):
        r = requests.get(f"http://localhost:{PORTAL_PORT}/status")
        assert r.status_code == 200
        data = r.json()
        assert "calendar" in data
        assert "documents" in data
        assert "analytics" in data

    def test_status_shows_servers_ok(self, running_servers, running_portal):
        r = requests.get(f"http://localhost:{PORTAL_PORT}/status")
        data = r.json()
        for sid in SERVERS:
            assert data[sid]["status"] == "ok"

    def test_portal_home(self, running_portal):
        r = requests.get(f"http://localhost:{PORTAL_PORT}/")
        assert r.status_code == 200
        assert "MCP Agent" in r.text

    def test_portal_config(self, running_portal):
        r = requests.get(f"http://localhost:{PORTAL_PORT}/config")
        assert r.status_code == 200
        assert "Settings" in r.text


class TestPreflightCheck:
    """Test the --check flag."""

    def test_check_exits_cleanly(self):
        result = subprocess.run(
            [".venv/bin/python3", "servers.py", "--check"],
            capture_output=True,
            text=True,
        )
        assert "Preflight check" in result.stdout
        assert "Calendar MCP Server" in result.stdout
        assert "Documents MCP Server" in result.stdout
        assert "Analytics MCP Server" in result.stdout

    def test_check_reports_issuer_status(self):
        result = subprocess.run(
            [".venv/bin/python3", "servers.py", "--check"],
            capture_output=True,
            text=True,
        )
        assert "issuer=" in result.stdout

    def test_check_reports_port_status(self):
        result = subprocess.run(
            [".venv/bin/python3", "servers.py", "--check"],
            capture_output=True,
            text=True,
        )
        assert "port=" in result.stdout
