# MCP Server on AWS Lambda: Project Spec

Status: draft v1
Owner: Jorge

## 1. Goal

Build a remote MCP server in Python and deploy it to AWS at the lowest practical cost. It is reachable over HTTPS by MCP clients (Claude and others) using the Streamable HTTP transport.

## 2. Decisions

| Area | Decision |
|---|---|
| Hosting | AWS Lambda + Function URL (no API Gateway) |
| Language | Python 3.12 (must match the Lambda runtime) |
| Architecture | arm64 (about 20% cheaper than x86) |
| MCP transport | Streamable HTTP, **stateless** mode, JSON responses |
| HTTP adapter | AWS Lambda Web Adapter (runs a normal ASGI app inside Lambda) |
| Packaging | Container image with uv (see Open Questions; zip + layer is the alternative) |
| Dependency management | uv (`pyproject.toml` + `uv.lock`) |
| IaC / deploy | AWS SAM |
| CI/CD | GitHub Actions, OIDC to AWS (no long-lived keys) |
| Secrets | SSM Parameter Store, SecureString, standard tier (free) |
| State (if ever needed) | DynamoDB on-demand or S3; never in-memory |

## 3. Non-goals

- stdio transport (cannot be deployed remotely).
- The legacy HTTP+SSE transport.
- Stateful sessions, server-initiated notifications, or long-lived streaming (these would justify moving to Lightsail/EC2).
- VPC networking (a NAT gateway would cost more than the rest of the system combined).

## 4. Functional requirements

- FR1: Expose an MCP endpoint at `/mcp` over HTTPS.
- FR2: Implement the tools listed in Section 11 using the official MCP Python SDK (FastMCP).
- FR3: Run with `stateless_http=True` and `json_response=True`, so each request is independent.
- FR4: Work with MCP Inspector and at least one real MCP client.

## 5. Security requirements

- SR1: The Function URL uses `AuthType: NONE`, because MCP clients cannot sign requests with SigV4. Authentication is enforced in application code instead.
- SR2: Every request must carry `Authorization: Bearer <token>`. Requests without a valid token get HTTP 401 before any tool code runs. Compare tokens in constant time (`hmac.compare_digest`).
- SR3: The bearer token and the Anthropic API key are stored as SSM SecureString parameters (e.g. `/mcp-server/auth-token`, `/mcp-server/anthropic-api-key`), never in env vars, code, or the repo.
- SR4: The Lambda role has least privilege: `ssm:GetParameter` on those two parameters only, plus the standard CloudWatch Logs permissions.
- SR5: Secrets are fetched once at cold start and cached in a module-level variable.
- SR6: Set a spend limit on the Anthropic API key in the Anthropic console.
- SR7: Never log tokens, API keys, or full request bodies.
- Future: if clients require the full MCP OAuth flow, add an OAuth provider (e.g. Cognito) and revisit this section.

## 6. Cost requirements

- CR1: Target of about $0/month at low traffic (Lambda free tier, free Function URL, free SSM standard parameters).
- CR2: AWS Budget alert at $5/month, with email notification.
- CR3: CloudWatch log retention of 14 days (the default is never expire).
- CR4: No NAT gateway, no API Gateway, no Secrets Manager unless a requirement changes.
- CR5: Lambda memory 256-512 MB, timeout 30 s (tune after measuring).
- Pricing and free-tier terms change, so verify against the AWS pricing pages before launch.

## 7. Build and packaging

- Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.
- `sam build` does not read `uv.lock`, so the build exports `requirements.txt`:
  `uv export --no-dev --frozen --no-hashes -o requirements.txt`
- Dependencies must be built for Linux arm64 (pydantic-core and others ship compiled wheels).
- Container approach: base image `public.ecr.aws/lambda/python:3.12`, uv copied from `ghcr.io/astral-sh/uv`, Lambda Web Adapter copied into `/opt/extensions/`. Pin the adapter and uv versions.
- Zip approach (alternative): `uv pip install --target build/ --python-platform aarch64-manylinux2014 --python-version 3.12 --only-binary=:all:`, plus the Web Adapter as a Lambda layer with `AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap`.
- Limits: zip 50 MB zipped / 250 MB unzipped; container image up to 10 GB.

## 8. CI/CD (GitHub Actions)

- Trigger on `pull_request`: install with uv, run lint and tests. No deploy.
- Trigger on push to `main`: tests, then `sam build` and `sam deploy --no-confirm-changeset --no-fail-on-empty-changeset`.
- AWS access via OIDC (`aws-actions/configure-aws-credentials`). The IAM role trust policy is restricted to this repo and the `main` branch.
- The deploy role is scoped to what SAM needs (CloudFormation, Lambda, IAM role creation for the stack, S3/ECR for artifacts), tightened after the first working deploy.
- Use `ubuntu-latest` runners only (macOS/Windows consume free minutes faster). Pin action versions.
- The first deploy is done manually with `sam deploy --guided` to bootstrap the stack; CI takes over afterward.
- No AWS keys or Anthropic key stored in GitHub secrets.

## 9. Observability

- Logs go to CloudWatch automatically (14-day retention).
- Log one structured line per request: method, tool name, status, duration. No secrets or payloads.
- Optional: a CloudWatch alarm on Lambda errors and throttles.

## 10. Constraints to keep in mind

- No in-memory state between invocations, so stateless mode is mandatory.
- Cold starts add latency. Python and Node are the best fit for Lambda; Java/.NET are slower and costlier.
- Function URLs allow the full Lambda duration (up to 15 minutes); API Gateway would cut at about 30 s.
- The MCP SDK API changes quickly. Check current SDK docs for option names and pin the version.

## 11. Tools to implement (placeholder)

TBD. List each tool with name, inputs, outputs, and external calls (e.g. whether it calls the Anthropic API).

## 12. Proposed project layout

```
.
├── SPEC.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── template.yaml            # SAM: function, Function URL, role, log group, SSM access
├── app/
│   ├── main.py              # FastMCP app + bearer-token middleware
│   └── tools/
├── tests/
└── .github/workflows/
    └── deploy.yml
```

## 13. Acceptance criteria

1. `curl` to the Function URL without a token returns 401.
2. MCP Inspector connects with the token, lists tools, and calls each one successfully.
3. A real MCP client can use the server end to end.
4. Pushing to `main` deploys automatically via GitHub Actions with no stored AWS keys.
5. Budget alert and 14-day log retention are in place.
6. Monthly cost at expected traffic is about $0.

## 14. Open questions

1. What tools will the server expose, and do any of them call the Anthropic API?
2. Packaging: container image (uses ECR, a few cents/month) or zip + layer (no ECR)? Default in this spec is the container.
3. Which clients will connect? If any require the full MCP OAuth flow, bearer-token auth is not enough.
4. Expected traffic and latency tolerance (does a cold start of about a second matter)?
5. AWS region, and a single environment or separate dev/prod stacks?
6. Custom domain needed? (Function URLs have an auto-generated hostname; a custom domain would need CloudFront or API Gateway.)
