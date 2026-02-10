@echo off
set IMAGE_NAME=fastapi-ai-cli
set IMAGE_TAG=v1.3
if not "%1"=="" set IMAGE_TAG=%1
docker build -t %IMAGE_NAME%:%IMAGE_TAG% .
echo Built %IMAGE_NAME%:%IMAGE_TAG%
