# Gonka OpenAI Proxy

OpenAI-compatible API proxy for Gonka that provides a ChatGPT-like interface with API key authentication. Self-hosted, no database required — configured entirely via environment variables.

## Features

- **OpenAI-compatible API**: Drop-in replacement for OpenAI Python SDK and other OpenAI-compatible clients
- **API Key Authentication**: Secure access using configurable API keys
- **Streaming Support**: Supports both streaming and non-streaming responses
- **Tool Emulation**: Automatic prompt-based tool call emulation for models that don't support native tool calling
- **Circuit Breaker**: Prevents cascading failures when the Gonka backend is degraded
- **Retry with Backoff**: Automatic retry with exponential backoff on transient errors
- **Web Interface**: Built-in web chat interface for testing
- **Docker Support**: Ready-to-use Docker container

## Quick Start

### Running Locally

1. Clone the repository:
```bash
git clone https://github.com/MinglesAI/gonka-proxy.git
cd gonka-proxy
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file (see [Environment Variables](#environment-variables)):
```bash
cp .env.example .env
# Edit .env with your values
```

4. Run the server:
```bash
python -m app.main
```

Or with uvicorn directly:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

5. Open `http://localhost:8000/` in your browser to use the web chat interface.

### Running with Docker

1. Build the image:
```bash
docker build -t gonka-proxy .
```

2. Run the container:
```bash
docker run -d \
  --name gonka-proxy \
  -p 8000:8000 \
  -e GONKA_PRIVATE_KEY=your_hex_private_key \
  -e GONKA_ADDRESS=your_gonka_address_bech32 \
  -e GONKA_ENDPOINT=https://host:port/v1 \
  -e GONKA_PROVIDER_ADDRESS=provider_gonka_address_bech32 \
  -e API_KEY=sk-your-secret-api-key \
  gonka-proxy
```

Or with a `.env` file:
```bash
docker run -d \
  --name gonka-proxy \
  -p 8000:8000 \
  --env-file .env \
  gonka-proxy
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GONKA_PRIVATE_KEY` | ✅ | — | Your ECDSA private key in hex format (with or without `0x` prefix) |
| `GONKA_ADDRESS` | ✅ | — | Your Gonka address in bech32 format (e.g. `gonka1abc...`) |
| `GONKA_ENDPOINT` | ✅ | — | Gonka API base URL (e.g. `https://host:port/v1`) |
| `GONKA_PROVIDER_ADDRESS` | ✅ | — | Provider's Gonka address in bech32 format — used for request signing |
| `API_KEY` | ✅ | — | Secret key clients must send in the `Authorization` header |
| `HOST` | ❌ | `0.0.0.0` | Server bind address |
| `PORT` | ❌ | `8000` | Server port |
| `GONKA_STREAM_READ_TIMEOUT` | ❌ | `300.0` | Max seconds to wait for streaming data from backend |

### Configuration Details

#### GONKA_PRIVATE_KEY
Your ECDSA private key in hex format. Used to sign every request to the Gonka backend.
Example: `a1b2c3d4e5f6...` or `0xa1b2c3d4e5f6...`

#### GONKA_ADDRESS
Your address in the Gonka network (bech32 format). Sent as the `X-Requester-Address` header.
Example: `gonka1qyqszqgpqyqszqgpqyqszqgp...`

#### GONKA_ENDPOINT
The Gonka inference API endpoint. Must include the `/v1` path segment.
Example: `https://my-gonka-node.example.com/v1`

#### GONKA_PROVIDER_ADDRESS
The **provider's** Gonka address (bech32 format). This is included in the cryptographic signature of every request and must match what the provider expects. Obtain this from your Gonka provider's documentation or contact page.
Example: `gonka1provideraddress...`

#### API_KEY
The bearer token clients must include in requests to the proxy.
Example: `sk-my-secret-key-123`

Clients send it as:
```
Authorization: Bearer sk-my-secret-key-123
```

### Example `.env` file

```bash
GONKA_PRIVATE_KEY=0xaabbccddeeff...
GONKA_ADDRESS=gonka1youraddress...
GONKA_ENDPOINT=https://my-gonka-node.example.com/v1
GONKA_PROVIDER_ADDRESS=gonka1provideraddress...
API_KEY=sk-my-secret-api-key
```

## Usage

### Web Interface

Open `http://localhost:8000/` to access the built-in chat interface.

### OpenAI Python SDK

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

### Streaming

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-your-secret-key",
    base_url="http://localhost:8000/v1"
)

stream = client.chat.completions.create(
    model="gonka-model",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### curl

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-your-secret-key" \
  -d '{
    "model": "gonka-model",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## API Endpoints

| Endpoint | Auth | Description |
|---|---|---|
| `POST /v1/chat/completions` | ✅ | Chat completions (OpenAI-compatible) |
| `GET /v1/models` | ✅ | List available models (OpenAI-compatible) |
| `GET /api/models` | ❌ | Get available models (for web interface) |
| `GET /health` | ❌ | Health check (includes circuit breaker state) |
| `GET /` | ❌ | Web chat interface |

## Architecture

### Tool Emulation

If the Gonka model doesn't support native tool calling (`tools` + `tool_choice`), the proxy automatically converts tool definitions into a system prompt and parses tool call JSON from the model's text response. This is transparent to the client — it still receives standard OpenAI-format `tool_calls` in the response.

### Circuit Breaker

Wraps non-streaming Gonka backend calls. After 5 consecutive failures, the circuit opens and requests are rejected immediately with a `503` error for 60 seconds, then transitions to half-open to test recovery.

### Retry

Non-streaming requests are retried up to 2 times with exponential backoff on transient errors.

## License

MIT
