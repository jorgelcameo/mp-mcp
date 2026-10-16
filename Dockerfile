# Multi-stage build for AWS Lambda (container image, arm64).
#
# The base image is a stock python:3.12-slim, not an AWS managed base image: the
# Lambda Web Adapter ships the Runtime Interface Client, which is what makes a
# plain container image runnable on Lambda. The image is multi-arch.

FROM ghcr.io/astral-sh/uv:0.12.5 AS uv

FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim

COPY --from=uv /uv /uvx /bin/
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter

WORKDIR /var/task

ENV PYTHONPATH=/var/task/src:/var/task/deps \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health

# Dependencies come from uv.lock, so the image and the dev environment agree.
# --no-emit-project keeps the project itself out of requirements.txt; src/ is
# copied in the next layer instead.
COPY pyproject.toml uv.lock README.md ./
RUN uv export --frozen --no-dev --no-hashes --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --target /var/task/deps --no-cache -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY src/ /var/task/src/

EXPOSE 8080
CMD exec python -m uvicorn --host 0.0.0.0 --port "$AWS_LWA_PORT" mp_mcp.asgi:app
