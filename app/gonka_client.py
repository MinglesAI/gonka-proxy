import json
import time
import hashlib
import base64
import logging
from typing import Optional, Tuple
from ecdsa import SigningKey, SECP256k1
import httpx


logger = logging.getLogger(__name__)


def encode_with_low_s(r: int, s: int, order: int) -> bytes:
    """Encode ECDSA signature with low-S normalization"""
    # Normalize s to low-S
    if s > order // 2:
        s = order - s

    # Convert to bytes (32 bytes each for r and s)
    r_bytes = r.to_bytes(32, 'big')
    s_bytes = s.to_bytes(32, 'big')

    return r_bytes + s_bytes


class GonkaClient:
    """Client for making signed requests to Gonka API"""

    def __init__(
        self,
        private_key: str,
        address: str,
        endpoint: str,
        provider_address: str,
        timeout: float = 60.0,
        stream_read_timeout: float = 300.0,
    ):
        self.private_key = private_key
        self.address = address
        self.endpoint = endpoint.rstrip('/')
        self.provider_address = provider_address
        self.timeout = timeout
        self.stream_read_timeout = stream_read_timeout

        # Initialize hybrid timestamp tracking
        self._wall_base = time.time_ns()
        self._perf_base = time.perf_counter_ns()

        # HTTP client: default timeout for non-streaming; streaming uses per-request timeout
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
        signing_key = SigningKey.from_string(bytes.fromhex(pk), curve=SECP256k1)

        # Phase 3: Sign hash of payload instead of raw payload
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        # Build signature input: hash + timestamp + transfer_address
        signature_input = payload_hash
        signature_input += str(timestamp_ns)
        signature_input += provider_address

        signature_bytes = signature_input.encode('utf-8')

        # Sign the message with deterministic ECDSA using low-S normalization
        signature = signing_key.sign_deterministic(
            signature_bytes,
            hashfunc=hashlib.sha256,
            sigencode=lambda r, s, order: encode_with_low_s(r, s, order)
        )

        return base64.b64encode(signature).decode('utf-8')

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

        logger.info(f"Gonka API Request: {method} {path}")
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
            logger.error(f"Gonka API Error Response: {e.response.status_code}")
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

        logger.info(f"Gonka API Stream Request: {method} {path}")
        try:
            # Use longer read timeout for streaming so long generations don't get cut off
            stream_timeout = httpx.Timeout(self.timeout, read=self.stream_read_timeout)
            async with self.client.stream(
                method,
                url,
                headers=headers,
                content=payload_bytes,
                timeout=stream_timeout,
            ) as response:
                if response.status_code >= 400:
                    try:
                        error_body = await response.aread()
                        error_text = error_body.decode('utf-8', errors='replace')
                        logger.error(f"Gonka API Stream Error Response: {response.status_code}")
                        logger.error(f"Error response body: {error_text}")
                    except Exception as read_err:
                        logger.error(
                            f"Gonka API Stream Error Response: {response.status_code} "
                            f"(failed to read body: {read_err})"
                        )
                    response.raise_for_status()

                total_bytes = 0
                chunk_count = 0
                completed_normally = False
                try:
                    async for chunk in response.aiter_bytes():
                        total_bytes += len(chunk)
                        chunk_count += 1
                        yield chunk
                    completed_normally = True
                    logger.info(
                        f"Gonka API Stream completed: {method} {path} "
                        f"(chunks={chunk_count}, bytes={total_bytes})"
                    )
                finally:
                    if not completed_normally:
                        logger.info(
                            f"Gonka API Stream ended without full completion: {method} {path} "
                            f"(chunks={chunk_count}, bytes={total_bytes}) — client disconnect or stream closed"
                        )
        except httpx.HTTPStatusError as e:
            logger.error(f"Gonka API Stream Error Response: {e.response.status_code}")
            raise
        except httpx.ReadTimeout:
            logger.error(
                "Gonka API Stream read timeout: backend did not send data within "
                "stream_read_timeout; stream ended abruptly"
            )
            raise
        except httpx.ConnectError as e:
            logger.error(f"Gonka API Stream connection error: {e}")
            raise
        except httpx.WriteTimeout:
            logger.error("Gonka API Stream write timeout: request body send timed out")
            raise
        except Exception as e:
            logger.error(
                f"Gonka API Stream failed unexpectedly: {type(e).__name__}: {str(e)}"
            )
            raise

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()
