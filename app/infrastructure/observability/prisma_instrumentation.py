import functools
import time
from contextlib import asynccontextmanager
from typing import Any

from opentelemetry import trace

# noinspection PyProtectedMember
from opentelemetry.semconv._incubating.attributes.db_attributes import (
    DB_NAME,
    DB_OPERATION,
    DB_SYSTEM,
)
from opentelemetry.trace import Status, StatusCode
from prisma import Prisma
from prometheus_client import Counter, Histogram

from app.domain.common.utils import StringUtils

tracer = trace.get_tracer(__name__)

PRISMA_SLOW_QUERIES_TOTAL = Counter(
    'prisma_slow_queries_total',
    'Total number of slow Prisma queries',
    ['model', 'operation', 'threshold'],
)

PRISMA_QUERY_COMPLEXITY = Histogram(
    'prisma_query_complexity_score',
    'Complexity score of Prisma queries based on clauses',
    ['model', 'operation'],
    buckets=[1, 2, 3, 5, 8, 13, 21, 34, 55, 89],
)

PRISMA_TRANSACTION_DURATION = Histogram(
    'prisma_transaction_duration_seconds',
    'Duration of Prisma transactions',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

PRISMA_OPERATION_ERRORS = Counter(
    'prisma_operation_errors_total',
    'Total number of Prisma operation errors by type',
    ['model', 'operation', 'error_type'],
)

PRISMA_RESULT_SIZE = Histogram(
    'prisma_result_size_records',
    'Number of records returned by Prisma queries',
    ['model', 'operation'],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000],
)


# noinspection PyMethodMayBeStatic
class PrismaInstrumentation:
    """Prisma instrumentation."""

    def __init__(self) -> None:
        self._instrumented_clients: set[int] = set()
        self._operation_stats: dict[str, dict[str, Any]] = {}
        self._slow_query_threshold = 1.0  # seconds
        self._very_slow_query_threshold = 5.0  # seconds

    def instrument_client(self, client: Prisma) -> None:
        """Instrument a Prisma client instance with enhanced observability."""
        client_id = id(client)

        if client_id in self._instrumented_clients:
            return

        self._instrumented_clients.add(client_id)

        # Instrument model delegates
        self._instrument_model_delegates(client)

        # Instrument client methods
        self._instrument_client_methods(client)

    def _instrument_model_delegates(self, client: Prisma) -> None:
        """Instrument all model delegates with enhanced monitoring."""
        for attr_name in dir(client):
            if not attr_name.startswith('_'):
                attr = getattr(client, attr_name)
                if self._is_model_delegate(attr):
                    self._instrument_model_delegate(attr, attr_name)

    def _is_model_delegate(self, attr: Any) -> bool:
        """Check if an attribute is a Prisma model delegate."""
        return (
            hasattr(attr, '__class__')
            and hasattr(attr.__class__, '__name__')
            and any(
                hasattr(attr, method)
                for method in ['create', 'find_many', 'find_first', 'update', 'delete']
            )
        )

    def _instrument_model_delegate(self, model_delegate: Any, model_name: str) -> None:
        """Instrument all methods of a Prisma model delegate."""
        methods_to_instrument = [
            'create',
            'create_many',
            'find_first',
            'find_many',
            'find_unique',
            'update',
            'update_many',
            'delete',
            'delete_many',
            'upsert',
            'count',
            'aggregate',
            'group_by',
        ]

        for method_name in methods_to_instrument:
            if hasattr(model_delegate, method_name):
                original_method = getattr(model_delegate.__class__, method_name)

                if original_method and not getattr(
                    original_method, '__otel_patched__', False
                ):
                    instrumented_method = self._wrap_model_method(
                        original_method, model_name, method_name
                    )
                    setattr(model_delegate.__class__, method_name, instrumented_method)

    def _instrument_client_methods(self, client: Prisma) -> None:
        """Instrument client-level methods with enhanced monitoring."""
        client_methods = [
            'connect',
            'disconnect',
            'execute_raw',
            'query_raw',
            'transaction',
        ]

        for method_name in client_methods:
            if hasattr(client, method_name):
                original_method = getattr(client.__class__, method_name)

                if original_method and not getattr(
                    original_method, '__otel_patched__', False
                ):
                    instrumented_method = self._wrap_client_method(
                        original_method, method_name
                    )
                    setattr(client.__class__, method_name, instrumented_method)

    def _wrap_model_method(self, method: Any, model_name: str, operation: str) -> Any:  # noqa: PLR0915
        """Wrap a Prisma model method with comprehensive instrumentation."""

        @functools.wraps(method)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: PLR0915
            span_name = f'prisma.{model_name}.{operation}'
            start_time = time.time()

            with tracer.start_as_current_span(span_name) as span:
                # Add comprehensive span attributes
                span.set_attribute(DB_SYSTEM, 'postgresql')
                span.set_attribute(DB_NAME, model_name)
                span.set_attribute(DB_OPERATION, operation)
                span.set_attribute('prisma.model', model_name)
                span.set_attribute('prisma.operation', operation)
                span.set_attribute('service.name', StringUtils.service_name())

                # Calculate query complexity
                complexity_score = self._calculate_query_complexity(kwargs)
                span.set_attribute('prisma.query_complexity', complexity_score)

                # Add query parameters (sanitized)
                if kwargs:
                    span.set_attribute('prisma.query_params_count', len(kwargs))

                    # Add specific query info for common operations
                    if 'where' in kwargs:
                        span.set_attribute('prisma.has_where_clause', True)
                        span.set_attribute(
                            'prisma.where_conditions',
                            len(kwargs['where'])
                            if isinstance(kwargs['where'], dict)
                            else 1,
                        )
                    if 'include' in kwargs:
                        span.set_attribute('prisma.has_include', True)
                        span.set_attribute(
                            'prisma.include_relations',
                            len(kwargs['include'])
                            if isinstance(kwargs['include'], dict)
                            else 1,
                        )
                    if 'select' in kwargs:
                        span.set_attribute('prisma.has_select', True)
                        span.set_attribute(
                            'prisma.select_fields',
                            len(kwargs['select'])
                            if isinstance(kwargs['select'], dict)
                            else 1,
                        )
                    if 'orderBy' in kwargs:
                        span.set_attribute('prisma.has_order_by', True)
                    if 'take' in kwargs:
                        span.set_attribute('prisma.limit', kwargs['take'])
                    if 'skip' in kwargs:
                        span.set_attribute('prisma.offset', kwargs['skip'])

                try:
                    result = await method(*args, **kwargs)
                    duration = time.time() - start_time

                    # Record query complexity
                    PRISMA_QUERY_COMPLEXITY.labels(
                        model=model_name, operation=operation
                    ).observe(complexity_score)

                    # Add result metadata to span
                    result_count = self._add_result_metadata(span, result, operation)

                    # Record result size metrics
                    if result_count > 0:
                        PRISMA_RESULT_SIZE.labels(
                            model=model_name, operation=operation
                        ).observe(result_count)

                    # Handle slow queries with different thresholds
                    if duration > self._very_slow_query_threshold:
                        span.set_attribute('prisma.very_slow_query', True)
                        PRISMA_SLOW_QUERIES_TOTAL.labels(
                            model=model_name, operation=operation, threshold='very_slow'
                        ).inc()
                    elif duration > self._slow_query_threshold:
                        span.set_attribute('prisma.slow_query', True)
                        PRISMA_SLOW_QUERIES_TOTAL.labels(
                            model=model_name, operation=operation, threshold='slow'
                        ).inc()

                    # Update operation statistics
                    self._update_operation_stats(
                        model_name,
                        operation,
                        duration,
                        True,
                        complexity_score,
                        result_count,
                    )

                    return result

                except Exception as e:
                    duration = time.time() - start_time

                    # Record error metrics
                    error_type = type(e).__name__
                    PRISMA_OPERATION_ERRORS.labels(
                        model=model_name, operation=operation, error_type=error_type
                    ).inc()

                    # Add error information to span
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute('prisma.error', True)
                    span.set_attribute('prisma.error_type', error_type)
                    span.set_attribute(
                        'prisma.error_message', str(e)[:200]
                    )  # Truncate long messages

                    # Update operation statistics
                    self._update_operation_stats(
                        model_name, operation, duration, False, complexity_score, 0
                    )

                    raise

        wrapper.__otel_patched__ = True  # type: ignore [attr-defined]
        return wrapper

    def _wrap_client_method(self, method: Any, operation: str) -> Any:
        """Wrap a Prisma client method with comprehensive instrumentation."""

        @functools.wraps(method)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = f'prisma.client.{operation}'
            start_time = time.time()

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute(DB_SYSTEM, 'postgresql')
                span.set_attribute(DB_OPERATION, operation)
                span.set_attribute('prisma.operation', operation)
                span.set_attribute('service.name', StringUtils.service_name())

                try:
                    result = await method(*args, **kwargs)
                    duration = time.time() - start_time

                    # Special handling for raw queries
                    if operation in ['execute_raw', 'query_raw']:
                        span.set_attribute('prisma.raw_query', True)
                        if args:
                            # Don't log the actual query for security
                            span.set_attribute('prisma.has_raw_query', True)
                            span.set_attribute('prisma.raw_query_params', len(args))

                    # Special handling for transactions
                    if operation == 'transaction':
                        PRISMA_TRANSACTION_DURATION.observe(duration)
                        span.set_attribute('prisma.transaction_duration', duration)

                    return result

                except Exception as e:
                    # Record error metrics
                    error_type = type(e).__name__
                    PRISMA_OPERATION_ERRORS.labels(
                        model='client', operation=operation, error_type=error_type
                    ).inc()

                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.set_attribute('prisma.error_type', error_type)

                    raise

        wrapper.__otel_patched__ = True  # type: ignore [attr-defined]
        return wrapper

    def _calculate_query_complexity(self, kwargs: dict[str, Any]) -> int:
        """Calculate a complexity score for the query based on its structure."""
        complexity = 1  # Base complexity

        if 'where' in kwargs:
            where_clause = kwargs['where']
            if isinstance(where_clause, dict):
                complexity += len(where_clause)
                # Add complexity for nested conditions
                for value in where_clause.values():
                    if isinstance(value, dict):
                        complexity += 1

        if 'include' in kwargs:
            include_clause = kwargs['include']
            if isinstance(include_clause, dict):
                complexity += len(include_clause) * 2  # Relations are more expensive
            else:
                complexity += 2

        if 'select' in kwargs:
            select_clause = kwargs['select']
            if isinstance(select_clause, dict):
                complexity += len(select_clause)

        if 'orderBy' in kwargs:
            complexity += 1

        if 'take' in kwargs and kwargs['take'] > 100:
            complexity += 2  # Large result sets

        return min(complexity, 100)  # Cap at 100

    def _add_result_metadata(self, span: Any, result: Any, operation: str) -> int:
        """Add result metadata to the span and return result count."""
        result_count = 0

        if hasattr(result, '__len__') and not isinstance(result, str):
            result_count = len(result)
            span.set_attribute('db.rows_affected', result_count)
            span.set_attribute('prisma.result_count', result_count)
        elif isinstance(result, dict):
            if 'count' in result:
                result_count = result['count']
                span.set_attribute('db.rows_affected', result_count)
                span.set_attribute('prisma.result_count', result_count)
            elif operation in ['create', 'update', 'upsert'] and 'id' in result:
                result_count = 1
                span.set_attribute('db.rows_affected', 1)
                span.set_attribute('prisma.result_count', 1)
        elif result is not None and operation in ['create', 'update', 'upsert']:
            result_count = 1
            span.set_attribute('db.rows_affected', 1)
            span.set_attribute('prisma.result_count', 1)

        # Add result size category
        if result_count > 0:
            if result_count == 1:
                span.set_attribute('prisma.result_size_category', 'single')
            elif result_count <= 10:
                span.set_attribute('prisma.result_size_category', 'small')
            elif result_count <= 100:
                span.set_attribute('prisma.result_size_category', 'medium')
            elif result_count <= 1000:
                span.set_attribute('prisma.result_size_category', 'large')
            else:
                span.set_attribute('prisma.result_size_category', 'very_large')

        return result_count

    def _update_operation_stats(
        self,
        model: str,
        operation: str,
        duration: float,
        success: bool,
        complexity: int,
        result_count: int,
    ) -> None:
        """Update internal operation statistics with enhanced metrics."""
        key = f'{model}.{operation}'
        if key not in self._operation_stats:
            self._operation_stats[key] = {
                'total_calls': 0,
                'successful_calls': 0,
                'failed_calls': 0,
                'total_duration': 0.0,
                'min_duration': float('inf'),
                'max_duration': 0.0,
                'total_complexity': 0,
                'max_complexity': 0,
                'total_result_count': 0,
                'max_result_count': 0,
                'slow_queries': 0,
                'very_slow_queries': 0,
            }

        stats = self._operation_stats[key]
        stats['total_calls'] += 1
        stats['total_duration'] += duration
        stats['min_duration'] = min(stats['min_duration'], duration)
        stats['max_duration'] = max(stats['max_duration'], duration)
        stats['total_complexity'] += complexity
        stats['max_complexity'] = max(stats['max_complexity'], complexity)
        stats['total_result_count'] += result_count
        stats['max_result_count'] = max(stats['max_result_count'], result_count)

        if duration > self._very_slow_query_threshold:
            stats['very_slow_queries'] += 1
        elif duration > self._slow_query_threshold:
            stats['slow_queries'] += 1

        if success:
            stats['successful_calls'] += 1
        else:
            stats['failed_calls'] += 1

    def get_operation_stats(self) -> dict[str, dict[str, Any]]:
        """Get comprehensive operation statistics."""
        enhanced_stats = {}

        for key, stats in self._operation_stats.items():
            enhanced_stats[key] = {
                **stats,
                'average_duration': stats['total_duration'] / stats['total_calls']
                if stats['total_calls'] > 0
                else 0,
                'success_rate': stats['successful_calls'] / stats['total_calls']
                if stats['total_calls'] > 0
                else 0,
                'average_complexity': stats['total_complexity'] / stats['total_calls']
                if stats['total_calls'] > 0
                else 0,
                'average_result_count': stats['total_result_count']
                / stats['successful_calls']
                if stats['successful_calls'] > 0
                else 0,
                'slow_query_rate': stats['slow_queries'] / stats['total_calls']
                if stats['total_calls'] > 0
                else 0,
                'very_slow_query_rate': stats['very_slow_queries']
                / stats['total_calls']
                if stats['total_calls'] > 0
                else 0,
            }

        return enhanced_stats

    def get_health_metrics(self) -> dict[str, Any]:
        """Get health metrics for the Prisma instrumentation."""
        total_operations = sum(
            stats['total_calls'] for stats in self._operation_stats.values()
        )
        successful_operations = sum(
            stats['successful_calls'] for stats in self._operation_stats.values()
        )
        slow_queries = sum(
            stats['slow_queries'] for stats in self._operation_stats.values()
        )
        very_slow_queries = sum(
            stats['very_slow_queries'] for stats in self._operation_stats.values()
        )

        return {
            'total_operations': total_operations,
            'successful_operations': successful_operations,
            'success_rate': successful_operations / total_operations
            if total_operations > 0
            else 0,
            'instrumented_clients': len(self._instrumented_clients),
            'slow_query_threshold': self._slow_query_threshold,
            'very_slow_query_threshold': self._very_slow_query_threshold,
            'slow_queries': slow_queries,
            'very_slow_queries': very_slow_queries,
            'slow_query_rate': slow_queries / total_operations
            if total_operations > 0
            else 0,
            'very_slow_query_rate': very_slow_queries / total_operations
            if total_operations > 0
            else 0,
        }

    @asynccontextmanager
    async def transaction_context(self, client: Prisma, **kwargs: Any) -> Any:
        """Context manager for instrumented transactions."""
        with tracer.start_as_current_span('prisma.transaction') as span:
            span.set_attribute('prisma.operation', 'transaction')
            span.set_attribute('service.name', StringUtils.service_name())

            start_time = time.time()
            try:
                async with client.tx(**kwargs) as transaction:
                    yield transaction

                duration = time.time() - start_time
                PRISMA_TRANSACTION_DURATION.observe(duration)
                span.set_attribute('prisma.transaction_duration', duration)
                span.set_attribute('prisma.transaction_success', True)

            except Exception as e:
                duration = time.time() - start_time
                PRISMA_TRANSACTION_DURATION.observe(duration)
                PRISMA_OPERATION_ERRORS.labels(
                    model='client', operation='transaction', error_type=type(e).__name__
                ).inc()
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.set_attribute('prisma.transaction_success', False)

                raise
