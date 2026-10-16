# mp-mcp

A remote [MCP](https://modelcontextprotocol.io) server in Python, deployed to AWS Lambda at
roughly $0/month. It speaks **Streamable HTTP** in stateless mode, so any invocation can serve
any request — no sessions, no in-memory state.

Designed against [`specs/init/SPEC.md`](specs/init/SPEC.md). Tool definitions (spec Section 11)
are still TBD; the server currently exposes a single `ping` placeholder.

## How it fits together

```
MCP client ──HTTPS──▶ Lambda Function URL (AuthType: NONE)
                          │
                          ▼
                    Lambda Web Adapter  ──▶ uvicorn ──▶ Starlette app
                        (extension)                       ├─ CORS
                                                          ├─ access log
                                                          ├─ bearer-token auth (401 first)
                                                          └─ MCPServer  (/mcp, stateless)
```

| Concern | Choice |
|---|---|
| Compute | Lambda, container image, **arm64**, 512 MB, 30 s (spec §2) |
| Ingress | Function URL (`AuthType: NONE`) — no API Gateway (FR1, SR1) |
| HTTP bridge | [Lambda Web Adapter](https://github.com/aws/aws-lambda-web-adapter) 1.1.0 |
| Transport | Streamable HTTP, `stateless_http=True`, `json_response=True` (FR3) |
| Auth | `Authorization: Bearer <token>` checked in ASGI middleware, constant time (SR2) |
| Secrets | SSM Parameter Store SecureString, fetched once per cold start (SR3, SR5) |
| IaC | AWS SAM (`template.yaml`) |
| CI/CD | GitHub Actions + OIDC, no long-lived AWS keys (spec §8) |

The bearer token is the security boundary: the Function URL is public by necessity, because MCP
clients cannot sign SigV4 requests.

## Layout

```
src/mp_mcp/
  asgi.py         # `app = create_app()` — the cold start
  server.py       # MCPServer, tools, /health, create_app()
  middleware.py   # BearerAuthMiddleware, AccessLogMiddleware
  config.py       # Settings from environment variables
  secrets.py      # SSM lookups, cached per process
tests/            # HTTP-level tests, no AWS calls
template.yaml     # SAM: function, Function URL, IAM, log group, budget
Dockerfile        # arm64 image: python:3.12-slim + uv + Web Adapter
```

The spec proposed an `app/` directory; this repo keeps the pre-existing `src/mp_mcp` layout
because the `uv_build` backend and `mp-mcp` console script already assume it.

## Local development

```bash
uv sync --all-groups
uv run pytest                       # HTTP-level tests, offline
uv run ruff check . && uv run ruff format --check .
```

Run it locally against real AWS secrets (needs `ssm:GetParameter` on the two parameters):

```bash
AWS_PROFILE=personal-dev uv run mp-mcp      # serves http://0.0.0.0:8080/mcp
```

Everything is configured through environment variables: `SSM_AUTH_TOKEN_PARAM`,
`SSM_ANTHROPIC_KEY_PARAM`, `ALLOWED_HOSTS`, `ALLOWED_ORIGINS`, `PORT`/`AWS_LWA_PORT`.

`ALLOWED_HOSTS` controls DNS-rebinding protection:

| Value | Effect |
|---|---|
| unset | `localhost,127.0.0.1`, protection **on** (local dev) |
| `*` | protection **off** — what the stack ships, since the Function URL hostname only exists after deploy |
| `host1,host2` | exact allowlist, protection **on** (recommended hardening) |

## First-time AWS setup

1. **Bootstrap the two secrets** (values never enter git or env vars):

   ```bash
   aws ssm put-parameter --name /mcp-server/auth-token \
     --type SecureString --value "$(openssl rand -hex 32)" --profile personal-dev
   aws ssm put-parameter --name /mcp-server/anthropic-api-key \
     --type SecureString --value "sk-ant-..." --profile personal-dev
   ```

2. **First deploy by hand**, which also creates the ECR repository:

   ```bash
   sam build && sam deploy --guided --region us-east-2 --profile personal-dev
   ```

   Builds target arm64. On an x86 machine that needs QEMU (`docker run --privileged --rm
   tonistiigi/binfmt --install arm64`), or build on an arm64 host.

3. **CI from then on.** Create a GitHub OIDC identity provider and a deploy role whose trust
   policy is scoped to this repo and `main`, then store its ARN as the `AWS_ROLE_ARN` repository
   secret. Optionally set the `BUDGET_NOTIFICATION_EMAIL` repository variable for the cost alert.

## Connecting a client

```
https://<url-id>.lambda-url.us-east-2.on.aws/mcp
Authorization: Bearer <token>
```

Quick check:

```bash
# 401 without a token (acceptance criterion 1)
curl -i -X POST https://<url-id>.lambda-url.us-east-2.on.aws/mcp

# tools/list with one
curl -s -X POST https://<url-id>.lambda-url.us-east-2.on.aws/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

For MCP Inspector or a client without header support, use a proxy that injects the header.

## Deploying a change

Push to `main`: the workflow lints, tests, then `sam build` + `sam deploy`. To harden the Host
allowlist afterwards, redeploy with `AllowedHosts=<host>` from the `McpFunctionUrlHost` output.

## Cost notes

Lambda free tier, a free Function URL, and standard-tier SSM parameters keep this at ~$0 for low
traffic. There is no NAT gateway, no API Gateway, and no Secrets Manager. Log retention is 14
days so CloudWatch cannot grow unbounded. The optional budget alerts at 80% of a $5 monthly limit.
