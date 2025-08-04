#!/bin/bash
# Start script for Telegram Bot API local server

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file not found!"
    echo "Please copy .env.example to .env and fill in your API credentials"
    exit 1
fi

# Load environment variables
source .env

# Check if API credentials are provided
if [ -z "$TELEGRAM_API_ID" ] || [ -z "$TELEGRAM_API_HASH" ]; then
    echo "Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in .env file"
    exit 1
fi

# Build the image if it doesn't exist
if ! docker images | grep -q "telegram-bot-api-local"; then
    echo "Building Docker image..."
    docker build -t telegram-bot-api-local .
fi

# Stop and remove existing container if it exists
if docker ps -a | grep -q "telegram-bot-api"; then
    echo "Stopping existing container..."
    docker stop telegram-bot-api
    docker rm telegram-bot-api
fi

# Start the container
echo "Starting Telegram Bot API server..."
docker run -d \
  --name telegram-bot-api \
  -p 8081:8081 \
  -v telegram-bot-api-data:/var/lib/telegram-bot-api \
  -e TELEGRAM_API_ID=$TELEGRAM_API_ID \
  -e TELEGRAM_API_HASH=$TELEGRAM_API_HASH \
  telegram-bot-api-local \
  --api-id=$TELEGRAM_API_ID \
  --api-hash=$TELEGRAM_API_HASH \
  --local \
  --dir=/var/lib/telegram-bot-api

# Check if container started successfully
if [ $? -eq 0 ]; then
    echo "Telegram Bot API server started successfully!"
    echo "Server is running on http://localhost:8081"
    echo ""
    echo "To view logs: docker logs -f telegram-bot-api"
    echo "To stop: docker stop telegram-bot-api"
else
    echo "Failed to start Telegram Bot API server"
    exit 1
fi