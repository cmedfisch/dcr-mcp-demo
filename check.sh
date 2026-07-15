#!/usr/bin/env bash
# Verify the DCR demo stack is running and configured correctly.
# Usage: ./check.sh

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

PASS=0
FAIL=0

check() {
    local label="$1"
    local url="$2"
    local expect="$3"

    code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [ "$code" = "$expect" ]; then
        printf "  ${GREEN}✓${NC} %-45s %s\n" "$label" "$code"
        PASS=$((PASS + 1))
    else
        printf "  ${RED}✗${NC} %-45s %s (expected %s)\n" "$label" "$code" "$expect"
        FAIL=$((FAIL + 1))
    fi
}

check_json() {
    local label="$1"
    local url="$2"
    local key="$3"

    body=$(curl -s "$url" 2>/dev/null || echo "")
    if echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('$key')" 2>/dev/null; then
        printf "  ${GREEN}✓${NC} %-45s has '%s'\n" "$label" "$key"
        PASS=$((PASS + 1))
    else
        printf "  ${RED}✗${NC} %-45s missing '%s'\n" "$label" "$key"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "  DCR Demo — Stack Check"
echo "  ============================================"
echo ""

echo "  MCP Servers"
echo "  -----------"
check "Calendar health (:3001)"      "http://localhost:3001/health" "200"
check "Documents health (:3002)"     "http://localhost:3002/health" "200"
check "Analytics health (:3003)"     "http://localhost:3003/health" "200"
check "Calendar auth gate (:3001)"   "http://localhost:3001/mcp"    "401"
check "Documents auth gate (:3002)"  "http://localhost:3002/mcp"    "401"
check "Analytics auth gate (:3003)"  "http://localhost:3003/mcp"    "401"
echo ""

echo "  Resource Metadata (RFC 9728)"
echo "  ----------------------------"
check_json "Calendar resource metadata"  "http://localhost:3001/.well-known/oauth-protected-resource" "resource"
check_json "Documents resource metadata" "http://localhost:3002/.well-known/oauth-protected-resource" "resource"
check_json "Analytics resource metadata" "http://localhost:3003/.well-known/oauth-protected-resource" "resource"
echo ""

echo "  Chatbot Portal"
echo "  --------------"
check "Portal home (:8080)"          "http://localhost:8080/"       "200"
check "Portal config (:8080)"        "http://localhost:8080/config" "200"
check "Portal status (:8080)"        "http://localhost:8080/status" "200"
echo ""

echo "  Issuer Configuration"
echo "  --------------------"
for port in 3001 3002 3003; do
    body=$(curl -s "http://localhost:$port/health" 2>/dev/null || echo "{}")
    configured=$(echo "$body" | python3 -c "import sys,json; print(json.load(sys.stdin).get('issuer_configured', False))" 2>/dev/null || echo "False")
    if [ "$configured" = "True" ]; then
        printf "  ${GREEN}✓${NC} %-45s issuer configured\n" "Server :$port"
        PASS=$((PASS + 1))
    else
        printf "  ${YELLOW}!${NC} %-45s issuer NOT configured\n" "Server :$port"
        FAIL=$((FAIL + 1))
    fi
done
echo ""

echo "  ============================================"
printf "  Results: ${GREEN}%d passed${NC}" "$PASS"
if [ "$FAIL" -gt 0 ]; then
    printf ", ${RED}%d failed${NC}" "$FAIL"
fi
echo ""
echo ""

exit $FAIL
