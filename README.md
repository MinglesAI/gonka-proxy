# Gonka OpenAI Proxy

OpenAI-compatible API proxy for Gonka that provides ChatGPT-like interface with API key authentication.

## Features

- **OpenAI-compatible API**: Compatible with OpenAI Python SDK and other OpenAI-compatible clients
- **API Key Authentication**: Secure access using API keys (like ChatGPT API)
- **Streaming Support**: Supports both streaming and non-streaming responses
- **Web Interface**: Built-in web chat interface for testing
- **Automatic Model Loading**: Loads available models from Gonka API on startup
- **Docker Support**: Ready-to-use Docker container

## Configuration

Copy `.env.example` to `.env` and configure the following variables:

```bash
# Gonka API Configuration
GONKA_PRIVATE_KEY=your_hex_private_key_here
GONKA_ADDRESS=your_gonka_address_bech32
GONKA_ENDPOINT=https://host:port/v1
GONKA_PROVIDER_ADDRESS=provider_gonka_address_bech32

# API Key for external access (like ChatGPT API)
API_KEY=sk-your-secret-api-key-here

# Server Configuration (optional)
HOST=0.0.0.0
PORT=8000
```

### Configuration Details

#### GONKA_PROVIDER_ADDRESS

**What is it?** `GONKA_PROVIDER_ADDRESS` is the provider (host) address in the Gonka network in bech32 format. It is used to sign requests to the Gonka API.

**Where to get it?**

1. **From provider documentation**: If you are using a specific Gonka provider, their address should be specified in their documentation or provider page.

2. **From endpoint metadata**: The provider address is usually associated with the endpoint (`GONKA_ENDPOINT`). The provider should specify their Gonka address in the documentation or during registration.

3. **Via Gonka Dashboard**: If you have access to the Gonka Dashboard, the provider address can be found in your connection information or node settings.

4. **Contact the provider**: If you are using a public Gonka endpoint, contact the endpoint owner or Gonka support to get the provider address.

**Example**: The address usually looks like `gonka1...` (bech32 format), e.g., `gonka1abc123def456...`

**Important**: The provider address is used in the cryptographic signature of each request, so it must be correct for successful authentication.

## Running with Docker

1. Build the Docker image:
```bash
docker build -t gonka-proxy .
```

2. Run the container:
```bash
docker run -d \
  --name gonka-proxy \
  -p 8000:8000 \
  --env-file .env \
  gonka-proxy
```

## Running Locally

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables or create `.env` file

3. Run the server:
```bash
python -m app.main
```

Or with uvicorn directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Usage

### Web Interface

Access the web interface at `http://localhost:8000/` to test the API interactively.

### Using OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-secret-key",
    base_url="http://localhost:8000/v1"
)

response = client.chat.completions.create(
    model="gonka-model",
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

### Using curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-your-secret-key" \
  -d '{
    "model": "gonka-model",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### Streaming

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-secret-key",
    base_url="http://localhost:8000/v1"
)

stream = client.chat.completions.create(
    model="gonka-model",
    messages=[
        {"role": "user", "content": "Tell me a story"}
    ],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

## API Endpoints

- `POST /v1/chat/completions` - Chat completions (OpenAI-compatible)
- `GET /v1/models` - List available models
- `GET /api/models` - Get available models (no auth, for web interface)
- `GET /health` - Health check endpoint (no auth required)
- `GET /` - Web chat interface

## Authentication

All endpoints except `/health`, `/api/models`, and `/` require authentication using the `Authorization` header:

```
Authorization: Bearer sk-your-secret-key
```

Or simply:

```
Authorization: sk-your-secret-key
```

## License

MIT
