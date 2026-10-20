# MCP Server on AWS Lambda: Deployment and Setup Spec

Companion to `SPEC.md`. This file lists every setup task, split by who does it.

- **Part A: Needs you** (AWS console, AWS CLI, GitHub settings). These involve credentials, secrets or account-level changes.
- **Part B: AI can do** (code and config files that can be generated and reviewed).

Fixed values for this project:

| Item | Value |
|---|---|
| AWS profile (local) | `personal-dev` (IAM user, no SSO) |
| Region | `us-east-2` |
| Runtime | Python 3.12, arm64, container image |
| Stack name | `mp-mcp` |
| GitHub repo | `jorgelcameo/mp-mcp` |
| SSM parameters | `/mcp-server/auth-token`, `/mcp-server/anthropic-api-key` (only if tools call Claude) |

## Suggested order

1. B1-B5 (AI generates the project and SAM files)
2. A1-A4 (permissions, profile check, SSM secrets)
3. A5 (first manual deploy)
4. A6-A8 (budget, GitHub OIDC, GitHub variables) and B6-B7 (workflow, tests)
5. A9 (verification)

---

# Part A: Needs you

## A1. Give the `personal-dev` IAM user enough permissions (console, as admin)

The `AccessDenied` on `iam:ListAttachedUserPolicies` shows the user has no IAM permissions. Sign in to the console with an admin identity (root or an admin IAM user), then: IAM > Users > `personal-dev` > Add permissions.

Choose one option.

**Option 0: quickest.** Attach `AdministratorAccess`. Acceptable for a personal sandbox, not least privilege.

**Option 1: middle ground.** Attach the managed policy `PowerUserAccess` (covers CloudFormation, Lambda, ECR, S3, Logs, SSM but not IAM), plus this inline policy for role management:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
      "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
      "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy"
    ],
    "Resource": "arn:aws:iam::102171546465:role/mp-mcp-*"
  }]
}
```

The inline policy alone is not enough. `PowerUserAccess` must be attached too.

**Option 2: least privilege.** One inline policy, scoped to this account and `us-east-2`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CloudFormation",
      "Effect": "Allow",
      "Action": "cloudformation:*",
      "Resource": [
        "arn:aws:cloudformation:us-east-2:102171546465:stack/mp-mcp/*",
        "arn:aws:cloudformation:us-east-2:102171546465:stack/aws-sam-cli-managed-default/*",
        "arn:aws:cloudformation:us-east-2:aws:transform/Serverless-2016-10-31"
      ]
    },
    {
      "Sid": "CloudFormationNoResourceScope",
      "Effect": "Allow",
      "Action": ["cloudformation:GetTemplateSummary", "cloudformation:ListStacks"],
      "Resource": "*"
    },
    {
      "Sid": "SamManagedBucket",
      "Effect": "Allow",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::aws-sam-cli-managed-default-*",
        "arn:aws:s3:::aws-sam-cli-managed-default-*/*"
      ]
    },
    {
      "Sid": "EcrRepos",
      "Effect": "Allow",
      "Action": "ecr:*",
      "Resource": "arn:aws:ecr:us-east-2:102171546465:repository/mp-mcp*"
    },
    {
      "Sid": "EcrLogin",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "Lambda",
      "Effect": "Allow",
      "Action": "lambda:*",
      "Resource": "arn:aws:lambda:us-east-2:102171546465:function:mp-mcp-*"
    },
    {
      "Sid": "Roles",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole", "iam:DeleteRole", "iam:GetRole", "iam:PassRole",
        "iam:AttachRolePolicy", "iam:DetachRolePolicy",
        "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:GetRolePolicy",
        "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
        "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy"
      ],
      "Resource": "arn:aws:iam::102171546465:role/mp-mcp-*"
    },
    {
      "Sid": "Logs",
      "Effect": "Allow",
      "Action": "logs:*",
      "Resource": "arn:aws:logs:us-east-2:102171546465:log-group:*"
    },
    {
      "Sid": "Ssm",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:PutParameter"],
      "Resource": "arn:aws:ssm:us-east-2:102171546465:parameter/mcp-server/*"
    }
  ]
}
```

Scoped policies rarely fit on the first try. Each `AccessDenied` message names the exact missing action and resource; add it and retry. If that gets tedious, use Option 1.

Notes:

- A user who can create roles and attach policies can in principle grant itself more access. That is acceptable in a personal sandbox but not in a shared account.
- If you add canary deployments later, you also need CodeDeploy and CloudWatch alarm permissions.
- Do not create access keys for the root user. Use IAM users.

## A2. Verify the profile and region (CLI)

```bash
aws configure list-profiles
aws configure get region --profile personal-dev      # should print us-east-2
aws configure set region us-east-2 --profile personal-dev   # only if empty or different
aws sts get-caller-identity --profile personal-dev
aws cloudformation list-stacks --profile personal-dev --region us-east-2
```

If the last command works, the permissions from A1 are in effect. Do not use `aws iam list-attached-user-policies` as a test; the policies above do not allow it.

**If SAM keeps asking for an SSO login**, something is pointing at one of your other (SSO) profiles. Precedence is: `--profile` flag, then `AWS_PROFILE`, then `profile` in `samconfig.toml`, then `[default]`. Check:

```bash
echo $AWS_PROFILE
grep -n profile samconfig.toml
cat ~/.aws/config
```

Fix by running `unset AWS_PROFILE`, editing the `profile` line in `samconfig.toml`, or passing `--profile personal-dev` explicitly. Locally, `export AWS_PROFILE=personal-dev` is the simplest.

## A3. Clean up the earlier failed deploy (CLI)

```bash
aws cloudformation describe-stacks --stack-name mp-mcp --query "Stacks[0].StackStatus" --profile personal-dev --region us-east-2
```

- `ROLLBACK_COMPLETE`: delete it with `sam delete --stack-name mp-mcp --profile personal-dev --region us-east-2` (answer `y`). A stack in this state cannot be updated.
- "does not exist": nothing to do.
- If the failed stack was created in a different region, delete it there with `--region <that-region>`, and remove its ECR repository if it lingers.

To see why a deploy failed, look at the earliest failed event:

```bash
aws cloudformation describe-stack-events --stack-name mp-mcp \
  --query "StackEvents[?contains(ResourceStatus,'FAILED')].[LogicalResourceId,ResourceStatusReason]" \
  --output table --profile personal-dev --region us-east-2
```

## A4. Create the secrets in SSM Parameter Store (CLI)

Create these in `us-east-2` (parameters are per-region). Never paste secret values into chats, code or git.

```bash
# bearer token your MCP clients will send
aws ssm put-parameter --name /mcp-server/auth-token --type SecureString \
  --value "$(openssl rand -hex 32)" --profile personal-dev --region us-east-2

# only if a tool calls the Anthropic API
aws ssm put-parameter --name /mcp-server/anthropic-api-key --type SecureString \
  --value "<your-anthropic-key>" --profile personal-dev --region us-east-2
```

Read the token back when you need it for clients:

```bash
aws ssm get-parameter --name /mcp-server/auth-token --with-decryption \
  --query Parameter.Value --output text --profile personal-dev --region us-east-2
```

Also set a spend limit on the Anthropic key in the Anthropic console.

## A5. First manual deploy (CLI)

Run after Part B files exist (B1-B5). Docker must be running.

```bash
export AWS_PROFILE=personal-dev
sam build
sam deploy --guided --region us-east-2
```

Answers for the guided prompts:

| Prompt | Answer |
|---|---|
| Stack name | `mp-mcp` |
| AWS Region | `us-east-2` |
| Confirm changes before deploy | `y` |
| Allow SAM CLI IAM role creation | `y` (the stack creates the function's role) |
| Disable rollback | `N` (keep automatic rollback; use `y` only when debugging, never in CI) |
| Create managed ECR repositories for all functions | `Y` (SAM creates and manages the image repository) |
| Deploy this changeset? | `y` if every row is **Add** and nothing unexpected is listed |
| Save arguments to samconfig.toml | `y` |

About the changeset: it is CloudFormation's preview of what the deploy will add, modify or remove. Nothing happens until you answer `y`. On a first deploy everything should be **Add**. On later deploys, watch for **Remove** rows and `Replacement: True`, which mean a resource is destroyed and recreated.

If SAM asks about a function URL or API without authorization defined, answer `y`: the Function URL uses `AuthType: NONE` and authentication is enforced in application code (bearer token). Make sure the bearer-token check (B2) is in the deployed code, because the endpoint is public.

After the deploy succeeds, later deploys are just `sam build && sam deploy`.

## A6. Budget alert and log retention check (console)

- Billing and Cost Management > Budgets > Create budget > Monthly cost budget, **$5**, with email alerts.
- After the first deploy, confirm the Lambda log group shows 14-day retention (CloudWatch > Log groups).

## A7. GitHub OIDC role for CI/CD (console, as admin)

`personal-dev` cannot do this; use an admin identity.

1. **Identity provider** (once per account; skip if it exists): IAM > Identity providers > Add provider > OpenID Connect.
   - Provider URL: `https://token.actions.githubusercontent.com`
   - Audience: `sts.amazonaws.com`
2. **GitHub environment**: in `jorgelcameo/mp-mcp`, create the `production` environment and restrict deployments to the `main` branch. This workflow uses that environment, so GitHub's OIDC subject identifies the environment rather than the branch.
3. **Role**: IAM > Roles > Create role > Web identity.
   - Identity provider: `token.actions.githubusercontent.com`; audience `sts.amazonaws.com`
   - GitHub organization: `jorgelcameo`; repository: `mp-mcp`
   - Name it `mp-mcp-github-deploy`
4. **Verify the trust policy** (role > Trust relationships). It should be equivalent to:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "Federated": "arn:aws:iam::102171546465:oidc-provider/token.actions.githubusercontent.com"
    },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:jorgelcameo/mp-mcp:environment:production"
      }
    }
  }]
}
```

The `sub` condition restricts role assumption to this repository's `production` environment. The GitHub environment's deployment branch rule must restrict that environment to `main`; without these restrictions, another branch could deploy or another repository could assume the role.

5. **Permissions**: attach deployment permissions to this role. Start with the policy needed for the SAM resources in A1; do not grant the Lambda execution role's SSM permissions to the GitHub role unless SAM needs them.
6. **Copy the role ARN** from the role summary page:
   `arn:aws:iam::102171546465:role/mp-mcp-github-deploy`

## A8. GitHub repository settings

In `jorgelcameo/mp-mcp`: Settings > Secrets and variables > Actions > **Variables** tab > New repository variable.

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | the role ARN from A7 |
| `AWS_REGION` | `us-east-2` |
| `BUDGET_NOTIFICATION_EMAIL` | Optional: recipient for the budget alert; leave unset or blank to skip the budget resource |

The workflow reads these as repository variables. The role ARN is an identifier, not a credential. Do not store AWS access keys or the Anthropic key in GitHub; application secrets stay in SSM.

Optional hardening: add required reviewers to the `production` environment if you want manual approval before deploys.

## A9. Verify the deployment

```bash
# 1. no token: expect 401
curl -i -X POST <function-url>mcp

# 2. MCP Inspector with the bearer token
npx @modelcontextprotocol/inspector
```

- Connect the Inspector to the Function URL (Streamable HTTP) with the `Authorization: Bearer <token>` header, list tools, and call each one.
- Connect one real MCP client end to end.
- Push a commit to `main` and confirm the GitHub Action deploys without any stored AWS keys.

## A10. Ongoing housekeeping

- ECR charges storage and SAM pushes a new image per deploy; delete old images occasionally (or ask the AI to add a lifecycle policy, see B9).
- Rotate the bearer token if it leaks: `put-parameter --overwrite`, then update clients.
- If a first deploy ever fails again: find the first failed event (A3), fix, delete a `ROLLBACK_COMPLETE` stack, redeploy.

---

# Part B: AI can do

Give the AI this spec plus `SPEC.md`. Inputs it needs from you: stack name, repo name, and the list of tools the server should expose (and whether any call the Anthropic API).

## B1. Project scaffold

- `pyproject.toml` with uv, `requires-python = ">=3.12,<3.13"`, dependencies: the official MCP Python SDK (pinned), `uvicorn`, `boto3`; dev dependencies: `pytest`, `httpx`, a linter.
- Commit `uv.lock`.
- Layout as in `SPEC.md` Section 12 (`app/main.py`, `app/tools/`, `tests/`).

## B2. App and authentication

- `FastMCP` with `stateless_http=True` and `json_response=True`; expose the ASGI app via `mcp.streamable_http_app()`.
- ASGI middleware that requires `Authorization: Bearer <token>` and returns 401 otherwise, using `hmac.compare_digest`.
- Load the token (and, if needed, the Anthropic key) from SSM SecureString at cold start with `boto3` and cache it in a module-level variable. Parameter names come from environment variables.
- Never log tokens, keys or full request bodies; one structured log line per request (method, tool name, status, duration).
- Implement the tools from `SPEC.md` Section 11 once defined.

## B3. Dockerfile

- Base image `public.ecr.aws/lambda/python:3.12`.
- Copy uv from `ghcr.io/astral-sh/uv` and the Lambda Web Adapter into `/opt/extensions/`; pin both versions.
- Export requirements from the lockfile and install: `uv export --no-dev --frozen --no-hashes -o requirements.txt && uv pip install --system -r requirements.txt`.
- Run uvicorn on port 8080 (set the adapter's port variable to match).
- Build for arm64.

## B4. SAM template (`template.yaml`)

- `AWS::Serverless::Function` with `PackageType: Image`, `Architectures: [arm64]`, `MemorySize` 256-512, `Timeout` 30, and Docker build metadata.
- `FunctionUrlConfig` with `AuthType: NONE`.
- Environment variables: SSM parameter names (not values).
- Execution role policy: `ssm:GetParameter` on the two parameters only, plus CloudWatch Logs.
- Explicit `AWS::Logs::LogGroup` with 14-day retention.
- Output: the Function URL.

## B5. `samconfig.toml`

- `stack_name`, `region = "us-east-2"`, `resolve_image_repos = true`, `capabilities = "CAPABILITY_IAM"`, `confirm_changeset = true` for local use.
- No `profile` line (locally use `AWS_PROFILE=personal-dev`; CI uses OIDC).

## B6. GitHub Actions workflow (`.github/workflows/ci.yml`)

- On `pull_request`: `astral-sh/setup-uv`, `uv sync`, lint, `uv run pytest`. No deploy.
- On push to `main`: tests, then OIDC login, `sam build`, `sam deploy --no-confirm-changeset --no-fail-on-empty-changeset`.
- `permissions: id-token: write` and `contents: read`.
- Use `aws-actions/configure-aws-credentials` with `role-to-assume: ${{ vars.AWS_ROLE_ARN }}` and `aws-region: ${{ vars.AWS_REGION }}`.
- `ubuntu-latest` only; pin action versions. No AWS keys in the workflow.

## B7. Tests

- Missing or wrong token returns 401; valid token passes.
- Each tool has at least one test.
- Tests mock SSM so they run offline in CI.

## B8. README

- How to run locally with the MCP Inspector, how to build and deploy, and links to this spec.

## B9. Optional improvements

- ECR lifecycle policy keeping the last few images. This means defining your own `AWS::ECR::Repository` in the template instead of using managed repos, and answering `N` to the managed-repo prompt in A5.
- CloudWatch alarm on Lambda errors and throttles.
- Canary deployment (`AutoPublishAlias` plus `DeploymentPreference` and an alarm). Only worth it if traffic grows; it requires the Function URL on the alias and has some quirks.
- Request-level metrics in structured logs.

---

# Acceptance (combined)

1. A1-A4 done: `aws sts get-caller-identity --profile personal-dev` works and the SSM parameters exist in `us-east-2`.
2. `sam deploy` succeeds locally and outputs a Function URL.
3. `curl` without a token returns 401; the Inspector works with the token.
4. A push to `main` deploys via GitHub Actions through OIDC with no stored AWS keys.
5. Budget alert and 14-day log retention are in place.
