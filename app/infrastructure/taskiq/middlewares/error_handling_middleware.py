from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from kink import di
from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from app.common.constants import QUARANTINE_ERRORS
from app.common.errors.error_response import ErrorSeverity, StandardErrorResponse
from app.common.errors.errors import (
    ApplicationError,
    ErrorCode,
    TaskError,
)
from app.common.logging import get_logger
from app.common.utils import DataSanitizer
from app.infrastructure.taskiq.config import TaskiqConfiguration


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Circuit breaker for task execution with adaptive behavior."""

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
        """Check if task can be executed."""

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
        """Record successful execution."""

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1

            if self.half_open_calls >= self.half_open_max_calls:
                self.reset()

        elif self.state == CircuitBreakerState.CLOSED:
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

    def reset(self) -> None:
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
    """
    Error handling middleware for Taskiq that provides standardized
    error responses, circuit breaker functionality, and comprehensive error tracking.
    """

    def __init__(self, config: TaskiqConfiguration) -> None:
        super().__init__()

        self.config = config
        self.logger = get_logger(__name__)

        # Circuit breakers per task type
        self.circuit_breakers: dict[str, CircuitBreaker] = defaultdict(
            lambda: CircuitBreaker(
                failure_threshold=5, recovery_timeout=60, half_open_max_calls=3
            )
        )

        # Error tracking with time-based cleanup
        self.error_history: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self.error_patterns: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # Rate limiting with sliding window
        self.rate_limits: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))

        # Quarantine management
        self.quarantined_tasks: set[str] = set()
        self.quarantine_until: dict[str, datetime] = {}
        self.quarantine_reasons: dict[str, str] = {}

        # Performance metrics
        self.task_performance: dict[str, dict[str, float]] = defaultdict(
            lambda: {"avg_duration": 0.0, "max_duration": 0.0, "total_executions": 0}
        )

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """Pre-execution validation and circuit breaker checks."""

        task_name = message.task_name
        trace_id = self._get_trace_id(message)
        request_id = self._get_request_id(message)

        # Check quarantine status
        if task_name in self.quarantined_tasks:
            quarantine_end = self.quarantine_until.get(task_name)

            if quarantine_end and datetime.now(di["timezone"]) < quarantine_end:
                reason = self.quarantine_reasons.get(task_name, "unknown reason")

                raise TaskError(
                    error_code=ErrorCode.TASK_QUARANTINED,
                    message=f"task is quarantined: {reason}",
                    task_name=task_name,
                    details={
                        "quarantine_until": quarantine_end.isoformat(),
                        "reason": reason,
                    },
                    trace_id=trace_id,
                    request_id=request_id,
                )

            # Remove from quarantine if expired
            self._remove_from_quarantine(task_name)

        # Circuit breaker check
        circuit_breaker = self.circuit_breakers[task_name]
        if not circuit_breaker.can_execute():
            state_info = circuit_breaker.get_state_info()

            raise TaskError(
                error_code=ErrorCode.TASK_EXECUTION_ERROR,
                message=f"circuit breaker is {circuit_breaker.state.value}",
                task_name=task_name,
                details={"circuit_breaker_state": state_info},
                trace_id=trace_id,
                request_id=request_id,
            )

        # Rate limiting check
        if self._is_rate_limited(task_name):
            recent_errors = len(self._get_recent_errors(task_name, minutes=1))

            raise TaskError(
                error_code=ErrorCode.TASK_RATE_LIMITED,
                message="task is rate limited due to recent errors",
                task_name=task_name,
                details={"recent_errors": recent_errors},
                trace_id=trace_id,
                request_id=request_id,
            )

        # Store execution start time
        message.labels["execution_start"] = datetime.now(di["timezone"]).isoformat()

        return message

    async def on_error(
        self, message: TaskiqMessage, result: TaskiqResult[Any], exception: Exception
    ) -> None:
        """Comprehensive error handling with standardized responses."""

        task_name = message.task_name

        # Convert to ApplicationError if not already
        if not isinstance(exception, ApplicationError):
            exception = TaskError(
                error_code=ErrorCode.TASK_EXECUTION_ERROR,
                message=str(exception),
                task_name=task_name,
                trace_id=message.kwargs.get("trace_id"),
                request_id=message.kwargs.get("request_id"),
                cause=exception,
            )

        # Update error tracking
        self._update_error_patterns(task_name, exception)

        # Update circuit breaker
        self.circuit_breakers[task_name].record_failure()

        # Check for quarantine conditions
        should_quarantine, quarantine_reason = self._should_quarantine_task(
            task_name, exception
        )
        if should_quarantine:
            self._quarantine_task(task_name, quarantine_reason)

        # Update performance metrics for failed executions
        self._update_execution_metrics(message)

        # Create comprehensive error context
        error_context = self._create_comprehensive_error_context(
            message, exception, result
        )

        # Create standardized error response
        error_response = self._create_standardized_error_response(
            message, exception, result
        )

        # Store error response in result metadata
        if hasattr(result, "metadata"):
            result.metadata = result.metadata or {}
            result.metadata["error_response"] = error_response.model_dump()

        # Log with appropriate severity
        severity = self._determine_error_severity(exception)
        log_method = getattr(
            self.logger.bind(**error_context),
            "critical" if severity == ErrorSeverity.CRITICAL else "error",
        )
        log_method(f"task '{task_name}' execution failed: {exception}")

    async def post_execute(
        self, message: TaskiqMessage, result: TaskiqResult[Any]
    ) -> None:
        """Post-execution success handling."""

        if not result.is_err:
            # Record success in circuit breaker
            self.circuit_breakers[message.task_name].record_success()

            # Update performance metrics for successful executions
            self._update_execution_metrics(message)

    def _should_quarantine_task(
        self, task_name: str, exception: Exception
    ) -> tuple[bool, str]:
        """Determine if task should be quarantined with detailed reasoning."""

        # Quarantine for specific error types
        error_type = type(exception).__name__
        if error_type in QUARANTINE_ERRORS:
            return True, f"error type {error_type} is in quarantine list"

        # Check for connection/infrastructure issues
        error_message = str(exception).lower()
        if any(
            keyword in error_message for keyword in ["connection", "timeout", "network"]
        ):
            return True, "infrastructure-related error detected"

        # Quarantine based on error frequency
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
        if len(recent_errors) >= 5:
            same_error_count = sum(
                1 for error in recent_errors if error["error_type"] == error_type
            )
            if same_error_count / len(recent_errors) >= 0.8:
                return (
                    True,
                    f"consistent error pattern: "
                    f"{same_error_count}/{len(recent_errors)} same errors",
                )

        return False, ""

    def _create_standardized_error_response(
        self,
        message: TaskiqMessage,
        exception: Exception,
        _result: TaskiqResult | None = None,
    ) -> StandardErrorResponse:
        """Create standardized error response for task failures."""

        trace_id = self._get_trace_id(message)
        request_id = self._get_request_id(message)
        severity = self._determine_error_severity(exception)

        # Get error code from ApplicationError or use default
        if isinstance(exception, ApplicationError):
            error_code = exception.error_code
            error_message = exception.message
            error_details = exception.details

        else:
            error_code = ErrorCode.TASK_EXECUTION_ERROR
            error_message = str(exception)
            error_details = {}

        return StandardErrorResponse.create(
            error="task execution error",
            message=error_message[:500],
            code=error_code.value,
            details={
                **error_details,
                "task_name": message.task_name,
                "task_id": message.task_id,
                "exception_type": type(exception).__name__,
                "exception_module": getattr(
                    exception.__class__, "__module__", "unknown"
                ),
                "retry_count": message.labels.get("retry_count", 0),
                "circuit_breaker_state": self.circuit_breakers[
                    message.task_name
                ].state.value,
                "is_quarantined": message.task_name in self.quarantined_tasks,
            },
            trace_id=trace_id,
            request_id=request_id,
            severity=severity,
        )

    def _determine_error_severity(self, exception: Exception) -> ErrorSeverity:
        """Determine error severity based on exception characteristics."""

        if isinstance(exception, ApplicationError):
            if exception.error_code in {
                ErrorCode.VALIDATION_ERROR,
                ErrorCode.RESOURCE_NOT_FOUND,
            }:
                return ErrorSeverity.LOW

            if exception.error_code in {
                ErrorCode.AUTHENTICATION_ERROR,
                ErrorCode.AUTHORIZATION_ERROR,
            }:
                return ErrorSeverity.MEDIUM

            if exception.error_code in {
                ErrorCode.TASK_QUARANTINED,
                ErrorCode.EXTERNAL_SERVICE_UNAVAILABLE,
                ErrorCode.DATABASE_CONNECTION,
            }:
                return ErrorSeverity.CRITICAL

            return ErrorSeverity.HIGH

        # Connection/timeout errors are critical
        error_message = str(exception).lower()

        if any(
            keyword in error_message for keyword in ["connection", "timeout", "network"]
        ):
            return ErrorSeverity.CRITICAL

        return ErrorSeverity.MEDIUM

    def _create_comprehensive_error_context(
        self,
        message: TaskiqMessage,
        exception: Exception,
        result: TaskiqResult | None = None,
    ) -> dict[str, Any]:
        """Create comprehensive error context for logging."""

        trace_id = self._get_trace_id(message)
        request_id = self._get_request_id(message)
        circuit_breaker = self.circuit_breakers[message.task_name]
        severity = self._determine_error_severity(exception)

        # Get error details from ApplicationError
        if isinstance(exception, ApplicationError):
            error_code = exception.error_code.value
            error_details = exception.details

        else:
            error_code = ErrorCode.TASK_EXECUTION_ERROR.value
            error_details = {}

        context = {
            "trace_id": trace_id,
            "request_id": request_id,
            "circuit_breaker": circuit_breaker.get_state_info(),
            "exception_code": error_code,
            "exception_details": error_details,
            "exception_message": str(exception)[:1000],
            "exception_module": getattr(exception.__class__, "__module__", "unknown"),
            "exception_type": type(exception).__name__,
            "is_quarantined": message.task_name in self.quarantined_tasks,
            "recent_error_count": len(self._get_recent_errors(message.task_name)),
            "retry_count": message.labels.get("retry_count", 0),
            "severity": severity.value,
            "task_id": message.task_id,
            "task_name": message.task_name,
            "task_performance": self.task_performance.get(message.task_name, {}),
            "timestamp": datetime.now(di["timezone"]).isoformat(),
        }

        # Add error pattern analysis
        if message.task_name in self.error_patterns:
            context["error_patterns"] = dict(self.error_patterns[message.task_name])

        # Add sanitized task context
        if self.config.sanitize_logs:
            context["task_args"] = (
                DataSanitizer.sanitize_data(message.args) if message.args else None
            )
            context["task_kwargs"] = (
                DataSanitizer.sanitize_data(message.kwargs) if message.kwargs else None
            )

        # Result context
        if result:
            context.update(
                {
                    "task_result_is_error": result.is_err,
                    "task_result_log": result.log[:500] if result.log else None,
                }
            )

        return context

    def _update_error_patterns(self, task_name: str, exception: Exception) -> None:
        """Update error pattern analysis with cleanup."""

        error_type = type(exception).__name__
        error_message = str(exception)

        # Update error patterns
        self.error_patterns[task_name][error_type] += 1

        # Add to error history
        error_entry = {
            "timestamp": datetime.now(di["timezone"]),
            "error_type": error_type,
            "error_message": error_message[:500],
            "error_module": getattr(exception.__class__, "__module__", "unknown"),
            "circuit_breaker_state": self.circuit_breakers[task_name].state.value,
        }

        self.error_history[task_name].append(error_entry)

        # Update rate limiting
        self.rate_limits[task_name].append(datetime.now(di["timezone"]))

        # Periodic cleanup
        if len(self.error_history[task_name]) % 50 == 0:
            self._cleanup_old_patterns(task_name)

    def _get_recent_errors(self, task_name: str, minutes: int = 10) -> list:
        """Get recent errors within specified time window."""

        cutoff = datetime.now(di["timezone"]) - timedelta(minutes=minutes)
        return [
            error
            for error in self.error_history[task_name]
            if error["timestamp"] >= cutoff
        ]

    def _is_rate_limited(self, task_name: str) -> bool:
        """Check if task is rate limited using sliding window."""

        now = datetime.now(di["timezone"])
        minute_ago = now - timedelta(minutes=1)

        # Clean old entries
        rate_limit_queue = self.rate_limits[task_name]
        while rate_limit_queue and rate_limit_queue[0] < minute_ago:
            rate_limit_queue.popleft()

        # Dynamic rate limit based on task characteristics
        max_failures_per_minute = self._calculate_rate_limit(task_name)
        return len(rate_limit_queue) >= max_failures_per_minute

    def _calculate_rate_limit(self, task_name: str) -> int:
        """Calculate dynamic rate limit based on task characteristics."""

        base_limit = 30
        performance = self.task_performance.get(task_name, {})
        total_executions = performance.get("total_executions", 0)

        if total_executions > 1000:  # High-volume task
            return base_limit * 2
        if total_executions < 10:  # New or rare task
            return max(5, base_limit // 2)

        return base_limit

    def _quarantine_task(self, task_name: str, reason: str) -> None:
        """Quarantine task with detailed tracking."""

        quarantine_duration = timedelta(minutes=30)
        quarantine_end = datetime.now(di["timezone"]) + quarantine_duration

        self.quarantined_tasks.add(task_name)
        self.quarantine_until[task_name] = quarantine_end
        self.quarantine_reasons[task_name] = reason

        self.logger.warning(
            f"task {task_name} quarantined: {reason}",
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

    def _update_execution_metrics(self, message: TaskiqMessage) -> None:
        """
        Update task performance metrics for both successful and failed executions.
        """

        task_name = message.task_name
        start_time_str = message.labels.get("execution_start")

        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str)
                duration = (datetime.now(di["timezone"]) - start_time).total_seconds()

                performance = self.task_performance[task_name]
                performance["total_executions"] += 1

                # Update average duration
                current_avg = performance["avg_duration"]
                total_execs = performance["total_executions"]
                performance["avg_duration"] = (
                    current_avg * (total_execs - 1) + duration
                ) / total_execs
                performance["max_duration"] = max(performance["max_duration"], duration)

            except (ValueError, TypeError) as e:
                self.logger.debug(f"failed to update execution metrics: {e}")

    def _cleanup_old_patterns(self, task_name: str) -> None:
        """Clean up old error patterns to prevent memory growth."""

        cutoff = datetime.now(di["timezone"]) - timedelta(hours=24)
        error_queue = self.error_history[task_name]

        while error_queue and error_queue[0]["timestamp"] < cutoff:
            error_queue.popleft()

    def get_error_statistics(self) -> dict[str, Any]:
        """Get comprehensive error statistics."""

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
                self.circuit_breakers[task_name].reset()

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

    def _get_trace_id(self, message: TaskiqMessage) -> str:
        return (
            message.labels.get("trace_id")
            if message.labels.get("trace_id", "unknown") != "unknown"
            else message.kwargs.get("trace_id")
        )

    def _get_request_id(self, message: TaskiqMessage) -> str:
        return (
            message.labels.get("request_id")
            if message.labels.get("request_id", "unknown") != "unknown"
            else message.kwargs.get("request_id")
        )
