from app.common.base_response import BaseResponse
from app.domain.v1.health.schemas import HealthCheckOutput


class HealthCheckResponse(BaseResponse):
    data: HealthCheckOutput
