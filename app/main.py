import json
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings

from app.gonka_client import GonkaClient
from app.auth import verify_api_key
from app.tool_emulation import (
    emulate_tool_choice_auto,
    process_response_with_tool_emulation,
    process_stream_with_tool_emulation,
)
from app.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.retry import retry_with_backoff, BACKEND_RETRY_CONFIG


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings"""
    # Gonka API settings
    gonka_private_key: str = ""
    gonka_address: str = ""
    gonka_endpoint: str = ""
    gonka_provider_address: str = ""

    # API Key for external access
    api_key: str = ""

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    # Streaming read timeout (seconds); increase for slow/long generations
    gonka_stream_read_timeout: float = 300.0

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


# Initialize Gonka client and models cache
gonka_client: Optional[GonkaClient] = None
available_models: List[Dict] = []

# Circuit breaker for Gonka backend
gonka_circuit_breaker = CircuitBreaker(
    name="gonka_backend",
    failure_threshold=5,
    recovery_timeout=60.0,
    success_threshold=2,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    global gonka_client, available_models

    try:
        client = _create_gonka_client()
        if client:
            models = await client.get_models()
            available_models = models
            logger.info(f"Successfully loaded {len(available_models)} models at startup")
        else:
            logger.warning("Gonka configuration incomplete, skipping model loading")
            available_models = []
    except Exception as e:
        logger.error(f"Failed to load models at startup: {e}")
        available_models = []

    yield

    if gonka_client:
        await gonka_client.close()


def _create_gonka_client() -> Optional[GonkaClient]:
    """Create Gonka client if configuration is complete (returns None if not configured)"""
    global gonka_client
    if gonka_client is None:
        if not all([
            settings.gonka_private_key,
            settings.gonka_address,
            settings.gonka_endpoint,
            settings.gonka_provider_address
        ]):
            return None
        gonka_client = GonkaClient(
            private_key=settings.gonka_private_key,
            address=settings.gonka_address,
            endpoint=settings.gonka_endpoint,
            provider_address=settings.gonka_provider_address,
            stream_read_timeout=settings.gonka_stream_read_timeout,
        )
    return gonka_client


def get_gonka_client() -> GonkaClient:
    """Get or create Gonka client (raises HTTPException if not configured)"""
    client = _create_gonka_client()
    if client is None:
        missing = []
        if not settings.gonka_private_key:
            missing.append("GONKA_PRIVATE_KEY")
        if not settings.gonka_address:
            missing.append("GONKA_ADDRESS")
        if not settings.gonka_endpoint:
            missing.append("GONKA_ENDPOINT")
        if not settings.gonka_provider_address:
            missing.append("GONKA_PROVIDER_ADDRESS")

        raise HTTPException(
            status_code=500,
            detail=f"Gonka configuration incomplete. Missing: {', '.join(missing)}. "
                   f"GONKA_PROVIDER_ADDRESS is the Gonka provider address (bech32 format), "
                   f"which can be obtained from the provider or in Gonka documentation."
        )
    return client


app = FastAPI(
    title="Gonka OpenAI Proxy",
    description="OpenAI-compatible API proxy for Gonka",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# OpenAI-compatible models endpoint
@app.get("/v1/models")
async def list_models(request: Request, api_key_valid: bool = Depends(verify_api_key)):
    """List available models (OpenAI-compatible endpoint)"""
    global available_models

    models_data = []
    for model in available_models:
        model_id = model.get("id", "unknown")
        models_data.append({
            "id": model_id,
            "object": "model",
            "created": 1677610602,
            "owned_by": "gonka"
        })

    if not models_data:
        models_data = [{
            "id": "gonka-model",
            "object": "model",
            "created": 1677610602,
            "owned_by": "gonka"
        }]

    return {
        "object": "list",
        "data": models_data
    }


# Models endpoint without auth (for web interface)
@app.get("/api/models")
async def get_models_no_auth():
    """Get available models without authentication (for web interface)"""
    global available_models
    return {"models": available_models}


# Chat completions endpoint
@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    api_key_valid: bool = Depends(verify_api_key)
):
    """Chat completions endpoint (OpenAI-compatible)"""
    client = get_gonka_client()

    try:
        body = await request.json()
        logger.info("Incoming chat completions request")
    except Exception as e:
        logger.error(f"Failed to parse request JSON: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    stream = body.get("stream", False)
    original_tools = body.get("tools")

    # Apply tool emulation if model doesn't support native tool calling
    # (emulate_tool_choice_auto is a no-op when no tools are present)
    emulated_body = emulate_tool_choice_auto(body)
    tools_were_emulated = original_tools and "tools" not in emulated_body

    try:
        if stream:
            async def generate():
                try:
                    raw_stream = client.request_stream(
                        method="POST",
                        path="/chat/completions",
                        payload=emulated_body,
                    )
                    if tools_were_emulated:
                        async for chunk in process_stream_with_tool_emulation(
                            raw_stream, original_tools
                        ):
                            yield chunk
                    else:
                        async for chunk in raw_stream:
                            yield chunk
                except CircuitBreakerOpenError as e:
                    logger.error(f"Circuit breaker open: {e}")
                    error_payload = json.dumps({"error": {"message": str(e), "type": "service_unavailable"}})
                    yield f"data: {error_payload}\n\ndata: [DONE]\n\n".encode()
                except Exception as e:
                    logger.error(f"Streaming error: {type(e).__name__}: {str(e)}")
                    raise

            return StreamingResponse(
                generate(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                }
            )
        else:
            # Non-streaming: wrap with circuit breaker + retry
            async def do_request():
                return await gonka_circuit_breaker.call(
                    client.request,
                    method="POST",
                    path="/chat/completions",
                    payload=emulated_body,
                )

            response = await retry_with_backoff(
                do_request,
                max_retries=BACKEND_RETRY_CONFIG.max_retries,
                initial_delay=BACKEND_RETRY_CONFIG.initial_delay,
                max_delay=BACKEND_RETRY_CONFIG.max_delay,
                exceptions=BACKEND_RETRY_CONFIG.exceptions,
            )

            if tools_were_emulated:
                response = process_response_with_tool_emulation(response, original_tools)

            return response

    except CircuitBreakerOpenError as e:
        logger.error(f"Circuit breaker open: {e}")
        raise HTTPException(status_code=503, detail=f"Backend temporarily unavailable: {str(e)}")
    except Exception as e:
        logger.error(f"Chat completions error: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


# Web interface endpoint (must be before static mount)
@app.get("/")
async def web_interface():
    """Serve web chat interface"""
    return FileResponse("app/static/index.html")


# Health check endpoint (no auth required)
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "ok",
        "circuit_breaker": gonka_circuit_breaker.get_state(),
    }


# Serve static files (must be last)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False
    )
