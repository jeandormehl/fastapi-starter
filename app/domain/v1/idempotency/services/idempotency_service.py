import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

from kink import di
from pydantic import BaseModel

from app.common.errors.errors import ApplicationError, ErrorCode
from app.common.logging import get_logger
from app.core.config import Configuration
from app.infrastructure.database import Database


class CacheType(str, Enum):
    REQUEST = "request"
    TASK = "task"


class IdempotencyResult(BaseModel):
    """Result of idempotency check"""

    is_duplicate: bool
    cached_response: dict | None = None
    cache_id: str | None = None
    cache_type: CacheType | None = None


class IdempotencyService:
    """Service for handling request and task idempotency"""

    def __init__(self) -> None:
        self.db = di[Database]
        self.config = di[Configuration].idempotency
        self.logger = get_logger(__name__)

    @property
    def cache_ttl_hours(self) -> int:
        return self.config.cache_ttl_hours

    @property
    def is_enabled(self) -> bool:
        return self.config.enabled

    @property
    def request_idempotency_enabled(self) -> bool:
        return self.is_enabled and self.config.request_enabled

    @property
    def task_idempotency_enabled(self) -> bool:
        return self.is_enabled and self.config.task_enabled

    def generate_content_hash(
        self, content_data: dict, _cache_type: CacheType = CacheType.REQUEST
    ) -> str:
        """Generate consistent hash for content verification"""

        # Sort and serialize for consistent hashing
        content_str = json.dumps(content_data, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()

    def generate_request_hash(
        self, method: str, path: str, body: bytes, headers: dict
    ) -> str:
        """Generate hash for request content"""

        # Include relevant headers but exclude volatile ones
        stable_headers = {
            k: v
            for k, v in headers.items()
            if k.lower()
            not in [
                "date",
                "timestamp",
                "x-request-id",
                "x-trace-id",
                "user-agent",
                "accept-encoding",
                "connection",
            ]
        }

        hash_content = {
            "method": method,
            "path": path,
            "body": body.decode("utf-8", errors="ignore") if body else "",
            "headers": stable_headers,
        }

        return self.generate_content_hash(hash_content, CacheType.REQUEST)

    def generate_task_hash(self, task_name: str, args: tuple, kwargs: dict) -> str:
        """Generate hash for task content"""

        hash_content = {
            "task_name": task_name,
            "args": args,
            "kwargs": {k: v for k, v in kwargs.items() if k != "idempotency_key"},
        }

        return self.generate_content_hash(hash_content, CacheType.TASK)

    async def check_request_idempotency(
        self,
        idempotency_key: str,
        method: str,
        path: str,
        content_hash: str,
        _client_id: str | None = None,
    ) -> IdempotencyResult:
        """Check if request is a duplicate and return cached response if available"""

        if not self.request_idempotency_enabled:
            return IdempotencyResult(is_duplicate=False)

        try:
            # Ensure database connection
            await Database.connect_db()

            # Look for existing cache entry with better indexing
            cached_entry = await self.db.idempotencycache.find_first(
                where={
                    "idempotency_key": idempotency_key,
                    "cache_type": CacheType.REQUEST,
                    "request_method": method,
                    "request_path": path,
                    "expires_at": {"gt": datetime.now(self.config.app_timezone_obj)},
                },
                # Add ordering for performance
                order={"created_at": "desc"},
            )

            if cached_entry:
                # Verify content matches if verification is enabled
                if (
                    self.config.idempotency_content_verification
                    and cached_entry.content_hash != content_hash
                ):
                    raise ApplicationError(
                        ErrorCode.VALIDATION_ERROR,
                        (
                            f"idempotency key {idempotency_key} "
                            f"was used with different request content"
                        ),
                    )

                # Return cached response
                return IdempotencyResult(
                    is_duplicate=True,
                    cached_response={
                        "status_code": cached_entry.response_status_code,
                        "body": cached_entry.response_body,
                        "headers": cached_entry.response_headers,
                    },
                    cache_id=cached_entry.id,
                    cache_type=CacheType.REQUEST,
                )

            return IdempotencyResult(is_duplicate=False)

        except Exception as e:
            self.logger.error(f"error checking request idempotency: {e}")
            # Fail open - allow request to proceed if idempotency check fails
            return IdempotencyResult(is_duplicate=False)

    async def check_task_idempotency(
        self, idempotency_key: str, task_name: str, content_hash: str
    ) -> IdempotencyResult:
        """Check if task is a duplicate and return cached result if available"""

        if not self.task_idempotency_enabled:
            return IdempotencyResult(is_duplicate=False)

        try:
            # Look for existing cache entry
            cached_entry = await self.db.idempotencycache.find_first(
                where={
                    "idempotency_key": idempotency_key,
                    "task_name": task_name,
                    "cache_type": CacheType.TASK,
                    "expires_at": {"gt": datetime.now(di["timezone"])},
                }
            )

            if cached_entry:
                # Verify content matches if verification is enabled
                if (
                    self.config.idempotency_content_verification
                    and cached_entry.content_hash != content_hash
                ):
                    self.logger.warning(
                        f"task idempotency key {idempotency_key} "
                        f"used with different content"
                    )
                    # For tasks, we might want to proceed rather than error
                    return IdempotencyResult(is_duplicate=False)

                # Return cached result
                return IdempotencyResult(
                    is_duplicate=True,
                    cached_response={"result": cached_entry.task_result},
                    cache_id=cached_entry.id,
                    cache_type=CacheType.TASK,
                )

            return IdempotencyResult(is_duplicate=False)

        except Exception as e:
            self.logger.error(f"error checking task idempotency: {e}")
            # Fail open - allow task to proceed if idempotency check fails
            return IdempotencyResult(is_duplicate=False)

    async def cache_request_response(
        self,
        idempotency_key: str,
        method: str,
        path: str,
        content_hash: str,
        response_status: int,
        response_body: Any,
        response_headers: dict,
        client_id: str | None = None,
    ) -> str:
        """Cache successful request response for future idempotency checks"""

        if not self.request_idempotency_enabled:
            return ""

        cache_id = str(uuid4())
        expires_at = datetime.now(di["timezone"]) + timedelta(
            hours=self.cache_ttl_hours
        )

        data = {
            "id": cache_id,
            "idempotency_key": idempotency_key,
            "request_method": method,
            "request_path": path,
            "client_id": client_id,
            "content_hash": content_hash,
            "response_status_code": response_status,
            "response_body": response_body,
            "response_headers": response_headers,
            "cache_type": CacheType.REQUEST,
            "expires_at": expires_at,
        }
        try:
            from app.common.utils import PrismaDataTransformer

            prisma_data = PrismaDataTransformer.prepare_data(data, "IdempotencyCache")
            await self.db.idempotencycache.create(data=prisma_data)

            self.logger.info(
                f"cached request response for idempotency key: {idempotency_key}"
            )
            return cache_id

        except Exception as e:
            self.logger.error(f"failed to cache request response: {e}")
            return ""

    async def cache_task_result(
        self, idempotency_key: str, task_name: str, content_hash: str, task_result: Any
    ) -> str:
        """Cache successful task result for future idempotency checks"""

        if not self.task_idempotency_enabled:
            return ""

        cache_id = str(uuid4())
        expires_at = datetime.now(di["timezone"]) + timedelta(
            hours=self.cache_ttl_hours
        )

        data = {
            "id": cache_id,
            "idempotency_key": idempotency_key,
            "task_name": task_name,
            "content_hash": content_hash,
            "task_result": task_result,
            "cache_type": CacheType.TASK,
            "expires_at": expires_at,
        }
        try:
            from app.common.utils import PrismaDataTransformer

            prisma_data = PrismaDataTransformer.prepare_data(data, "IdempotencyCache")
            await self.db.idempotencycache.create(data=prisma_data)

            self.logger.info(
                f"cached task result for idempotency key: {idempotency_key}"
            )
            return cache_id

        except Exception as e:
            self.logger.error(f"failed to cache task result: {e}")
            return ""

    async def cleanup_expired_entries(self) -> int:
        """Clean up expired idempotency cache entries"""

        try:
            result = await self.db.idempotencycache.delete_many(
                where={"expires_at": {"lt": datetime.now(di["timezone"])}}
            )

            deleted_count = result or 0
            if deleted_count > 0:
                self.logger.info(
                    f"cleaned up {deleted_count} expired idempotency entries"
                )

            return deleted_count

        except Exception as e:
            self.logger.error(f"failed to cleanup expired entries: {e}")
            return 0

    def extract_idempotency_key(self, headers: dict) -> str | None:
        """Extract and validate idempotency key from request headers."""

        for header_name in self.config.header_names:
            key = headers.get(header_name) or headers.get(header_name.lower())

            if key:
                key = str(key).strip()
                if not key:
                    continue

                # Check for valid characters (alphanumeric, hyphens, underscores)
                import re

                if not re.match(r"^[a-zA-Z0-9\-_]+$", key):
                    self.logger.warning(f"invalid idempotency key format: {key[:50]}")
                    continue

                # Truncate if too long
                if len(key) > self.config.max_key_length:
                    key = key[: self.config.max_key_length]
                    self.logger.info(
                        f"truncated idempotency key to "
                        f"{self.config.max_key_length} characters"
                    )

                return key
        return None

    def should_apply_request_idempotency(self, method: str, path: str) -> bool:
        """Determine if idempotency should be applied to this request"""

        if not self.request_idempotency_enabled:
            return False

        # Check HTTP method
        if method not in self.config.supported_methods:
            return False

        # Check excluded paths
        for excluded_path in self.config.excluded_paths:
            if path.startswith(excluded_path):
                return False

        return True
