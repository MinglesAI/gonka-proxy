# Gonka Proxy

Gonka Proxy is an API proxy for Gonka-compatible AI interfaces.

## Setup Locally

To run the Gonka Proxy locally, create a `.env` file in the root directory with the following variables:

- `GONKA_PRIVATE_KEY`: Your Gonka private key.
- `GONKA_ADDRESS`: Your Gonka address.
- `GONKA_ENDPOINT`: The Gonka API endpoint.
- `GONKA_PROVIDER_ADDRESS`: The Gonka provider address (bech32 format).
- `API_KEY`: Your API key for access.

## Running the Application

Use Docker or run it directly with Python:

```bash
# Using Docker
docker build -t gonka-proxy .
docker run -p 8000:8000 env-file .env gonka-proxy
```

```bash
# Directly
python3 -m app.main
```

## Testing

Test the tool emulation to ensure it is working as expected using the adapted tests from `test_tool_emulation.py`.


## Important Links

- Remove any internal links related to `mingles.ai` or any other non-public resources.