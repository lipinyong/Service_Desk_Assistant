#!/usr/bin/env bash
IMAGE_NAME=${IMAGE_NAME:-fastapi-ai-cli}
IMAGE_TAG=${IMAGE_TAG:-v1.3}
docker build -t "$IMAGE_NAME:$IMAGE_TAG" .
echo "Built $IMAGE_NAME:$IMAGE_TAG"
