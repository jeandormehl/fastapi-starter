from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.core.constants import QUARANTINE_ERRORS
from app.core.errors.exceptions import AppException, ErrorCode
from app.core.logging import get_logger
from app.infrastructure.taskiq.config import TaskiqConfiguration


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for task execution."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: datetime | None = None
        self.state = CircuitBreakerState.CLOSED

    def can_execute(self) -> bool:
        """Check if task can be executed."""

        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            if (
                datetime.now(di["timezone"]) - self.last_failure_time
            ).seconds >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False

        # HALF_OPEN state
        return True

    def record_success(self) -> None:
        """Record successful execution."""

        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED

    def record_failure(self) -> None:
        """Record failed execution."""

        self.failure_count += 1
        self.last_failure_time = datetime.now(di["timezone"])

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN


class ErrorHandlingMiddleware(TaskiqMiddleware):
    """Error handling with circuit breaker and adaptive retry."""

    def __init__(self, config: TaskiqConfiguration):
        super().__init__()

        self.config = config
        self.logger = get_logger(__name__)

        # Circuit breakers per task type
        self.circuit_breakers: dict[str, CircuitBreaker] = defaultdict(
            lambda: CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        )

        # Error tracking
        self.error_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.error_patterns: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # Rate limiting
        self.rate_limits: dict[str, deque] = defaultdict(lambda: deque(maxlen=60))

        # Quarantine
        self.quarantined_tasks: set[str] = set()
        self.quarantine_until: dict[str, datetime] = {}

    def _should_quarantine_task(self, task_name: str, exception: Exception) -> bool:
        """Determine if task should be quarantined."""

        # Quarantine for specific error types
        quarantine_errors = QUARANTINE_ERRORS

        error_type = type(exception).__name__
        if error_type in quarantine_errors:
            return True

        # Quarantine based on error frequency
        recent_errors = [
            error
            for error in self.error_history[task_name]
            if datetime.now(di["timezone"]) - error["timestamp"] < timedelta(minutes=5)
        ]

        return len(recent_errors) >= 10

    def _calculate_adaptive_delay(self, task_name: str, retry_count: int) -> int:
        """Calculate adaptive retry delay based on error patterns."""

        base_delay = self.config.default_retry_delay

        # Exponential backoff with jitter
        exponential_delay = min(
            base_delay * (2**retry_count), self.config.max_retry_delay
        )

        # Adjust based on recent error rate
        recent_errors = len(
            [
                error
                for error in self.error_history[task_name]
                if datetime.now(di["timezone"]) - error["timestamp"]
                < timedelta(minutes=10)
            ]
        )

        if recent_errors > 5:
            exponential_delay *= 2  # Double delay for frequently failing tasks

        # Add jitter (±25%)
        import random

        jitter = random.uniform(0.75, 1.25)

        return int(exponential_delay * jitter)

    def _is_rate_limited(self, task_name: str) -> bool:
        """Check if task is rate limited."""

        now = datetime.now(di["timezone"])
        minute_ago = now - timedelta(minutes=1)

        # Clean old entries
        while (
            self.rate_limits[task_name] and self.rate_limits[task_name][0] < minute_ago
        ):
            self.rate_limits[task_name].popleft()

        # Check if rate limit exceeded (max 30 failures per minute)
        return len(self.rate_limits[task_name]) >= 30

    def _update_error_patterns(self, task_name: str, exception: Exception) -> None:
        """Update error pattern analysis."""
        error_type = type(exception).__name__
        self.error_patterns[task_name][error_type] += 1

        # Record error in history
        self.error_history[task_name].append(
            {
                "timestamp": datetime.now(di["timezone"]),
                "error_type": error_type,
                "error_message": str(exception)[:200],
            }
        )

        # Update rate limiting
        self.rate_limits[task_name].append(datetime.now(di["timezone"]))

    def _create_comprehensive_error_context(
        self,
        message: TaskiqMessage,
        exception: Exception,
        result: TaskiqResult | None = None,
    ) -> dict[str, Any]:
        """Create comprehensive error context with enhanced details."""

        context = {
            "task_id": message.task_id,
            "task_name": message.task_name,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "exception_module": getattr(exception.__class__, "__module__", "unknown"),
            "timestamp": datetime.now(di["timezone"]).isoformat(),
            "trace_id": message.kwargs.get("trace_id"),
            "request_id": message.kwargs.get("request_id"),
            "retry_count": message.labels.get("retry_count", 0),
            "circuit_breaker_state": self.circuit_breakers[
                message.task_name
            ].state.value,
            "recent_error_count": len(self.error_history[message.task_name]),
            "is_quarantined": message.task_name in self.quarantined_tasks,
        }

        # Add error pattern analysis
        if message.task_name in self.error_patterns:
            context["error_patterns"] = dict(self.error_patterns[message.task_name])

        # Add task context
        if self.config.sanitize_logs:
            context["task_args"] = (
                self._sanitize_data(message.args) if message.args else None
            )
            context["task_kwargs"] = (
                self._sanitize_data(message.kwargs) if message.kwargs else None
            )

        # Add result context if available
        if result:
            context.update(
                {
                    "task_result_is_error": result.is_err,
                    "task_result_log": result.log,
                }
            )

        # Add AppException details
        if isinstance(exception, AppException):
            context.update(
                {
                    "app_error_code": exception.error_code.value,
                    "app_error_details": exception.details,
                    "app_error_status_code": exception.status_code,
                }
            )

        return context

    def _sanitize_data(self, data: Any) -> Any:
        """Sanitize sensitive data for logging."""
        if isinstance(data, dict):
            return {
                key: "[REDACTED]"
                if any(
                    sensitive in key.lower()
                    for sensitive in ["password", "secret", "token", "key", "auth"]
                )
                else self._sanitize_data(value)
                for key, value in data.items()
            }

        if isinstance(data, list | tuple):
            return [self._sanitize_data(item) for item in data]

        return data

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution checks with circuit breaker."""
        task_name = message.task_name

        # Check if task is quarantined
        if task_name in self.quarantined_tasks:
            quarantine_end = self.quarantine_until.get(task_name)
            if quarantine_end and datetime.now(di["timezone"]) < quarantine_end:
                msg = f"task {task_name} is quarantined until {quarantine_end}"
                raise Exception(msg)

            # Remove from quarantine
            self.quarantined_tasks.discard(task_name)
            self.quarantine_until.pop(task_name, None)

        # Check circuit breaker
        circuit_breaker = self.circuit_breakers[task_name]
        if not circuit_breaker.can_execute():
            msg = f"circuit breaker is OPEN for task {task_name}"
            raise Exception(msg)

        # Check rate limiting
        if self._is_rate_limited(task_name):
            msg = f"task {task_name} is rate limited"
            raise Exception(msg)

        return message

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Enhanced error handling with adaptive strategies."""
        task_name = message.task_name

        # Update error tracking
        self._update_error_patterns(task_name, exception)

        # Update circuit breaker
        self.circuit_breakers[task_name].record_failure()

        # Check for quarantine
        if self._should_quarantine_task(task_name, exception):
            self.quarantined_tasks.add(task_name)
            self.quarantine_until[task_name] = datetime.now(di["timezone"]) + timedelta(
                minutes=30
            )

            self.logger.warning(
                f"task {task_name} quarantined due to repeated failures",
                extra={
                    "quarantine_until": self.quarantine_until[task_name].isoformat()
                },
            )

        # Create comprehensive error context
        error_context = self._create_comprehensive_error_context(
            message, exception, result
        )

        # Determine retry strategy
        retry_count = message.labels.get("retry_count", 0)
        max_retries = self.config.default_retry_count

        if retry_count < max_retries and task_name not in self.quarantined_tasks:
            # Calculate adaptive delay
            retry_delay = self._calculate_adaptive_delay(task_name, retry_count)
            error_context["next_retry_delay"] = retry_delay
            error_context["retry_strategy"] = "adaptive_backoff"
        else:
            error_context["retry_strategy"] = (
                "exhausted" if retry_count >= max_retries else "quarantined"
            )

        # Log error with enhanced context
        log_level = (
            "warning"
            if isinstance(exception, AppException)
            and exception.error_code
            in {ErrorCode.VALIDATION_ERROR, ErrorCode.RESOURCE_NOT_FOUND}
            else "error"
        )

        logger = self.logger.bind(**error_context)
        getattr(logger, log_level)(f"task '{task_name}' execution failed: {exception}")

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution success handling."""
        if not result.is_err:
            # Record success in circuit breaker
            self.circuit_breakers[message.task_name].record_success()

    def get_error_statistics(self) -> dict[str, Any]:
        """Get comprehensive error statistics."""
        return {
            "circuit_breakers": {
                name: {
                    "state": breaker.state.value,
                    "failure_count": breaker.failure_count,
                    "last_failure": breaker.last_failure_time.isoformat()
                    if breaker.last_failure_time
                    else None,
                }
                for name, breaker in self.circuit_breakers.items()
            },
            "quarantined_tasks": list(self.quarantined_tasks),
            "error_patterns": {
                task: dict(patterns) for task, patterns in self.error_patterns.items()
            },
            "recent_error_counts": {
                task: len(errors) for task, errors in self.error_history.items()
            },
        }
