import json
import time
import hashlib
import base64
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from ecdsa import SigningKey, SECP256k1
import httpx

logger = logging.getLogger(__name__)
@dataclass(frozen=True)
class GonkaClusterNode:
    base_url: str
    priority: int
    provider_address: str

def encode_with_low_s(r: int, s: int, order: int) -> bytes:
    if s > order // 2:
        s = order - s
    r_bytes = r.to_bytes(32, 'big')
    s_bytes = s.to_bytes(32, 'big')
    return r_bytes + s_bytes

class GonkaClient:
    def __init__(self, private_key: str, address: str, endpoint: str, provider_address: str, timeout: float = 60.0, stream_read_timeout: float = 300.0):
        self.private_key = private_key
        self.address = address
        self.endpoint = endpoint.rstrip('/')
        self.provider_address = provider_address
        self.timeout = timeout
        self.stream_read_timeout = stream_read_timeout
        self._wall_base = time.time_ns()
        self._perf_base = time.perf_counter_ns()
        self.client = httpx.AsyncClient(timeout=timeout)
    # Additional methods remain unchanged
