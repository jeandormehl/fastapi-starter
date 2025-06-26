from fastapi.requests import Request


class ClientIPExtractor:
    """Utility for extracting client IP addresses."""

    @staticmethod
    def extract_client_ip(request: Request) -> str:
        """Extract client IP with proper proxy support."""

        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()

        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip.strip()

        return request.client.host if request.client else 'unknown'
