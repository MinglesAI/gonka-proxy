import json
import time
import hashlib
import base64
import logging
from typing import Optional, Tuple
from ecdsa import SigningKey, SECP256k1
import httpx


logger = logging.getLogger(__name__)


class GonkaClient:
    """Client for making signed requests to Gonka API"""
    
    def __init__(
        self,
        private_key: str,
        address: str,
        endpoint: str,
        provider_address: str,
        timeout: float = 60.0
    ):
        self.private_key = private_key
        self.address = address
        self.endpoint = endpoint.rstrip('/')
        self.provider_address = provider_address
        self.timeout = timeout
        
        # Initialize hybrid timestamp tracking
        self._wall_base = time.time_ns()
        self._perf_base = time.perf_counter_ns()
        
        # HTTP client
        self.client = httpx.AsyncClient(timeout=timeout)
    
    def _hybrid_timestamp_ns(self) -> int:
        """Generate hybrid timestamp (monotonic + aligned to wall clock)"""
        return self._wall_base + (time.perf_counter_ns() - self._perf_base)
    
    def _sign_payload(
        self,
        payload_bytes: bytes,
        timestamp_ns: int,
        provider_address: str
    ) -> str:
        """Sign payload using ECDSA with SHA-256"""
        # Remove 0x prefix if present
        pk = self.private_key[2:] if self.private_key.startswith('0x') else self.private_key
        sk = SigningKey.from_string(bytes.fromhex(pk), curve=SECP256k1)
        
        # Message bytes: payload || timestamp || provider_address
        msg = payload_bytes + str(timestamp_ns).encode('utf-8') + provider_address.encode('utf-8')
        
        # Deterministic ECDSA over SHA-256 with low-S normalization
        sig = sk.sign_deterministic(msg, hashfunc=hashlib.sha256)
        r, s = sig[:32], sig[32:]
        
        order = SECP256k1.order
        s_int = int.from_bytes(s, 'big')
        if s_int > order // 2:
            s_int = order - s_int
            s = s_int.to_bytes(32, 'big')
        
        return base64.b64encode(r + s).decode('utf-8')
    
    def _prepare_request(self, payload: Optional[dict]) -> Tuple[bytes, dict]:
        """Prepare request data (payload bytes, headers with signature)"""
        if payload is None:
            payload = {}
        
        payload_bytes = json.dumps(payload).encode('utf-8')
        timestamp_ns = self._hybrid_timestamp_ns()
        signature = self._sign_payload(payload_bytes, timestamp_ns, self.provider_address)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": signature,
            "X-Requester-Address": self.address,
            "X-Timestamp": str(timestamp_ns),
        }
        
        return payload_bytes, headers
    
    async def get_models(self) -> list:
        """Get available models from Gonka API"""
        try:
            # GET request with empty payload (still needs signature)
            response = await self.request("GET", "/models", payload={})
            models = response.get("models", [])
            logger.info(f"Loaded {len(models)} models from Gonka API")
            return models
        except Exception as e:
            logger.warning(f"Failed to load models from Gonka API: {e}")
            return []
    
    async def request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None
    ) -> dict:
        """Make a signed request to Gonka API (non-streaming)"""
        url = f"{self.endpoint}{path}"
        payload_bytes, headers = self._prepare_request(payload)
        
        # Log request body before sending
        try:
            request_body = json.loads(payload_bytes.decode('utf-8'))
            logger.info(f"Gonka API Request: {method} {url}")
            logger.info(f"Request body: {json.dumps(request_body, indent=2, ensure_ascii=False)}")
        except Exception as e:
            logger.warning(f"Failed to log request body: {e}")
        
        try:
            response = await self.client.request(
                method,
                url,
                headers=headers,
                content=payload_bytes
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            # Log error response
            try:
                error_body = e.response.text
                logger.error(f"Gonka API Error Response: {e.response.status_code}")
                logger.error(f"Error response body: {error_body}")
            except Exception:
                logger.error(f"Gonka API Error Response: {e.response.status_code} (failed to read body)")
            raise
        except Exception as e:
            logger.error(f"Gonka API Request failed: {type(e).__name__}: {str(e)}")
            raise
    
    async def request_stream(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None
    ):
        """Make a signed streaming request to Gonka API"""
        url = f"{self.endpoint}{path}"
        payload_bytes, headers = self._prepare_request(payload)
        
        # Log request body before sending
        try:
            request_body = json.loads(payload_bytes.decode('utf-8'))
            logger.info(f"Gonka API Stream Request: {method} {url}")
            logger.info(f"Request body: {json.dumps(request_body, indent=2, ensure_ascii=False)}")
        except Exception as e:
            logger.warning(f"Failed to log request body: {e}")
        
        try:
            async with self.client.stream(
                method,
                url,
                headers=headers,
                content=payload_bytes
            ) as response:
                if response.status_code >= 400:
                    # Read error response body
                    try:
                        error_body = await response.aread()
                        error_text = error_body.decode('utf-8', errors='replace')
                        logger.error(f"Gonka API Stream Error Response: {response.status_code}")
                        logger.error(f"Error response body: {error_text}")
                    except Exception as read_err:
                        logger.error(f"Gonka API Stream Error Response: {response.status_code} (failed to read body: {read_err})")
                    response.raise_for_status()
                
                async for chunk in response.aiter_bytes():
                    yield chunk
        except httpx.HTTPStatusError as e:
            # Log error response (fallback for non-stream errors)
            try:
                error_body = e.response.text
                logger.error(f"Gonka API Stream Error Response: {e.response.status_code}")
                logger.error(f"Error response body: {error_body}")
            except Exception:
                logger.error(f"Gonka API Stream Error Response: {e.response.status_code} (failed to read body)")
            raise
        except Exception as e:
            logger.error(f"Gonka API Stream Request failed: {type(e).__name__}: {str(e)}")
            raise
    
    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

