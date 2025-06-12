import asyncio
import atexit
import signal
import sys
import traceback
from collections import deque
from enum import Enum
from threading import Lock, Thread
from typing import Any

import httpx

from app.core.config import Configuration


class LogStreamType(str, Enum):
    """Log stream types for categorization."""

    API = "api"
    TASK = "task"
    ERROR = "error"
    METRICS = "metrics"


class ParseableSink:
    """Parseable sink with multiple stream support and intelligent routing."""

    def __init__(self, config: Configuration) -> None:
        self.config = config

        self.base_url = config.parseable_url
        self.username = config.parseable_username
        self.password = config.parseable_password.get_secret_value()

        # Stream configuration
        self.stream_names = {
            LogStreamType.API: config.parseable_api_stream,
            LogStreamType.TASK: config.parseable_task_stream,
            LogStreamType.ERROR: config.parseable_error_stream,
            LogStreamType.METRICS: config.parseable_metrics_stream,
        }

        # Batching configuration
        self.batch_size = getattr(config, "parseable_batch_size", 100)
        self.flush_interval = getattr(config, "parseable_flush_interval", 5.0)
        self.max_retries = getattr(config, "parseable_max_retries", 3)
        self.retry_delay = getattr(config, "parseable_retry_delay", 1.0)

        # Separate buffers for each stream
        self._buffers: dict[LogStreamType, deque] = {
            stream_type: deque() for stream_type in LogStreamType
        }
        self._locks: dict[LogStreamType, Lock] = {
            stream_type: Lock() for stream_type in LogStreamType
        }

        self._client: httpx.AsyncClient | None = None
        self._flush_task: asyncio.Task | None = None
        self._running = True
        self._loop: asyncio.AbstractEventLoop | None = None

        if config.parseable_enabled:
            self._start_background_processing()
            atexit.register(self.cleanup)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, _signum: Any, _frame: Any) -> None:
        """Handle shutdown signals gracefully."""

        self.cleanup()

    def _start_background_processing(self) -> None:
        """Start background thread for async processing."""

        def run_loop() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._background_processor())

        thread = Thread(target=run_loop, daemon=True)
        thread.start()

    async def _background_processor(self) -> None:
        """Background coroutine for processing log batches across all streams."""

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0), limits=httpx.Limits(max_connections=10)
        )

        try:
            while self._running:
                await asyncio.sleep(self.flush_interval)
                # Flush all streams
                for stream_type in LogStreamType:
                    if self._buffers[stream_type]:
                        await self._flush_buffer(stream_type)
        finally:
            await self._client.aclose()

    def _determine_stream_type(self, log_entry: dict[str, Any]) -> LogStreamType:
        """Intelligently determine which stream a log entry belongs to."""

        # Check for error indicators first
        if (
            log_entry.get("level") in ["ERROR", "CRITICAL", "WARNING"]
            or "error_category" in log_entry
            or "error_occured" in log_entry
            or "error_type" in log_entry
        ):
            return LogStreamType.ERROR

        # Check for metrics
        if (
            log_entry.get("event") == "metrics"
            or "memory_usage" in log_entry
            or "cpu_usage" in log_entry
            or "performance" in log_entry
        ):
            return LogStreamType.METRICS

        # Check for task-related logs
        if (
            log_entry.get("execution_environment") == "taskiq_worker"
            or "task_id" in log_entry
            or "task_name" in log_entry
            or "task_labels" in log_entry
            or "worker_id" in log_entry
        ):
            return LogStreamType.TASK

        # Check for API request logs
        if (
            log_entry.get("event") in ["request_started", "request_completed"]
            or "request_method" in log_entry
            or "request_url" in log_entry
            or "status_code" in log_entry
            or "duration_ms" in log_entry
        ):
            return LogStreamType.API

        # Default to application logs
        return LogStreamType.API

    def _create_stream_specific_entry(
        self, log_entry: dict[str, Any], stream_type: LogStreamType
    ) -> dict[str, Any]:
        """Create stream-specific log entry with relevant fields."""

        # TODO: Revist this and add more relevant fields to different categories.
        # Common fields for all streams
        base_fields = {
            "timestamp": log_entry.get("timestamp"),
            "level": log_entry.get("level"),
            "message": log_entry.get("message"),
            "trace_id": log_entry.get("trace_id"),
            "request_id": log_entry.get("request_id"),
            "logger": log_entry.get("logger"),
            "function": log_entry.get("function"),
            "line": log_entry.get("line"),
            "module": log_entry.get("module"),
            "file": log_entry.get("file"),
            "process_id": log_entry.get("process_id"),
            "thread_id": log_entry.get("thread_id"),
            "thread_name": log_entry.get("thread_name"),
        }

        # Stream-specific field sets
        if stream_type == LogStreamType.API:
            api_fields = {
                "event": log_entry.get("event"),
                "method": log_entry.get("method"),
                "url": log_entry.get("url"),
                "path": log_entry.get("path"),
                "path_params": log_entry.get("path_params"),
                "query_params": log_entry.get("query_params"),
                "headers": log_entry.get("headers"),
                "body": log_entry.get("body"),
                "content_type": log_entry.get("content_type"),
                "content_length": log_entry.get("content_length"),
                "client_ip": log_entry.get("client_ip"),
                "user_agent": log_entry.get("user_agent"),
                "status_code": log_entry.get("status_code"),
                "response_body": log_entry.get("response_body"),
                "response_headers": log_entry.get("response_headers"),
                "duration_ms": log_entry.get("duration_ms"),
                "start_time": log_entry.get("start_time"),
                "end_time": log_entry.get("end_time"),
            }
            log_fields = {**base_fields, **api_fields}

        if stream_type == LogStreamType.TASK:
            task_fields = {
                "event": log_entry.get("event"),
                "task_id": log_entry.get("task_id"),
                "task_name": log_entry.get("task_name"),
                "task_labels": log_entry.get("task_labels"),
                "task_args": log_entry.get("task_args"),
                "task_kwargs": log_entry.get("task_kwargs"),
                "execution_environment": log_entry.get("execution_environment"),
                "worker_id": log_entry.get("worker_id"),
                "broker_type": log_entry.get("broker_type"),
                "priority": log_entry.get("priority"),
                "queue": log_entry.get("queue"),
                "retry_count": log_entry.get("retry_count"),
                "max_retries": log_entry.get("max_retries"),
                "task_timeout": log_entry.get("task_timeout"),
                "memory_usage_mb": log_entry.get("memory_usage_mb"),
                "duration_ms": log_entry.get("duration_ms"),
                "start_time": log_entry.get("start_time"),
                "end_time": log_entry.get("end_time"),
                "task_result": log_entry.get("task_result"),
                "task_status": log_entry.get("task_status"),
            }
            log_fields = {**base_fields, **task_fields}

        if stream_type == LogStreamType.ERROR:
            error_fields = {
                "event": log_entry.get("event"),
                "exception_type": log_entry.get("exception_type"),
                "exception_message": log_entry.get("exception_message"),
                "exception_traceback": log_entry.get("exception_traceback"),
                "traceback": log_entry.get("traceback"),
                "error_code": log_entry.get("error_code"),
                "error_details": log_entry.get("error_details"),
                "context": log_entry.get("context"),
                "stack_trace": log_entry.get("stack_trace"),
                "severity": log_entry.get("severity"),
                # Include relevant request/task context for errors
                "request_method": log_entry.get("method"),
                "request_url": log_entry.get("url"),
                "task_name": log_entry.get("task_name"),
                "task_id": log_entry.get("task_id"),
            }
            log_fields = {**base_fields, **error_fields}

        if stream_type == LogStreamType.METRICS:
            metrics_fields = {
                "event": log_entry.get("event"),
                "memory_usage_mb": log_entry.get("memory_usage_mb"),
                "cpu_usage_percent": log_entry.get("cpu_usage_percent"),
                "duration_ms": log_entry.get("duration_ms"),
                "performance_metrics": log_entry.get("performance_metrics"),
                "system_metrics": log_entry.get("system_metrics"),
                "request_count": log_entry.get("request_count"),
                "task_count": log_entry.get("task_count"),
                "error_count": log_entry.get("error_count"),
            }
            log_fields = {**base_fields, **metrics_fields}

        return log_fields

    def log(self, message: Any) -> None:
        """Log message to appropriate Parseable stream (called by loguru)."""

        record = message.record
        try:
            extra_data = record.get("extra", {}).copy()

            # Handle exc_info properly
            if "exc_info" in extra_data:
                exc_info = extra_data.pop("exc_info")
                if exc_info and exc_info is not True:
                    try:
                        if isinstance(exc_info, tuple):
                            extra_data["exception_type"] = (
                                exc_info[0].__name__ if exc_info[0] else None
                            )
                            extra_data["exception_message"] = (
                                str(exc_info[1]) if exc_info[1] else None
                            )
                            extra_data["exception_traceback"] = (
                                traceback.format_exception(*exc_info)
                                if exc_info[2]
                                else None
                            )
                        else:
                            extra_data["exception_info"] = str(exc_info)
                    except Exception as e:
                        extra_data["exc_info_error"] = (
                            f"failed to process exc_info: {e}"
                        )

            # Handle non-serializable objects
            serializable_extra = {}
            for key, value in extra_data.items():
                try:
                    import json

                    json.dumps(value)
                    serializable_extra[key] = value
                except (TypeError, ValueError):
                    serializable_extra[key] = str(value)

            # Create base log entry
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

            # Determine stream and create stream-specific entry
            stream_type = self._determine_stream_type(log_entry)
            stream_entry = self._create_stream_specific_entry(log_entry, stream_type)

            # Remove None values to reduce field count
            stream_entry = {k: v for k, v in stream_entry.items() if v is not None}

            # Add to appropriate buffer
            with self._locks[stream_type]:
                self._buffers[stream_type].append(stream_entry)

                # Flush if buffer is full
                if (
                    len(self._buffers[stream_type]) >= self.batch_size
                    and self._loop
                    and not self._loop.is_closed()
                ):
                    asyncio.run_coroutine_threadsafe(
                        self._flush_buffer(stream_type), self._loop
                    )

        except Exception as e:
            print(f"parseable_sink error: {e}", file=sys.stderr)
            print(
                f"record data: {record if 'record' in locals() else 'unavailable'}",
                file=sys.stderr,
            )

    async def _flush_buffer(self, stream_type: LogStreamType) -> None:
        """Flush buffered logs for a specific stream."""

        if not self._buffers[stream_type]:
            return

        # Get batch from buffer
        with self._locks[stream_type]:
            batch = list(self._buffers[stream_type])
            self._buffers[stream_type].clear()

        if not batch:
            return

        # Attempt to send with retries
        for attempt in range(self.max_retries + 1):
            try:
                await self._send_batch(batch, stream_type)
                return  # Success

            except Exception as e:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (2**attempt))
                    continue
                print(
                    f"parseable_sink: failed to send batch to {stream_type.value} "
                    f"after {self.max_retries} retries: {e}",
                    file=sys.stderr,
                )
                break

    async def _send_batch(
        self, batch: list[dict[str, Any]], stream_type: LogStreamType
    ) -> None:
        """Send a batch of logs to specific Parseable stream."""

        if not self._client:
            msg = "http client not initialized"
            raise RuntimeError(msg)

        url = f"{self.base_url}/api/v1/ingest"

        headers = {
            "Content-Type": "application/json",
            "X-P-Stream": self.stream_names[stream_type],
            "User-Agent": f"parseable-sink-{stream_type.value}/1.0",
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
                f"parseable_sink ({stream_type.value}): http error "
                f"{e.response.status_code}: {e.response.text}",
                file=sys.stderr,
            )
            raise

        except httpx.RequestError as e:
            print(
                f"parseable_sink ({stream_type.value}): request error: {e}",
                file=sys.stderr,
            )
            raise

    def cleanup(self) -> None:
        """Cleanup resources and flush remaining logs."""

        self._running = False

        # Flush any remaining logs for all streams
        if self._loop and not self._loop.is_closed():
            try:
                for stream_type in LogStreamType:
                    if self._buffers[stream_type]:
                        future = asyncio.run_coroutine_threadsafe(
                            self._flush_buffer(stream_type), self._loop
                        )
                        future.result(timeout=10.0)

            except Exception as e:
                print(f"parseable_sink cleanup error: {e}", file=sys.stderr)
