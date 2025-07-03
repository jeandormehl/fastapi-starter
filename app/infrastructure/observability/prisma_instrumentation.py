import functools
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from prisma import Prisma

from app.domain.common.utils import StringUtils

tracer = trace.get_tracer(__name__)


# noinspection PyMethodMayBeStatic
class PrismaInstrumentation:
    def __init__(self) -> None:
        self._instrumented_clients: set[int] = set()
        self._connection_count = 0

    def instrument_client(self, client: Prisma) -> None:
        """Instrument a Prisma client instance with observability."""
        self._instrumented_clients.add(id(client))

        # Get all model attributes from the client
        for attr_name in dir(client):
            if not attr_name.startswith('_'):
                attr = getattr(client, attr_name)
                if (
                    hasattr(attr, '__class__')
                    and hasattr(attr.__class__, '__name__')
                    and (
                        hasattr(attr, 'create')
                        or hasattr(attr, 'find_many')
                        or hasattr(attr, 'find_first')
                    )
                ):
                    self._instrument_model_delegate(attr, attr_name)

        self._instrument_client_methods(client)

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
                    instrumented_method = self._wrap_method(
                        original_method, model_name, method_name
                    )

                    setattr(model_delegate.__class__, method_name, instrumented_method)

    def _instrument_client_methods(self, client: Any) -> None:
        """Instrument client-level methods like connect, disconnect, etc."""
        client_methods = ['connect', 'disconnect', 'execute_raw', 'query_raw']

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

    def _wrap_method(self, method: Any, model_name: str, operation: str) -> Any:
        """Wrap a Prisma model method with instrumentation."""

        @functools.wraps(method)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = f'prisma.{model_name}.{operation}'

            with tracer.start_as_current_span(span_name) as span:
                # Add span attributes
                span.set_attribute('db.name', model_name)
                span.set_attribute('db.operation', operation)
                span.set_attribute('db.system', 'postgresql')
                span.set_attribute('prisma.model', model_name)
                span.set_attribute('prisma.operation', operation)
                span.set_attribute('service.name', StringUtils.service_name())

                try:
                    result = await method(*args, **kwargs)

                    if hasattr(result, '__len__') and not isinstance(result, str):
                        span.set_attribute('db.rows_affected', len(result))

                    elif isinstance(result, dict) and 'count' in result:
                        span.set_attribute('db.rows_affected', result['count'])

                    return result

                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))

                    raise

        wrapper.__otel_patched__ = True  # type: ignore [attr-defined]

        return wrapper

    def _wrap_client_method(self, method: Any, operation: str) -> Any:
        """Wrap a Prisma client method with instrumentation."""

        @functools.wraps(method)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            span_name = f'prisma.client.{operation}'

            with tracer.start_as_current_span(span_name) as span:
                span.set_attribute('db.operation', operation)
                span.set_attribute('db.system', 'postgresql')
                span.set_attribute('prisma.operation', operation)
                span.set_attribute('service.name', StringUtils.service_name())

                try:
                    return await method(*args, **kwargs)

                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))

                    raise

        wrapper.__otel_patched__ = True  # type: ignore [attr-defined]

        return wrapper
