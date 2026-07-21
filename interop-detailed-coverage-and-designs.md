# MCP Security Interop: Detailed Coverage Mapping & Implementation Designs

**Date:** 2026-07-20
**Companion to:** openid-mcp-interop-gap-analysis.md

---

## Part 1: Interop Matrix Coverage

The event defines three separate interop matrices. Each tests different aspects of the MCP+OAuth flow. Here is Duo's row-by-row coverage for each.

---

### CIMD Interoperability Matrix

**Duo's Role:** OAuth Authorization Server
**Partner Role:** MCP Client
**Test:** Can the OAuth AS accept CIMD-based clients and issue tokens via standard grants?

| Feature | Status | Code Location | Notes |
|---------|--------|---------------|-------|
| **Client ID Metadata** | | | |
| Pre-registered client | SUPPORTED | `duo_oidc/adapter.py:105-140`, `ssoserv/web/oidc/adapters.py:1766-1787` | All token requests require registered client_id. CIMD (RFC 9728 URL-based) and DCR (RFC 7591) also create registered entries. Feature-flagged: `ENABLE_OAUTH_CIMD`, `ENABLE_DCR_CLIENTS_IN_REDIS`. |
| `redirect_uris` support | SUPPORTED | `duo_oidc/util.py:2319-2450`, `duo_cloudsso/models.py:141` | Validates on /authorize. Supports exact, wildcard subdomain, loopback. CIMD clients get redirect_uris from metadata document. |
| `jwks_uri` support | NOT SUPPORTED | N/A | `_validate_client_assertion_auth` (adapter.py:196-249) uses `relying_party.client_secret` as HMAC key (HS512). No code fetches client public keys from a `jwks_uri`. |
| `jwks` (inline) support | NOT SUPPORTED | N/A | `CIMDData` model only has `client_id`, `client_name`, `redirect_uris`. No field for inline key material. |
| **Auth Code + PKCE** | | | |
| Client secret | SUPPORTED | `duo_oidc/adapter.py:105-140` | PKCE (S256 only) + client_secret for confidential clients. OAuth 2.1 clients require PKCE. Supports `client_secret_basic` and `client_secret_post`. |
| JWT (private_key_jwt) | NOT SUPPORTED | `duo_oidc/adapter.py:196-249` | Only `client_secret_jwt` (HS512 shared secret). No asymmetric key verification. Would need `jwks_uri`/`jwks` to verify client key. |
| MTLS | NOT SUPPORTED | N/A | No mTLS code. `ClientAuthMethod` enum only has SECRET_BASIC, SECRET_POST, SECRET_JWT, SECRET_NONE. |
| **Client Credentials** | | | |
| Client secret | SUPPORTED | `duo_oidc/util.py:1533-1598` | Requires `client_secret`. Validates via direct comparison. Per-client `client_credentials_enabled` flag. |
| JWT (private_key_jwt) | NOT SUPPORTED | `duo_oidc/util.py:1554` | Handler hard-requires `client_secret`, doesn't invoke general `authenticate_client_request`. |
| MTLS | NOT SUPPORTED | N/A | No mTLS implementation. |

**CIMD Matrix Qualification Status:**
- Need at least one "Client ID Metadata" row checked + one "Auth code with PKCE" or "Client credentials" row checked
- Duo qualifies: Pre-registered client + redirect_uris + Auth code with PKCE (client secret) + Client credentials (client secret)
- The `jwks_uri`/`jwks` and `private_key_jwt` rows are optional for qualification

---

### EMA Interoperability Matrix

**Duo's Role:** OpenID Provider (OP/IdP)
**Partner Roles:** MCP Client + Resource OAuth AS
**Test:** Can Duo issue ID-JAG tokens and can it accept them?

| Feature | Status | Evidence | Gap |
|---------|--------|----------|-----|
| **As OpenID Provider** | | | |
| Valid ID-JAG issuance | NOT SUPPORTED | `token_exchange.py:808-814` always returns access_token. `ALLOWED_REQUESTED_TOKEN_TYPES` = `{TOKEN_TYPE_URI_ACCESS_TOKEN}` only. No `oauth-id-jag+jwt` type anywhere. Signing always sets `typ: "JWT"`. | Must add id-jag token type, new model, branch in handler, custom typ header |
| `resource` parameter | SUPPORTED | `OAuthTokenExchangeRequest` accepts `resource`. Validation at `models_shared.py:376`. Handler resolves resource to RP via `get_relying_party_by_resource_uri`. | Fully implemented per RFC 8693. |
| `sub_id` support | NOT SUPPORTED | No sub_id structured claim (RFC 9493) in token exchange models. Only plain string `sub`. | Add sub_id as optional structured claim with format validation. |
| `scope` support | SUPPORTED | Token exchange accepts `scope`. `get_allowed_token_exchange_scopes` intersects requested with RP/rule/user scopes. | Fully implemented. |
| **As Resource OAuth AS** | | | |
| Accept jwt-bearer grant | NOT SUPPORTED | Grant dispatch in `web.py:566-648` has no case for `urn:ietf:params:oauth:grant-type:jwt-bearer`. | New grant type, handler, request model needed. |
| Validate external JWKS | NOT SUPPORTED | `JWTSigningService` only signs. `JWKSService` only serves Duo's keys. Subject token validation only looks up Redis (Duo-issued). | Need JWKS fetcher, cache, issuer trust registry. |

**EMA Matrix Qualification:**
- Need "Valid ID-JAG" row checked (as OP)
- This requires the ID-JAG issuance gap to be closed
- Sub_id is nice-to-have, not required for qualification

---

### OAuth Interoperability Matrix

**Duo's Role:** MCP Server (less natural fit) or MCP Client
**Partner Role:** MCP Client or MCP Server
**Test:** Basic OAuth 2.1 protected resource access

| Feature | Status | Evidence | Gap |
|---------|--------|----------|-----|
| OAuth Protected Resource Metadata (OPRM) | NOT SUPPORTED | No `.well-known/oauth-protected-resource`. Only `openid-configuration` and `oauth-authorization-server` routes exist. | Would need new endpoint per draft-ietf-oauth-resource-metadata. |
| `scope` in `WWW-Authenticate` | NOT SUPPORTED | No code sets `WWW-Authenticate` header anywhere. `InvalidAccessToken` returns 400, should be 401 with Bearer challenge per RFC 6750. | Modify error handling to return proper 401 + Bearer challenge with scope. |

**OAuth Matrix Relevance:**
- Less directly relevant - Duo is not an MCP Server.
- If Duo protects MCP Servers (as gateway/AS), those servers would need OPRM pointing to Duo.
- Low priority for interop qualification.

---

## Part 2: Implementation Designs

---

### Gap 1: RFC 7523 JWT Bearer Grant

**Purpose:** Accept externally-issued ID-JAG as an authorization grant and issue an access token.

#### Architecture

```
Token Endpoint POST /oauth2/{ikey}/token
    |
    v
OAuthTokenHandler.post() [hosted_oauth_server.py:432]
    |
    v
AbstractOAuthTokenHandler.handle() [web.py:531]
    |
    match grant_type:
        case "urn:ietf:params:oauth:grant-type:jwt-bearer":   <-- NEW
            |
            v
        jwt_bearer.handle_jwt_bearer_grant_request()          <-- NEW MODULE
            |
            +-- ExternalJWKSService.get_signing_key()         <-- NEW
            +-- JWTBearerService.validate_assertion_jti()     <-- NEW (reuses Redis pattern)
            +-- JWTBearerService.get_trusted_issuer_config()  <-- NEW (DB lookup)
            +-- util.create_access_token()                    <-- EXISTING
            +-- signing_service.sign()                        <-- EXISTING
            +-- access_token_service.set_access_token_record()<-- EXISTING
```

#### Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `lib-python-oidc/duo_oidc/constants.py` | Modify | Add `JWT_BEARER_GRANT_TYPE` constant |
| `lib-python-oidc/duo_oidc/models.py` | Modify | Add `JWTBearerGrantRequest` model |
| `lib-python-oidc/duo_oidc/jwt_bearer.py` | Create | Handler logic |
| `lib-python-oidc/duo_oidc/external_jwks.py` | Create | JWKS fetching + caching |
| `lib-python-oidc/duo_oidc/adapter.py` | Modify | Add `JWTBearerService` + `ExternalJWKSService` ABCs |
| `lib-python-oidc/duo_oidc/web.py` | Modify | Add case branch + abstract methods |
| `lib-python-oidc/duo_oidc/errors.py` | Modify | JWT Bearer-specific errors |
| `ssoserv/web/oidc/hosted_oauth_server.py` | Modify | Feature flag + service getters |
| `ssoserv/web/oidc/adapters.py` | Modify | Concrete service implementations |
| `lib-python-cloudsso/duo_cloudsso/enums/features.py` | Modify | `JWT_BEARER_GRANT` flag |

#### Request Model

```python
class JWTBearerGrantRequest(BaseOAuthRequest):
    grant_type: str         # urn:ietf:params:oauth:grant-type:jwt-bearer
    assertion: str          # The ID-JAG JWT
    scope: scope_type = frozenset()
    resource: tuple[ResourceUrl, ...] | None = None
    client_id: ClientID
    host: str
```

#### Handler Steps

1. Resolve client (relying party) from client_id
2. Verify RP has jwt_bearer grant enabled
3. Peek at assertion header to get kid, payload to get iss
4. Look up trusted issuer config
5. Fetch/cache external JWKS
6. Verify assertion signature
7. Validate claims (aud, exp, iat, jti, sub)
8. Check jti for replay (Redis, TTL = exp - now)
9. Resolve allowed scopes
10. Mint access token with `sub` from ID-JAG, `act.sub` = external issuer
11. Return token response

#### Security

| Concern | Mitigation |
|---------|-----------|
| Replay | Redis jti tracking with TTL (reuses `validate_client_assertion_jti` pattern) |
| Audience | `aud` must match Duo's issuer URL |
| Issuer allowlist | Only accept from pre-configured trusted issuers (DB) |
| Algorithm | Only RS256/ES256 per issuer; reject none/HS* |
| Key confusion | Fetch JWKS only from pre-configured jwks_uri, never from JWT |
| Clock skew | Configurable leeway (default 30s) |

#### Existing Code Reuse

| Existing | Reuse For |
|----------|-----------|
| `adapter.validate_client_assertion_jti()` | jti replay pattern |
| `generic_oauth._retrieve_jwks_info()` | JWKS fetch pattern |
| `duo_jwt.KeyRing.load_client_keys()` | JWK-to-key parsing |
| `util.create_access_token()` | Token construction |
| `web.py` match/case pattern | Grant dispatch integration |

#### Estimated Size: ~820 lines production + ~800 lines tests

---

### Gap 2: ID-JAG Token Issuance

**Purpose:** Extend token exchange to mint ID-JAG tokens when `requested_token_type=urn:ietf:params:oauth:token-type:id-jag`.

#### Current State

- Token exchange handler at `token_exchange.py:468` always issues access tokens
- `ALLOWED_REQUESTED_TOKEN_TYPES` = `frozenset({TOKEN_TYPE_URI_ACCESS_TOKEN})` (constants.py:142)
- Signing service hard-codes `"typ": "JWT"` (adapters.py:974)
- No jti on issued tokens (only DPoP proofs have jti)

#### ID-JAG JWT Structure

**Header:**
```json
{"alg": "RS256", "typ": "oauth-id-jag+jwt", "kid": "<duo-key-id>"}
```

**Required Claims:**
| Claim | Source |
|-------|--------|
| iss | Duo's issuer URL |
| sub | User from subject_token_record.auth_event.sub |
| aud | Target Resource AS (from request.audience/resource) |
| client_id | Requesting MCP client |
| jti | uuid4().hex |
| exp | iat + 300 (5 min, configurable) |
| iat | Current timestamp |

**Optional:** scope, resource, email, auth_time, acr, amr, act

#### Flow Changes

Branch in `handle_token_exchange_request` after rule resolution:

```python
if request.requested_token_type == constants.TOKEN_TYPE_URI_ID_JAG:
    return await _issue_id_jag(...)
else:
    # existing access token path (unchanged)
```

Key differences from access token path:
- ID-JAGs are NOT stored in Redis (stateless, verified by signature)
- `token_type` response = `N_A` (not Bearer)
- `issued_token_type` = `urn:ietf:params:oauth:token-type:id-jag`
- Audience can be an external URL (not just a Duo RP UUID)
- Short lifetime (5 min default)

#### Signing

Use existing `AsymKeychainSigningService.sign()` with the source OAuth Server's keys. Extend `sign()` to accept optional `headers_override` for the `typ` field.

Verifiers fetch Duo's existing JWKS endpoint to validate. No new endpoint needed.

#### Files to Modify

| File | Change |
|------|--------|
| `duo_oidc/constants.py` | Add `TOKEN_TYPE_URI_ID_JAG`, `ID_JAG_JWT_TYP`, `ID_JAG_EXPIRE_SECONDS`; update `ALLOWED_REQUESTED_TOKEN_TYPES` |
| `duo_oidc/models_v2.py` | Add `IdentityAssertionJWT` model |
| `duo_oidc/token_exchange.py` | Add `_issue_id_jag()`, branch on requested_token_type, adjust audience validation for external URLs |
| `duo_oidc/adapter.py` | Extend `JWTSigningService.sign()` with `headers_override` param |
| `duo_oidc/errors.py` | Add `IdJagIssuanceDisabled` |
| `ssoserv/web/oidc/adapters.py` | Update signing to respect typ override |
| `duo_cloudsso/enums/features.py` | Add `ID_JAG_ISSUANCE` flag |

#### New File

| File | Purpose |
|------|---------|
| `duo_oidc/id_jag.py` | Construction helpers, external audience validation, policy checks |

#### Sequence Diagram

```
MCP Client              Duo AS (IdP/OP)                 Resource AS (Partner)
    |                       |                                   |
    |--- Token Exchange --->|                                   |
    |  grant_type=token-exchange                                |
    |  subject_token=<access_token>                             |
    |  requested_token_type=id-jag                              |
    |  audience=https://partner-as/                             |
    |                       |                                   |
    |                       |-- Validate subject_token (Redis)  |
    |                       |-- Resolve exchange rule           |
    |                       |-- Build IdentityAssertionJWT      |
    |                       |   typ: oauth-id-jag+jwt           |
    |                       |-- Sign with Duo's key             |
    |                       |                                   |
    |<-- issued_token_type=id-jag                               |
    |  access_token=<signed-jwt>                                |
    |  token_type=N_A                                           |
    |                                                           |
    |--- JWT Bearer Grant ------------------------------------->|
    |  grant_type=jwt-bearer                                    |
    |  assertion=<ID-JAG>                                       |
    |                                                           |
    |                       (Partner fetches Duo's JWKS,        |
    |                        validates signature, maps user)    |
    |                                                           |
    |<-- access_token=<partner-scoped-token> -------------------|
```

#### Estimated Size: ~350 lines production + ~400 lines tests
#### Estimated Effort: 15-22 engineering days (3-4 weeks, 1 engineer)

---

### Gap 3: External JWKS Validation

**Purpose:** When Duo acts as Resource OAuth AS accepting jwt-bearer grants, validate the ID-JAG signature against the external issuer's public keys.

#### Existing Patterns in Codebase

| Pattern | Location | Reuse |
|---------|----------|-------|
| External JWKS fetch | `azureauthserv/lib/azure.py` - `get_azure_jwks()` | HTTP fetch + kid lookup pattern |
| JWK parsing | `duo_core/duo_jwt.py` - `KeyRing.load_client_keys()` | JWK dict to RSAKey |
| PyJWT verification | `sharedsignalsapi/.../signing.py` | `jwt.PyJWK` + `jwt.decode()` with kid |
| HTTPS fetch + cache | `oauth_cimd_metadata_service.py` | SSRFValidator + Redis TTL cache |
| Rate limiting | `duo_redis/ratelimiter.py` | Token-bucket for refetch limiting |
| SSRF protection | `duo_core/http_ssrf_validator.py` | Domain allowlisting, scheme/IP validation |

#### Class Design

```python
class ExternalJWKSService:
    """Fetches, caches, and resolves external JWKS keys."""

    async def get_signing_key(self, issuer: str, kid: str, alg: str, cid: int) -> RSAKey | ECKey:
        """
        1. Lookup trusted issuer by (issuer, cid)
        2. Check algorithm is permitted
        3. Get cached JWKS or fetch fresh
        4. Find key by kid
        5. On kid miss: re-fetch (rate-limited) then retry
        """

    async def get_cached_jwks(self, issuer: str, cid: int) -> CachedJWKS | None
    async def fetch_and_cache_jwks(self, trusted_issuer: TrustedIssuer) -> CachedJWKS


class JWTBearerValidationService:
    """Validates JWT-bearer assertions (ID-JAGs) from external IdPs."""

    async def validate_id_jag(self, assertion: str, expected_audience: str, cid: int) -> ValidatedIDJAG:
        """
        1. Decode header (unverified) for kid, alg
        2. Decode payload (unverified) for iss
        3. Verify iss in trusted registry
        4. Verify alg permitted
        5. Fetch signing key via ExternalJWKSService
        6. Verify signature
        7. Validate claims: exp, nbf, iat, aud
        8. Return validated claims
        """
```

#### Trusted Issuer Registry (DB)

```sql
CREATE TABLE trusted_issuers (
    trusted_issuer_id INT AUTO_INCREMENT PRIMARY KEY,
    cid INT NOT NULL,
    os_id INT NOT NULL,
    issuer VARCHAR(2048) NOT NULL,
    jwks_uri VARCHAR(2048) NOT NULL,
    allowed_algorithms JSON NOT NULL,   -- ["RS256", "ES256"]
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uq_cid_issuer (cid, issuer)
);
```

#### Caching Strategy

| Aspect | Design |
|--------|--------|
| Backend | Redis (consistent with CIMD service pattern) |
| Key format | `external_jwks:{cid}:{sha256(issuer)[:16]}` |
| TTL | 3600s (1 hour), configurable per issuer |
| Cache miss | Fetch from jwks_uri, store in Redis |
| kid miss | Re-fetch (rate-limited 10/min/issuer), retry once |
| Rate limit | `external_jwks_fetch_rate:{cid}:{issuer_hash}` |
| Stale-while-revalidate | On network error, serve stale cache if available |

#### Security

| Concern | Mitigation |
|---------|-----------|
| SSRF | `SSRFValidator(allow_private_ips=False, allowed_schemes=["https"])`. jwks_uri is admin-configured, not user-supplied. |
| Algorithm restriction | Per-issuer allowlist. Hard-reject `none`, all symmetric (HS*). Default: RS256, ES256. |
| Cache poisoning | JWKS fetched only from registered jwks_uri. Redis keys namespaced by cid for tenant isolation. |
| Key confusion | Enforce JWT header `alg` matches key's declared algorithm. |
| DoS | Rate limit refetches. Response size cap (50KB). Fetch timeout (5s). |

#### Files to Create

| File | Purpose |
|------|---------|
| `duo_cloudsso/services/external_jwks_service.py` | Core JWKS fetch, cache, resolve |
| `duo_cloudsso/db/trusted_issuers.py` | DB layer for issuer registry |
| `duo_cloudsso/services/jwt_bearer_validation_service.py` | Validation orchestrator |
| `cloudsso/schema/schema_up_XXX_create_trusted_issuers_table.py` | DB migration |

#### Files to Modify

| File | Change |
|------|--------|
| `duo_cloudsso/consts.py` | Redis keys, TTLs |
| `duo_cloudsso/models.py` | `TrustedIssuerConfig` model |
| `duo_core/duo_jwt.py` | Add EC key support (ES256) if needed |

#### Estimated Size: ~500 lines production + ~400 lines tests
#### Estimated Effort: 15-22 engineering days (3-4 weeks, 1 engineer)

---

## Part 3: Summary & Prioritization

### What Duo Can Demo Today (No Engineering)

For CIMD matrix qualification alone:
- Pre-registered client support
- redirect_uris validation
- Auth code + PKCE + client_secret
- Client credentials + client_secret
- Full RFC 9728 CIMD implementation

### What Requires Engineering

| Gap | Matrix | Effort | Priority |
|-----|--------|--------|----------|
| ID-JAG issuance | EMA (as OP) | M (3-4 weeks) | P0 - required for EMA qualification |
| JWT Bearer grant | EMA (as Resource AS) | L (3-4 weeks) | P1 - enables dual-role participation |
| External JWKS validation | EMA (as Resource AS) | M (3-4 weeks) | P1 - dependency of JWT Bearer |
| private_key_jwt support | CIMD | S (1-2 weeks) | P2 - nice-to-have for full CIMD coverage |
| sub_id claim | EMA | XS (days) | P2 - optional for qualification |
| OPRM endpoint | OAuth | S (1 week) | P3 - less relevant |
| WWW-Authenticate headers | OAuth | XS (days) | P3 - standards compliance |

### Recommended Phasing

**Phase 1 (Sprint 1-2): CIMD-only participation - ZERO engineering needed**
- Register with OpenID Foundation
- Deploy existing CIMD + OAuth AS
- Test with partner MCP Clients
- Qualify on CIMD matrix rows: pre-registered client, redirect_uris, auth code + PKCE (secret), client credentials (secret)

**Phase 2 (Sprint 2-4): EMA as OP**
- Implement ID-JAG issuance (Gap 2)
- Extends existing token exchange, reuses signing infra
- Partners present the ID-JAG to their Resource AS

**Phase 3 (Sprint 3-5): EMA as Resource AS**
- Implement External JWKS validation (Gap 3)
- Implement JWT Bearer grant (Gap 1)
- Accept partner-issued ID-JAGs
- Full bidirectional flow

### Total Estimated Effort

| Component | Lines (est.) | Days (est.) |
|-----------|-------------|-------------|
| JWT Bearer grant (Gap 1) | ~1,620 | 15-22 |
| ID-JAG issuance (Gap 2) | ~750 | 15-22 |
| External JWKS validation (Gap 3) | ~900 | 15-22 |
| **Total new code** | **~3,270** | **20-28 issues, 2-3 sprints** |

Note: Gaps 1 and 3 are tightly coupled (JWT Bearer requires External JWKS) and should be developed together. Gap 2 (ID-JAG issuance) is independent and can be parallelized.
