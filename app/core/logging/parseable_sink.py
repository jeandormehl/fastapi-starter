import asyncio
import atexit
import signal
import sys
import traceback
from collections import deque
from threading import Lock, Thread
from typing import Any

import httpx

from app.core.config import Configuration


class ParseableSink:
    """Parseable sink with improved reliability and error handling."""

    def __init__(self, config: Configuration):
        self.config = config

        self.base_url = config.parseable_url
        self.stream_name = config.parseable_stream
        self.username = config.parseable_username
        self.password = config.parseable_password.get_secret_value()

        # Batching configuration
        self.batch_size = getattr(config, "parseable_batch_size", 100)
        self.flush_interval = getattr(config, "parseable_flush_interval", 5.0)
        self.max_retries = getattr(config, "parseable_max_retries", 3)
        self.retry_delay = getattr(config, "parseable_retry_delay", 1.0)

        # Internal state
        self._buffer: deque = deque()
        self._lock = Lock()
        self._client: httpx.AsyncClient | None = None
        self._flush_task: asyncio.Task | None = None
        self._running = True
        self._loop: asyncio.AbstractEventLoop | None = None

        # Start background processing
        self._start_background_processing()

        # Register cleanup handlers
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    # noinspection PyUnusedLocal
    def _signal_handler(self, signum, frame):  # noqa: ARG002
        """Handle shutdown signals gracefully."""
        self.cleanup()

    def _start_background_processing(self):
        """Start background thread for async processing."""

        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._background_processor())

        thread = Thread(target=run_loop, daemon=True)
        thread.start()

    async def _background_processor(self):
        """Background coroutine for processing log batches."""

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0), limits=httpx.Limits(max_connections=10)
        )

        try:
            while self._running:
                await asyncio.sleep(self.flush_interval)
                if self._buffer:
                    await self._flush_buffer()
        finally:
            await self._client.aclose()

    def log(self, message):
        """Log message to Parseable (called by loguru)."""

        try:
            # Parse loguru record
            record = message.record

            # Extract extra data and handle special cases
            extra_data = record.get("extra", {}).copy()

            # Handle exc_info properly - convert to string representation
            if "exc_info" in extra_data:
                exc_info = extra_data.pop("exc_info")
                if exc_info and exc_info is not True:
                    try:
                        if isinstance(exc_info, tuple):
                            # Format exception tuple
                            extra_data["exception_type"] = (
                                exc_info[0].__name__ if exc_info[0] else None
                            )
                            extra_data["exception_message"] = (
                                str(exc_info[1]) if exc_info[1] else None
                            )
                            # noinspection PyArgumentList
                            extra_data["exception_traceback"] = (
                                traceback.format_exception(*exc_info)
                                if exc_info[2]
                                else None
                            )
                        else:
                            # Handle other exc_info formats
                            extra_data["exception_info"] = str(exc_info)
                    except Exception as e:
                        extra_data["exc_info_error"] = (
                            f"failed to process exc_info: {e}"
                        )

            # Handle other non-serializable objects in extra
            serializable_extra = {}
            for key, value in extra_data.items():
                try:
                    # Test serialization
                    import json

                    json.dumps(value)
                    serializable_extra[key] = value
                except (TypeError, ValueError):
                    # Convert non-serializable objects to string
                    serializable_extra[key] = str(value)

            # Create structured log entry with safe serialization
            log_entry = {
                "timestamp": record["time"].isoformat(),
                "level": record["level"].name,
                "logger": record["name"],
                "function": record["function"],
                "line": record["line"],
                "message": record["message"],
                "module": record["module"],
                "file": record["file"].name if record["file"] else None,
                "process_id": record.get("process").id,
                "thread_id": record.get("thread").id,
                "thread_name": record.get("thread").name,
                **serializable_extra,
            }

            # Add to buffer
            with self._lock:
                self._buffer.append(log_entry)

                # Flush if buffer is full
                if (
                    len(self._buffer) >= self.batch_size
                    and self._loop
                    and not self._loop.is_closed()
                ):
                    asyncio.run_coroutine_threadsafe(self._flush_buffer(), self._loop)

        except Exception as e:
            # Fallback logging to avoid recursion
            print(f"parseable_sink error: {e}", file=sys.stderr)
            # noinspection PyUnboundLocalVariable
            print(
                f"record data: {record if 'record' in locals() else 'unavailable'}",
                file=sys.stderr,
            )

    async def _flush_buffer(self):
        """Flush buffered logs to Parseable."""

        if not self._buffer:
            return

        # Get batch from buffer
        with self._lock:
            batch = list(self._buffer)
            self._buffer.clear()

        if not batch:
            return

        # Attempt to send with retries
        for attempt in range(self.max_retries + 1):
            try:
                await self._send_batch(batch)
                return  # Success

            except Exception as e:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
                    continue
                # Final attempt failed - log error and discard batch
                print(
                    f"parseable_sink: failed to send batch after "
                    f"{self.max_retries} retries: {e}",
                    file=sys.stderr,
                )
                print(f"batch size: {len(batch)}", file=sys.stderr)
                break

    async def _send_batch(self, batch: list[dict[str, Any]]):
        """Send a batch of logs to Parseable."""
        if not self._client:
            msg = "http client not initialized"
            raise RuntimeError(msg)

        url = f"{self.base_url}/api/v1/ingest"

        headers = {
            "Content-Type": "application/json",
            "X-P-Stream": self.stream_name,
            "User-Agent": "fastapi-starter-parseable-sink/1.0",
        }

        auth = (
            (self.username, self.password) if self.username and self.password else None
        )

        try:
            response = await self._client.post(
                url, json=batch, headers=headers, auth=auth, timeout=30.0
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(
                f"parseable_sink: HTTP error "
                f"{e.response.status_code}: {e.response.text}",
                file=sys.stderr,
            )
            raise
        except httpx.RequestError as e:
            print(f"parseable_sink: Request error: {e}", file=sys.stderr)
            raise

    def cleanup(self):
        """Cleanup resources and flush remaining logs."""

        self._running = False

        # Flush any remaining logs synchronously
        if self._buffer and self._loop and not self._loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._flush_buffer(), self._loop
                )
                future.result(timeout=10.0)  # Wait up to 10 seconds
            except Exception as e:
                print(f"parseable_sink cleanup error: {e}", file=sys.stderr)
