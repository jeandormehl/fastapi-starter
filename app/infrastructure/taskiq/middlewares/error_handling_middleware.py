import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.constants import QUARANTINE_ERRORS
from app.core.errors.errors import ApplicationError, ErrorCode
from app.core.logging import get_logger
from app.infrastructure.taskiq.config import TaskiqConfiguration


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for task execution."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.failure_count = 0
        self.half_open_calls = 0
        self.last_failure_time: datetime | None = None
        self.state = CircuitBreakerState.CLOSED

    def can_execute(self) -> bool:
        """Check if task can be executed with improved state management."""

        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                return True

            return False

        # HALF_OPEN state
        return self.half_open_calls < self.half_open_max_calls

    def record_success(self) -> None:
        """Record successful execution with improved state transitions."""

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1

            if self.half_open_calls >= self.half_open_max_calls:
                self._reset()

        elif self.state == CircuitBreakerState.CLOSED:
            # Gradually reduce failure count on success
            self.failure_count = max(0, self.failure_count - 1)

    def record_failure(self) -> None:
        """Record failed execution."""

        self.failure_count += 1
        self.last_failure_time = datetime.now(di["timezone"])

        if (
            self.state == CircuitBreakerState.HALF_OPEN
            or self.failure_count >= self.failure_threshold
        ):
            self.state = CircuitBreakerState.OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset."""

        if self.last_failure_time is None:
            return True

        time_since_failure = datetime.now(di["timezone"]) - self.last_failure_time
        return time_since_failure.total_seconds() >= self.recovery_timeout

    def _reset(self) -> None:
        """Reset circuit breaker to closed state."""

        self.failure_count = 0
        self.half_open_calls = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED

    def get_state_info(self) -> dict[str, Any]:
        """Get detailed state information."""

        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "last_failure_time": self.last_failure_time.isoformat()
            if self.last_failure_time
            else None,
            "half_open_calls": self.half_open_calls,
            "can_execute": self.can_execute(),
        }


class ErrorHandlingMiddleware(TaskiqMiddleware):
    """Error handling with improved circuit breaker and adaptive retry."""

    def __init__(self, config: TaskiqConfiguration) -> None:
        super().__init__()

        self.config = config
        self.logger = get_logger(__name__)

        # Circuit breakers per task type with configuration
        self.circuit_breakers: dict[str, CircuitBreaker] = defaultdict(
            lambda: CircuitBreaker(
                failure_threshold=5, recovery_timeout=60, half_open_max_calls=3
            )
        )

        # Error tracking with performance optimization
        self.error_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self.error_patterns: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # Improved rate limiting with sliding window
        self.rate_limits: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Quarantine management
        self.quarantined_tasks: set[str] = set()
        self.quarantine_until: dict[str, datetime] = {}
        self.quarantine_reasons: dict[str, str] = {}

        # Performance metrics
        self.task_performance: dict[str, dict[str, float]] = defaultdict(
            lambda: {"avg_duration": 0.0, "max_duration": 0.0, "total_executions": 0}
        )

    def _should_quarantine_task(
        self, task_name: str, exception: Exception
    ) -> tuple[bool, str]:
        """Quarantine decision with detailed reasoning."""

        # Quarantine for specific error types
        error_type = type(exception).__name__
        if error_type in QUARANTINE_ERRORS:
            return True, f"error type {error_type} is in quarantine list"

        # Check for database connection issues
        if (
            "connection" in str(exception).lower()
            or "timeout" in str(exception).lower()
        ):
            return True, "database/connection related error detected"

        # Quarantine based on error frequency with sliding window
        now = datetime.now(di["timezone"])
        recent_window = now - timedelta(minutes=5)

        recent_errors = [
            error
            for error in self.error_history[task_name]
            if error["timestamp"] >= recent_window
        ]

        if len(recent_errors) >= 10:
            return (
                True,
                f"high error frequency: {len(recent_errors)} errors in 5 minutes",
            )

        # Check for consistent error patterns
        error_pattern_threshold = 0.8
        if len(recent_errors) >= 5:
            same_error_count = sum(
                1 for error in recent_errors if error["error_type"] == error_type
            )
            if same_error_count / len(recent_errors) >= error_pattern_threshold:
                return (
                    True,
                    f"consistent error pattern: "
                    f"{same_error_count}/{len(recent_errors)} same errors",
                )

        return False, ""

    def _calculate_adaptive_delay(self, task_name: str, retry_count: int) -> int:
        """Adaptive retry delay with performance-based adjustments."""

        base_delay = self.config.default_retry_delay

        # Exponential backoff with jitter
        exponential_delay = min(
            base_delay * (2**retry_count), self.config.max_retry_delay
        )

        # Performance-based adjustment
        performance = self.task_performance.get(task_name, {})
        avg_duration = performance.get("avg_duration", 0)

        # If task typically takes long, increase delay
        if avg_duration > 30:  # 30 seconds
            exponential_delay = int(exponential_delay * 1.5)

        # Adjust based on recent error rate
        recent_errors = self._get_recent_errors(task_name, minutes=10)
        if len(recent_errors) > 5:
            exponential_delay *= 2

        # Circuit breaker state adjustment
        circuit_breaker = self.circuit_breakers[task_name]
        if circuit_breaker.state == CircuitBreakerState.OPEN:
            exponential_delay *= 3

        # Secure jitter (±25%) using secrets instead of random
        jitter_range = int(exponential_delay * 0.25)
        jitter = secrets.randbelow(jitter_range * 2 + 1) - jitter_range

        return max(1, exponential_delay + jitter)

    def _get_recent_errors(self, task_name: str, minutes: int = 10) -> list:
        """Get recent errors within specified time window."""

        cutoff = datetime.now(di["timezone"]) - timedelta(minutes=minutes)
        return [
            error
            for error in self.error_history[task_name]
            if error["timestamp"] >= cutoff
        ]

    def _is_rate_limited(self, task_name: str) -> bool:
        """Rate limiting with sliding window."""

        now = datetime.now(di["timezone"])
        minute_ago = now - timedelta(minutes=1)

        # Clean old entries more efficiently
        rate_limit_queue = self.rate_limits[task_name]
        while rate_limit_queue and rate_limit_queue[0] < minute_ago:
            rate_limit_queue.popleft()

        # Dynamic rate limit based on task type and history
        max_failures_per_minute = self._calculate_rate_limit(task_name)
        return len(rate_limit_queue) >= max_failures_per_minute

    def _calculate_rate_limit(self, task_name: str) -> int:
        """Calculate dynamic rate limit based on task characteristics."""

        base_limit = 30

        # Adjust based on historical performance
        performance = self.task_performance.get(task_name, {})
        total_executions = performance.get("total_executions", 0)

        if total_executions > 1000:  # High-volume task
            return base_limit * 2
        if total_executions < 10:  # New or rare task
            return max(5, base_limit // 2)

        return base_limit

    def _update_error_patterns(self, task_name: str, exception: Exception) -> None:
        """Error pattern analysis."""

        error_type = type(exception).__name__
        error_message = str(exception)

        # Update error patterns
        self.error_patterns[task_name][error_type] += 1

        # Error history with more details
        error_entry = {
            "timestamp": datetime.now(di["timezone"]),
            "error_type": error_type,
            "error_message": error_message[:500],  # Limit message size
            "error_module": getattr(exception.__class__, "__module__", "unknown"),
            "circuit_breaker_state": self.circuit_breakers[task_name].state.value,
        }

        self.error_history[task_name].append(error_entry)

        # Update rate limiting
        self.rate_limits[task_name].append(datetime.now(di["timezone"]))

        # Clean up old patterns periodically
        if len(self.error_history[task_name]) % 50 == 0:
            self._cleanup_old_patterns(task_name)

    def _cleanup_old_patterns(self, task_name: str) -> None:
        """Clean up old error patterns to prevent memory growth."""

        cutoff = datetime.now(di["timezone"]) - timedelta(hours=24)

        # Clean error history
        error_queue = self.error_history[task_name]
        while error_queue and error_queue[0]["timestamp"] < cutoff:
            error_queue.popleft()

    def _create_comprehensive_error_context(
        self,
        message: TaskiqMessage,
        exception: Exception,
        result: TaskiqResult | None = None,
    ) -> dict[str, Any]:
        """Error context with better performance tracking."""

        circuit_breaker = self.circuit_breakers[message.task_name]

        context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception)[:1000],  # Limit size
            "exception_module": getattr(exception.__class__, "__module__", "unknown"),
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
            "retry_count": message.labels.get("retry_count", 0),
            "circuit_breaker": circuit_breaker.get_state_info(),
            "recent_error_count": len(self._get_recent_errors(message.task_name)),
            "is_quarantined": message.task_name in self.quarantined_tasks,
            "task_performance": self.task_performance.get(message.task_name, {}),
        }

        # Add error pattern analysis
        if message.task_name in self.error_patterns:
            context["error_patterns"] = dict(self.error_patterns[message.task_name])

        # Sanitized task context
        if self.config.sanitize_logs:
            context["task_args"] = (
                self._sanitize_data(message.args) if message.args else None
            )
            context["task_kwargs"] = (
                self._sanitize_data(message.kwargs) if message.kwargs else None
            )

        # Result context
        if result:
            context.update(
                {
                    "task_result_is_error": result.is_err,
                    "task_result_log": result.log[:500] if result.log else None,
                }
            )

        # ApplicationError details
        if isinstance(exception, ApplicationError):
            context.update(
                {
                    "app_error_code": exception.error_code.value,
                    "app_error_details": exception.details,
                    "app_error_status_code": exception.status_code,
                    "app_error_retryable": exception.error_code
                    not in {ErrorCode.VALIDATION_ERROR, ErrorCode.RESOURCE_NOT_FOUND},
                }
            )

        return context

    def _sanitize_data(self, data: Any) -> Any:
        """Data sanitization with better pattern matching."""

        sensitive_patterns = {
            "password",
            "passwd",
            "pwd",
            "pass",
            "token",
            "access_token",
            "refresh_token",
            "auth_token",
            "secret",
            "key",
            "api_key",
            "private_key",
            "auth",
            "authorization",
            "credential",
            "credentials",
            "ssn",
            "social_security",
            "credit_card",
            "cvv",
        }

        if isinstance(data, dict):
            return {
                key: "[REDACTED]"
                if any(pattern in key.lower() for pattern in sensitive_patterns)
                else self._sanitize_data(value)
                for key, value in data.items()
            }

        if isinstance(data, list | tuple):
            return [self._sanitize_data(item) for item in data]

        if isinstance(data, str) and len(data) > 1000:
            return data[:1000] + "...[TRUNCATED]"

        return data

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution checks."""

        task_name = message.task_name

        # Check quarantine status
        if task_name in self.quarantined_tasks:
            quarantine_end = self.quarantine_until.get(task_name)
            if quarantine_end and datetime.now(di["timezone"]) < quarantine_end:
                reason = self.quarantine_reasons.get(task_name, "Unknown reason")
                msg = (
                    f"task {task_name} is quarantined until {quarantine_end}: {reason}"
                )
                raise Exception(msg)

            # Remove from quarantine
            self._remove_from_quarantine(task_name)

        # Circuit breaker check
        circuit_breaker = self.circuit_breakers[task_name]
        if not circuit_breaker.can_execute():
            state_info = circuit_breaker.get_state_info()
            msg = (
                f"circuit breaker is {circuit_breaker.state.value} for task "
                f"{task_name}: {state_info}"
            )
            raise Exception(msg)

        # Rate limiting
        if self._is_rate_limited(task_name):
            recent_errors = len(self._get_recent_errors(task_name, minutes=1))
            msg = f"task {task_name} is rate limited ({recent_errors} recent errors)"
            raise Exception(msg)

        # Track execution start
        message.labels["execution_start"] = datetime.now(di["timezone"]).isoformat()

        return message

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Error handling with comprehensive analysis."""

        task_name = message.task_name

        # Update error tracking
        self._update_error_patterns(task_name, exception)

        # Update circuit breaker
        self.circuit_breakers[task_name].record_failure()

        # Check for quarantine with detailed reasoning
        should_quarantine, quarantine_reason = self._should_quarantine_task(
            task_name, exception
        )
        if should_quarantine:
            self._quarantine_task(task_name, quarantine_reason)

        # Update performance metrics
        self._update_performance_metrics(message, exception)

        # Create comprehensive error context
        error_context = self._create_comprehensive_error_context(
            message, exception, result
        )

        # Retry strategy analysis
        retry_count = message.labels.get("retry_count", 0)
        max_retries = self.config.default_retry_count

        if retry_count < max_retries and task_name not in self.quarantined_tasks:
            retry_delay = self._calculate_adaptive_delay(task_name, retry_count)
            error_context.update(
                {
                    "next_retry_delay": retry_delay,
                    "retry_strategy": "adaptive_backoff",
                    "retries_remaining": max_retries - retry_count,
                }
            )
        else:
            error_context["retry_strategy"] = (
                "exhausted" if retry_count >= max_retries else "quarantined"
            )

        # Logging based on error severity
        log_level = self._determine_log_level(exception, retry_count, max_retries)

        logger = self.logger.bind(**error_context)
        getattr(logger, log_level)(
            f"task '{task_name}' execution failed: {exception}",
            exc_info=log_level == "error",
        )

    def _quarantine_task(self, task_name: str, reason: str) -> None:
        """Quarantine task with detailed tracking."""

        quarantine_duration = timedelta(minutes=30)
        quarantine_end = datetime.now(di["timezone"]) + quarantine_duration

        self.quarantined_tasks.add(task_name)
        self.quarantine_until[task_name] = quarantine_end
        self.quarantine_reasons[task_name] = reason

        self.logger.warning(
            f"Task {task_name} quarantined: {reason}",
            extra={
                "quarantine_until": quarantine_end.isoformat(),
                "quarantine_reason": reason,
                "quarantine_duration_minutes": 30,
            },
        )

    def _remove_from_quarantine(self, task_name: str) -> None:
        """Remove task from quarantine."""

        self.quarantined_tasks.discard(task_name)
        self.quarantine_until.pop(task_name, None)
        reason = self.quarantine_reasons.pop(task_name, "Unknown")

        self.logger.info(
            f"task {task_name} removed from quarantine",
            extra={"previous_quarantine_reason": reason},
        )

    def _update_performance_metrics(
        self, message: TaskiqMessage, _exception: Exception
    ) -> None:
        """Update task performance metrics."""

        task_name = message.task_name
        start_time_str = message.labels.get("execution_start")

        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str)
                duration = (datetime.now(di["timezone"]) - start_time).total_seconds()

                performance = self.task_performance[task_name]
                performance["total_executions"] += 1

                # Update average duration (for failed executions)
                current_avg = performance["avg_duration"]
                total_execs = performance["total_executions"]
                performance["avg_duration"] = (
                    current_avg * (total_execs - 1) + duration
                ) / total_execs
                performance["max_duration"] = max(performance["max_duration"], duration)

            except (ValueError, TypeError) as e:
                self.logger.debug(f"failed to update performance metrics: {e}")

    def _determine_log_level(
        self, exception: Exception, retry_count: int, max_retries: int
    ) -> str:
        """Determine appropriate log level based on error characteristics."""

        # Application errors with specific codes should be warnings
        if isinstance(exception, ApplicationError) and exception.error_code in {
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.RESOURCE_NOT_FOUND,
        }:
            return "warning"

        # First few retries should be debug/info
        if retry_count < max_retries // 2:
            return "info"

        # Later retries should be warnings
        if retry_count < max_retries:
            return "warning"

        # Final failure should be error
        return "error"

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution success handling."""
        if not result.is_err:
            # Record success in circuit breaker
            self.circuit_breakers[message.task_name].record_success()

            # Update performance metrics for successful executions
            self._update_success_metrics(message)

    def _update_success_metrics(self, message: TaskiqMessage) -> None:
        """Update metrics for successful task execution."""

        task_name = message.task_name
        start_time_str = message.labels.get("execution_start")

        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str)
                duration = (datetime.now(di["timezone"]) - start_time).total_seconds()

                performance = self.task_performance[task_name]
                performance["total_executions"] += 1

                current_avg = performance["avg_duration"]
                total_execs = performance["total_executions"]
                performance["avg_duration"] = (
                    current_avg * (total_execs - 1) + duration
                ) / total_execs
                performance["max_duration"] = max(performance["max_duration"], duration)

            except (ValueError, TypeError) as e:
                self.logger.debug(f"failed to update success metrics: {e}")

    def get_error_statistics(self) -> dict[str, Any]:
        """Get comprehensive error statistics with details."""

        return {
            "circuit_breakers": {
                name: breaker.get_state_info()
                for name, breaker in self.circuit_breakers.items()
            },
            "quarantined_tasks": {
                task: {
                    "quarantine_until": self.quarantine_until.get(task, "").isoformat()
                    if self.quarantine_until.get(task)
                    else None,
                    "reason": self.quarantine_reasons.get(task, "Unknown"),
                }
                for task in self.quarantined_tasks
            },
            "error_patterns": {
                task: dict(patterns) for task, patterns in self.error_patterns.items()
            },
            "recent_error_counts": {
                task: len(self._get_recent_errors(task, minutes=60))
                for task in self.error_history
            },
            "performance_metrics": dict(self.task_performance),
            "rate_limiting": {
                task: len(rate_queue) for task, rate_queue in self.rate_limits.items()
            },
        }

    def reset_task_state(self, task_name: str) -> bool:
        """Reset all error state for a specific task."""

        try:
            # Reset circuit breaker
            if task_name in self.circuit_breakers:
                self.circuit_breakers[task_name]._reset()

            # Remove from quarantine
            if task_name in self.quarantined_tasks:
                self._remove_from_quarantine(task_name)

            # Clear error history
            if task_name in self.error_history:
                self.error_history[task_name].clear()

            # Clear error patterns
            if task_name in self.error_patterns:
                self.error_patterns[task_name].clear()

            # Clear rate limiting
            if task_name in self.rate_limits:
                self.rate_limits[task_name].clear()

            self.logger.info(f"reset error state for task: {task_name}")
            return True

        except Exception as e:
            self.logger.error(f"failed to reset task state for {task_name}: {e}")
            return False
