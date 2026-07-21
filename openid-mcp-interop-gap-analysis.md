# OpenID MCP Security Interop: Duo Readiness & Gap Analysis

**Date:** 2026-07-20  
**Event:** OpenID Foundation AIIM CG — MCP-Based AI Agent Security Interoperability  
**Commitment Deadline:** August 10, 2026  
**Demo Deadline:** October 16, 2026  
**Presentation:** December 2026 — Gartner IAM Summit, Las Vegas

---

## TL;DR

Duo is well-positioned for the OpenID MCP Security Interop. We already have production implementations of **RFC 8693 Token Exchange** and **RFC 9728 CIMD** — two of the three core protocol building blocks. The remaining gaps are:

1. **JWT Bearer grant type** — accept externally-issued ID-JAGs as an authorization grant
2. **ID-JAG token minting** — extend our token exchange to issue the new ID-JAG token type
3. **External JWKS validation** — validate partner IdP signatures (currently we only validate Duo-issued tokens via Redis)
4. Two small metadata/config changes (EMA declaration + discovery fields)

Estimated effort: **~20–28 issues across 2–3 sprints (4–6 weeks)** with a dedicated team, based on prior Token Exchange and CIMD delivery velocity. Feasible for the Oct 16 cross-partner demo deadline if we commit resources by Aug 10.

**Recommended roles:** Enterprise IdP + OAuth Authorization Server + MCP Gateway — plays to our existing strengths.

---

## 1. Event Overview

The OpenID Foundation's AI Identity Management Community Group (AIIM CG) is running a cross-vendor interoperability event to prove that **MCP flows can be secured with open identity standards**. Participants implement at least one role and complete at least one cross-partner test.

**Call for Participation:** https://openid.net/call-for-participation-demonstrate-mcp-based-ai-agent-security-with-open-identity-standards-2/

### Roles (must implement at least one)

- MCP Client
- OpenID Provider
- OAuth Authorization Server
- MCP Gateway
- MCP Server

### Use Cases Under Test

1. **Agent governance** — restricting enterprise resource access to authorized agents only
2. **Cross-organizational identity assurance** — agents accessing MCP servers across org boundaries

### Required Protocol Flow

```
1. Client obtains OAuth 2.1 token via CIMD (RFC 9728)
2. Client accesses internal MCP server
3. Client exchanges token for ID-JAG (Identity Assertion JWT Authorization Grant)
4. Client exchanges ID-JAG with third-party enterprise's OAuth AS
5. Client communicates with external MCP server using obtained token
```

---

## 2. Relevant Specifications

| Spec | Role in Flow | Link |
|------|-------------|------|
| OAuth 2.1 | Foundation | https://datatracker.ietf.org/doc/draft-ietf-oauth-v2-1/ |
| RFC 9728 — Client ID Metadata Document (CIMD) | Client self-identification without pre-registration | https://datatracker.ietf.org/doc/rfc9728/ |
| RFC 8693 — Token Exchange | Subject token → ID-JAG exchange at IdP | https://datatracker.ietf.org/doc/rfc8693/ |
| draft-ietf-oauth-identity-assertion-authz-grant-04 (ID-JAG) | Cross-org identity assertion | https://datatracker.ietf.org/doc/draft-ietf-oauth-identity-assertion-authz-grant/ |
| RFC 7523 — JWT Bearer Grant | Presenting ID-JAG to Resource AS | https://datatracker.ietf.org/doc/rfc7523/ |
| MCP Enterprise Managed Authorization (EMA) | MCP extension declaring enterprise auth flow | https://modelcontextprotocol.io/extensions/auth/enterprise-managed-authorization |

### ID-JAG Protocol Summary (draft-04)

The Identity Assertion JWT Authorization Grant enables cross-domain API access by leveraging existing SSO trust:

1. **User authenticates** to MCP Client via enterprise IdP (OIDC/SAML) → receives ID Token
2. **Token Exchange at IdP** — Client exchanges ID Token for an ID-JAG:
   - `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`
   - `requested_token_type=urn:ietf:params:oauth:token-type:id-jag`
   - `audience=<Resource AS identifier>`
   - `subject_token=<ID Token>`
3. **ID-JAG redemption at Resource AS** — Client presents ID-JAG using JWT Bearer grant:
   - `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`
   - `assertion=<ID-JAG JWT>`
4. **Resource AS validates** — checks JWT type (`oauth-id-jag+jwt`), verifies signature via IdP's JWKS, validates audience/issuer/expiration, maps claims → issues access token

**ID-JAG Required Claims:** `iss`, `sub`, `aud`, `client_id`, `jti`, `exp`, `iat`  
**Optional Claims:** `scope`, `resource`, `authorization_details`, `email`, `auth_time`, `acr`, `amr`, `act`, `tenant`

---

## 3. What Duo Has Today

### 3.1 RFC 8693 Token Exchange — Complete

**Core implementation (~815 lines):**
- `lib-python-oidc/duo_oidc/token_exchange.py` — Subject token validation, actor tokens, audience resolution, delegation chains, scope resolution, token issuance
- `lib-python-oidc/duo_oidc/constants.py` — `TOKEN_EXCHANGE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:token-exchange"` + all Section 3 token type URIs

**Grant dispatch:**
- `ssoserv/web/oidc/hosted_oauth_server.py` (line 566) — Routes token-exchange grant type to handler

**Policy engine (DB-backed rules):**
- `lib-python-cloudsso/duo_cloudsso/db/token_exchange_rules.py` — CRUD
- `lib-python-cloudsso/duo_cloudsso/db/token_exchange_rule_lookup.py` — Runtime resolution (source AS, target AS, requesting client)
- `lib-python-cloudsso/duo_cloudsso/db/token_exchange_targets.py` — Target app config
- `lib-python-cloudsso/duo_cloudsso/db/token_exchange_target_scopes.py` — Per-target scope restrictions
- `cloudsso/schema/schema_up_175_create_token_exchange_tables.py` — DB schema

**Feature flags:**
- `Feature.TOKEN_EXCHANGE` (flag 158)
- `Feature.MAX_TOKEN_EXCHANGE_DEPTH` (flag 159, default 3)
- `Feature.TOKEN_EXCHANGE_RATE_LIMIT` (flag ~165)

**Admin API:**
- `adminapi-evergreen/adminapi_evergreen/handlers/cloudsso/sso_token_exchange_rules.py`
- `adminapi-evergreen/adminapi_evergreen/services/cloudsso/sso_token_exchange_rule_service.py`
- REST: `GET /cloudsso/token-exchange-rules`, `POST /cloudsso/token-exchange-rule`, update/delete

**Client SDK:**
- `third-party/duo-oauth-client-0.3.0/src/duo_oauth_client/_grants/token_exchange.py`
- `third-party/duo-oauth-client-0.3.0/src/duo_oauth_client/exchange.py` — `async_exchange_token()` / `exchange_token()`

**Tests:**
- `ssoserv/itest_ssoserv/test_web/test_oauth_server/test_token_exchange.py`
- `frontend_testing/cloudsso_test_service/tests/oidc/test_token_exchange.py`

---

### 3.2 RFC 9728 CIMD — Complete, Production, Default ON

**Metadata download + validation:**
- `lib-python-cloudsso/duo_cloudsso/services/oauth_cimd_metadata_service.py`
  - `download_cimd()` (line 27) — HTTPS fetch, SSRF checks, 5KB max, JSON validation, client_id match (line 129)
  - `OAuthCIMDMetadataService` (line 148) — Redis cache, 1-day TTL

**Data model:**
- `lib-python-cloudsso/duo_cloudsso/models.py` (line 133): `CIMDData(client_id, client_name, redirect_uris)`
- `lib-python-oidc/duo_oidc/models.py` (line 51-54): `ClientRegistrationMethod` enum with `CIMD` variant

**OAuth server integration:**
- `ssoserv/web/oidc/hosted_oauth_server.py` (line 366-377) — Detects URL-based client_id, routes to `CIMDClientService`
- `ssoserv/web/oidc/adapters.py` (line 2372) — `CIMDClientService(OAuthClientService)`: downloads metadata, sets redirect_uris/client_name, publishes activity logs
- `ssoserv/web/oidc/adapters.py` (line 2551) — `OAuthRPServiceFactory`: routes to CIMD service when client_id is URL

**URL detection:**
- `lib-python-oidc/duo_oidc/base_util.py` (line 25): `is_url()` helper
- Models expose `client_id_is_url` property (line 554, 666, 996)

**Discovery advertisement:**
- `lib-python-oidc/duo_oidc/models.py` (line 1685): `client_id_metadata_document_supported: bool`

**Feature flag:**
- `lib-python-cloudsso/duo_cloudsso/enums/features.py` (line 1223): `ENABLE_OAUTH_CIMD = feature_definition(156, ..., default=True)`

**Database:**
- `cloudsso/schema/schema_up_166_oauth_server_cimd_flag.py` — `is_cimd_enabled` column on `oauth_servers`
- `cloudsso/schema/schema_up_170_create_oauth_servers_cimd_clients.py` — `oauth_servers_cimd_clients` table
- `main/schema/schema_up_1471.py` (line 81) — `cimd_client_uris` table for agent classes
- `main/schema/schema_up_1480.py` — `client_id` expanded to `varchar(2048)` for CIMD URIs

**Agent provisioning integration:**
- `adminapi-evergreen/openapi/agent-provisioning.yaml` — CIMD URIs as first-class in Agent Classes API
- `admin-ui/src/views/AIAgents/components/CIMDUrlList/cimdUtils.ts` — Frontend validation (HTTPS, 512 chars, max 10 URIs)
- `lib-python/duo/db/agent_classes.py` — DB layer for `cimd_client_uris`

**Config/constants:**
- `lib-python-cloudsso/duo_cloudsso/consts.py` (lines 23-56) — Error messages, 1s timeout, 5KB max, 1-day Redis TTL

---

### 3.3 MCP Gateway & Authorization

- `adminserv/sso/oauth_server_configs/mcp.py` — MCP OAuth server integration type (client_credentials default)
- `adminapi-evergreen/adminapi_evergreen/handlers/mcp_gateway_metadata.py` — Admin API for MCP server/tool/prompt/resource listing
- `lib-python-common-fgp/duo_common_fgp/mcp_metadata/openmcp_gateway_metadata_interface.py` — External gateway communication
- `ssoserv/web/oidc/hosted_oauth_server.py` (lines 514-557) — CORS for `MCP-Protocol-Version` header
- `ZT-authz-bridge/` — Envoy ext_authz gRPC bridge for per-tool authorization decisions
- `frontend_testing/docs/cheatsheets/authz-mcp-tests.md` — MCP authorization test suite

---

### 3.4 OAuth AS Grant Types Supported

| Grant Type | Status |
|---|---|
| `authorization_code` | ✅ |
| `client_credentials` | ✅ |
| `refresh_token` | ✅ |
| `urn:ietf:params:oauth:grant-type:token-exchange` (RFC 8693) | ✅ Feature-flagged |
| `urn:ietf:params:oauth:grant-type:device_code` (RFC 8628) | ✅ Feature-flagged |
| `urn:ietf:params:oauth:grant-type:jwt-bearer` (RFC 7523) | ❌ Not implemented |

**Note:** `jwt-bearer` exists only as `CLIENT_ASSERTION_TYPE` for client authentication — not as a standalone grant type.

---

## 4. Gaps

### Gap 1: JWT Bearer Grant Type (RFC 7523) — Accept ID-JAG as Authorization Grant

**What:** Add `urn:ietf:params:oauth:grant-type:jwt-bearer` as a grant type in the OAuth AS token endpoint. When a partner's MCP client presents an ID-JAG, Duo validates it and issues an access token.

**Why:** The ID-JAG spec (draft-04, Section 5) requires the Resource AS to accept ID-JAGs via the JWT Bearer grant. This is how the cross-org exchange completes.

**Spec reference:** RFC 7523 Section 2.1 + draft-ietf-oauth-identity-assertion-authz-grant-04 Section 5

**Where to implement:**
- New grant handler in `ssoserv/web/oidc/hosted_oauth_server.py` (alongside existing grant dispatch at line 566)
- Validation logic: check JWT `typ` header = `oauth-id-jag+jwt`, verify `aud` matches Duo's issuer, validate `client_id`, enforce `exp`/`iat`

**Request format:**
```
POST /oauth/v1/token
grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
&assertion=<ID-JAG JWT>
&client_id=<client identifier>
&scope=<requested scopes>
```

---

### Gap 2: ID-JAG Token Issuance (IdP Role)

**What:** Extend the existing token exchange endpoint to mint ID-JAG tokens when `requested_token_type=urn:ietf:params:oauth:token-type:id-jag`.

**Why:** As the enterprise IdP, Duo must issue ID-JAGs that partner Resource AS instances can validate. This is the "identity chaining" step — user authenticates to Duo, Duo issues a scoped assertion the user's agent can present elsewhere.

**Spec reference:** draft-ietf-oauth-identity-assertion-authz-grant-04 Section 4

**Where to implement:**
- Extend `lib-python-oidc/duo_oidc/token_exchange.py` — add `requested_token_type` handling for `urn:ietf:params:oauth:token-type:id-jag`
- Add constant to `lib-python-oidc/duo_oidc/constants.py`: `ID_JAG_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:id-jag"`
- Mint JWT with `typ: oauth-id-jag+jwt` header and required claims (iss, sub, aud, client_id, jti, exp, iat) + optional (scope, resource, email)
- Policy evaluation: existing token exchange rules engine can gate which audiences an ID-JAG may be issued for

**Token Exchange Request:**
```
POST /oauth/v1/token
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&requested_token_type=urn:ietf:params:oauth:token-type:id-jag
&audience=https://partner-resource-as.example.com/
&subject_token=<ID Token or Refresh Token>
&subject_token_type=urn:ietf:params:oauth:token-type:id_token
&scope=mcp.tools.read
```

**Response:**
```json
{
  "issued_token_type": "urn:ietf:params:oauth:token-type:id-jag",
  "access_token": "<signed ID-JAG JWT>",
  "token_type": "N_A",
  "expires_in": 300
}
```

---

### Gap 3: External JWKS Validation (Trust External IdPs)

**What:** When Duo acts as the Resource AS (accepting an ID-JAG from a partner's IdP), it must validate the JWT signature against the partner IdP's JWKS endpoint — not via Redis lookup.

**Why:** Today, token exchange validates subject tokens by looking them up in Redis (they must be Duo-issued). For cross-org interop, Duo must trust externally-signed tokens from partner IdPs.

**Spec reference:** draft-ietf-oauth-identity-assertion-authz-grant-04 Section 5.2 (Processing Rules)

**Where to implement:**
- New service: external JWKS fetch + cache (similar pattern to `oauth_cimd_metadata_service.py`)
- Trust configuration: DB table mapping `issuer` → `jwks_uri` + allowed audiences + claim mapping rules
- Integration point: the new jwt-bearer grant handler (Gap 1) calls this service to validate the incoming ID-JAG signature
- Reuse patterns from CIMD implementation (HTTPS fetch, response validation, Redis cache)

**Validation steps per spec:**
1. Verify `typ` header = `oauth-id-jag+jwt`
2. Resolve issuer (`iss`) → JWKS URI from trust config
3. Fetch JWKS, verify JWT signature
4. Check `aud` matches Duo's AS issuer identifier
5. Validate `exp`, `iat`, `jti` (replay protection)
6. Map `sub` + claims → local user identity
7. Issue scoped access token

---

### Gap 4: EMA Extension Declaration in MCP

**What:** Duo's MCP server/gateway must declare support for `io.modelcontextprotocol/enterprise-managed-authorization` in its capabilities response.

**Why:** MCP clients need to discover that enterprise-managed auth is required (rather than per-user consent flows).

**Spec reference:** https://modelcontextprotocol.io/extensions/auth/enterprise-managed-authorization

**Where to implement:**
- MCP gateway configuration / metadata response
- Add extension to `initialize` response capabilities

**Effort:** Trivial — config/metadata only, no protocol logic.

---

### Gap 5: OAuth AS Metadata Advertisement

**What:** Advertise ID-JAG support in `.well-known/openid-configuration`:
- `identity_chaining_requested_token_types_supported`: `["urn:ietf:params:oauth:token-type:id-jag"]`
- `authorization_grant_profiles_supported`: `["urn:ietf:params:oauth:grant-profile:id-jag"]`
- `grant_types_supported`: add `urn:ietf:params:oauth:grant-type:jwt-bearer`

**Spec reference:** draft-ietf-oauth-identity-assertion-authz-grant-04 Section 7 (Metadata)

**Where to implement:**
- `lib-python-oidc/duo_oidc/models.py` — Add fields to discovery metadata model (near line 1685 where `client_id_metadata_document_supported` lives)

**Effort:** Low — model field additions + conditional inclusion in discovery response.

---

## 5. Recommended Interop Posture

### Roles Duo Should Play

| Role | Justification |
|------|------|
| **OpenID Provider / Enterprise IdP** | Duo IS the enterprise IdP — strongest position |
| **OAuth Authorization Server** | Token exchange + policy engine already built |
| **MCP Gateway** | ext_authz bridge + gateway metadata already built |

### Demo Scenario

```
┌─────────────┐     ┌──────────────┐     ┌────────────────────┐     ┌──────────────────┐
│  MCP Client │     │   Duo (IdP)  │     │ Partner Resource AS │     │ Partner MCP Srv  │
│  (Partner)  │     │              │     │                    │     │                  │
└──────┬──────┘     └──────┬───────┘     └─────────┬──────────┘     └────────┬─────────┘
       │                   │                       │                          │
       │──── SSO Login ───►│                       │                          │
       │◄── ID Token ──────│                       │                          │
       │                   │                       │                          │
       │── Token Exchange ─►│ (req_type=id-jag,    │                          │
       │   (subject=ID Tok) │  aud=Partner AS)     │                          │
       │◄── ID-JAG JWT ────│                       │                          │
       │                   │                       │                          │
       │───────────────── jwt-bearer grant ───────►│                          │
       │                   │  (assertion=ID-JAG)   │                          │
       │◄──────────────── Access Token ────────────│                          │
       │                   │                       │                          │
       │────────────────── MCP Request ───────────────────────────────────────►│
       │◄───────────────── MCP Response ──────────────────────────────────────│
```

**Duo also demonstrates the reverse:** Partner's IdP issues ID-JAG → presented to Duo's AS → Duo validates via JWKS → issues token → agent accesses Duo-protected MCP tools.

---

## 6. Implementation Effort Estimate

This is a **test/interop demo**, not customer-facing GA. Scope accordingly.

### Sizing Methodology

Estimates are based on observed delivery velocity from prior Token Exchange and CIMD (RFC 9728) implementation work — similar in complexity, touching the same codebase layers (OAuth AS, token issuance, external metadata fetch/cache, feature flags, discovery metadata). The team delivered those features at a rate of **15–20 issues per 2-week sprint** during focused execution.

### Effort Sizing by Analogy

| Gap | Comparable Prior Work | Estimated Issues | Sprints |
|-----|----------------------|-----------------|---------|
| **Gap 2: ID-JAG issuance** | Similar scope to CIMD metadata service implementation (service + cache + constants + feature flag + tests) | **6–10 issues** | 1 sprint |
| **Gap 1+3: JWT Bearer grant + external JWKS** | Similar scope to Token Exchange grant handler + CIMD fetch/validation service combined (new grant type + external trust validation path) | **12–16 issues** | 1.5–2 sprints |
| **Gap 5: AS metadata** | Similar to adding `client_id_metadata_document_supported` to discovery | **1–2 issues** | < 1 day |
| **Gap 4: EMA declaration** | Config/metadata only | **1 issue** | < 1 day |

**Total: ~20–28 issues**

### Timeline Projection

| Scenario | Sprints Required | Calendar Time | Oct 16 Feasible? |
|----------|-----------------|---------------|------------------|
| **Dedicated team (2–3 engineers)** | 2–3 sprints | 4–6 weeks | ✅ Yes — starts Aug, lands mid-Sept |
| **Shared with other priorities** | 4–5 sprints | 8–10 weeks | ⚠️ Tight — needs immediate start |
| **Single engineer, interop-only scope** | 3–4 sprints | 6–8 weeks | ⚠️ Possible if started immediately |

### Breakdown (Recommended Sprint Plan)

**Sprint 1 (2 weeks) — Foundation:**
- Add `ID_JAG_TOKEN_TYPE` constant + feature flag (1 issue)
- Implement ID-JAG JWT minting in token exchange handler (2–3 issues)
- Add ID-JAG metadata fields to discovery model (1 issue)
- Unit tests for ID-JAG issuance (1–2 issues)
- **Exit criteria:** Duo can issue ID-JAGs for configured audiences

**Sprint 2 (2 weeks) — External Trust:**
- External JWKS fetch + cache service (2–3 issues, pattern from CIMD service)
- Issuer → JWKS trust configuration (DB schema + admin config) (2–3 issues)
- JWT Bearer grant type handler in hosted_oauth_server.py (2–3 issues)
- Integration tests (1–2 issues)
- **Exit criteria:** Duo can accept externally-signed ID-JAGs and issue access tokens

**Sprint 3 (1 week, buffer/polish) — Interop Readiness:**
- EMA extension declaration on MCP gateway (1 issue)
- End-to-end test with mock partner (1–2 issues)
- Partner coordination / JWKS endpoint exchange (non-engineering)
- **Exit criteria:** Ready for cross-partner test

### Risk Factors

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Team bandwidth — current priorities may compete | No dedicated capacity for interop work | Interop is ~20–28 issues total — carve out 1–2 engineers |
| Partner coordination delays | Can't test cross-org without a partner | Start partner outreach at commitment (Aug 10), not at code-complete |
| External JWKS validation is net-new pattern | Higher risk of unknowns | Reuse CIMD service patterns (HTTPS fetch, Redis cache, timeout handling) |
| Token exchange codebase familiarity | Engineers may need ramp-up time | Architecture is well-structured; existing tests + CIMD patterns provide strong reference |

**Feature flag strategy:** Gate all behind `Feature.ID_JAG_GRANT` (off by default). Enable only for interop test accounts.

---

## 7. What Does NOT Need to Change

- Token exchange policy engine — already handles audience/scope/client rules
- CIMD (RFC 9728) — already production, default on
- MCP gateway — works as-is, just needs EMA metadata
- Delegation chain tracking — `act` claim already implemented
- Admin API for exchange rules — existing CRUD covers new use case
- CORS / MCP-Protocol-Version — already handled
- Agent classes / CIMD URI management — already built

---

## 8. Open Questions

1. **Partner identification** — Which other participants will Duo test against? CrowdStrike (co-chair) is likely. Need to coordinate JWKS endpoints and audience values.
2. **Scope of demo** — Internal-only MCP access (use case 1) vs. cross-org (use case 2)? Recommend both since gaps 1-3 enable both scenarios.
3. **Shared AS design** — The existing `PROJECT_PLAN.md` for Shared OAuth Server + DAG already envisions CIMD + dynamic clients. Should ID-JAG work land there or in the current per-customer AS?
4. **DPoP binding** — The ID-JAG spec supports proof-of-possession via `cnf` claim. Required for interop or optional?
5. **Commitment submission** — Who signs for Duo/Cisco? Need org commitment by Aug 10.
