# Telegram Bot API Local Server Docker Setup

This directory contains the Docker configuration for running a local Telegram Bot API server to support large file uploads (up to 2GB).

## Prerequisites

You need to obtain your own API credentials from Telegram:
1. Go to https://my.telegram.org
2. Log in with your phone number
3. Go to "API development tools"
4. Create a new application
5. Save your `api_id` and `api_hash`

## Building the Docker Image

```bash
# Navigate to this directory
cd docker/telegram-bot-api-server

# Build the image
docker build -t telegram-bot-api-local .
```

## Running the Container

### Basic Run Command

```bash
docker run -d \
  --name telegram-bot-api \
  -p 8081:8081 \
  -v telegram-bot-api-data:/var/lib/telegram-bot-api \
  -e TELEGRAM_API_ID=YOUR_API_ID \
  -e TELEGRAM_API_HASH=YOUR_API_HASH \
  telegram-bot-api-local \
  --api-id=${TELEGRAM_API_ID} \
  --api-hash=${TELEGRAM_API_HASH} \
  --local \
  --dir=/var/lib/telegram-bot-api
```

### Windows PowerShell Command

```powershell
docker run -d `
  --name telegram-bot-api `
  -p 8081:8081 `
  -v telegram-bot-api-data:/var/lib/telegram-bot-api `
  -e TELEGRAM_API_ID=YOUR_API_ID `
  -e TELEGRAM_API_HASH=YOUR_API_HASH `
  telegram-bot-api-local `
  --api-id=$env:TELEGRAM_API_ID `
  --api-hash=$env:TELEGRAM_API_HASH `
  --local `
  --dir=/var/lib/telegram-bot-api
```

### Using Docker Compose (Recommended)

Create a `.env` file in this directory:
```env
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
```

Then use the docker-compose.yaml file provided.

## Configuring Your Bot

After starting the local server, update your bot's settings:

1. Edit `app/settings.py`:
```python
def get_default_application(self) -> Application:
    _base_builder = (
        Application.builder()
        .token(self.TELEGRAM_BOT_API_TOKEN.get_secret_value())
        .base_url("http://localhost:8081/bot")  # Enable this line
        .local_mode(True)  # Set to True
        # ... rest of configuration
    )
```

2. Restart your bot application

## Verifying the Setup

1. Check if the server is running:
```bash
docker logs telegram-bot-api
```

2. Test the API endpoint:
```bash
curl http://localhost:8081/bot<YOUR_BOT_TOKEN>/getMe
```

## File Size Limits

- Without local server: Maximum 50MB
- With local server: Maximum 2000MB (2GB)

## Troubleshooting

### Container won't start
- Check if you provided valid API_ID and API_HASH
- Ensure port 8081 is not already in use

### Bot can't connect
- Verify the container is running: `docker ps`
- Check firewall settings for port 8081
- Ensure bot is configured with correct base_url

### Large files still fail
- Verify local_mode is enabled in bot settings
- Check available disk space in Docker volume
- Review container logs for errors

## Stopping the Server

```bash
docker stop telegram-bot-api
docker rm telegram-bot-api
```

## Cleaning Up

To remove the volume (this will delete all cached data):
```bash
docker volume rm telegram-bot-api-data
```