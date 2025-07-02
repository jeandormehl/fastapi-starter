from fastapi import Request


class ContextExtractor:
    """Utility for extracting trace and request context information."""

    _DEFAULT_UNKNOWN = 'unknown'

    @staticmethod
    def _extract_from_state_or_headers(
        request: Request, state_attr: str, header_name: str
    ) -> str:
        if hasattr(request, 'state') and hasattr(request.state, state_attr):
            value = getattr(request.state, state_attr, None)
            if value:
                return str(value)

        header_value = request.headers.get(header_name)
        if header_value:
            return header_value

        return ContextExtractor._DEFAULT_UNKNOWN

    @staticmethod
    def get_trace_id(request: Request) -> str:
        return ContextExtractor._extract_from_state_or_headers(
            request, 'trace_id', 'x-trace-id'
        )

    @staticmethod
    def get_request_id(request: Request) -> str:
        return ContextExtractor._extract_from_state_or_headers(
            request, 'request_id', 'x-request-id'
        )

    @staticmethod
    def get_idempotency_key(request: Request) -> str:
        return ContextExtractor._extract_from_state_or_headers(
            request, 'idempotency_key', 'x-idempotency-key'
        )
