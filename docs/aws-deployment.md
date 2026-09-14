# AWS and Bedrock

The current deployment guide is [AWS_DEPLOYMENT.md](../AWS_DEPLOYMENT.md), with measured results in [DEPLOYMENT_STATUS.md](../DEPLOYMENT_STATUS.md).

## Local Bedrock provider

1. Configure an AWS CLI profile or an IAM role with permission to invoke your chosen Bedrock model; complete the model's access requirements in the AWS account and region.
2. Set `TRAIL_AGENT_MODE=bedrock`, `AWS_REGION`, and `BEDROCK_MODEL_ID` in the ignored `.env` file; prefer an AWS profile or role over static credentials in files.
3. Restart the API and run `python scripts/check_bedrock.py` for a small synthetic connectivity test, then run the ordinary demo to exercise the same guarded tools.

The check can incur Bedrock usage charges; the model receives sanitized motion/risk evidence rather than the runner's name, exact coordinates, or contact details.

The selected default model identifier is a configurable example from the brief, and availability depends on account, region, model access, and inference-profile permissions; a failed or slow invocation records `POLICY_FALLBACK` instead of pretending that Bedrock reasoning succeeded.

The local mode always remains available with `TRAIL_AGENT_MODE=mock`, which uses a deterministic provider inside the actual Strands loop.

## Container deployment

The supplied Docker Compose configuration is for a local single-worker deployment; a cloud demo can run the same containers behind HTTPS with a persistent database volume, a narrowly scoped Bedrock IAM role, secrets supplied by a secret store, and the public frontend origin in `CORS_ORIGINS`.

Set `COOKIE_SECURE=true` behind HTTPS, keep the API internal to the reverse proxy, and use one API worker until database scheduling and concurrency are redesigned; Docker Compose deliberately binds the frontend to loopback by default.

The Lightsail scripts now provision a persistent single-host deployment with Caddy HTTPS, Nginx, and Docker Compose; the status document distinguishes verified work from remaining AWS account steps.

## Optional AgentCore path

AgentCore Runtime is not used by this deployment; live inference runs outside database write locks, and actual tools reload authorized session state in short transactions.

The appropriate next step is to separate sanitized agent inference from state mutation, expose authenticated idempotent backend tools over a secure boundary, place deadlines on a durable scheduler, and use PostgreSQL or DynamoDB conditional state changes before deploying the agent runtime.

This preserves the same Strands orchestration while allowing AgentCore to host the inference component without treating its execution lifetime as the safety countdown.
