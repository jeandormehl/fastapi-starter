import asyncio
from datetime import datetime
from typing import Any, Literal

from fastapi import status
from kink import di

from app.common.base_handler import BaseHandler
from app.common.errors.errors import ExternalServiceError
from app.domain.v1.health.requests import HealthCheckRequest
from app.domain.v1.health.responses import HealthCheckResponse
from app.domain.v1.health.schemas import HealthCheckOutput
from app.domain.v1.health.services import HealthService


class HealthCheckHandler(BaseHandler):
    _SERVICE_DATABASE = "database"
    _SERVICE_TASKS = "tasks"
    _SERVICE_APPLICATION = "application"

    def __init__(self) -> None:
        super().__init__()

        self.health_svc = di[HealthService]

    async def _handle_internal(
        self, request: HealthCheckRequest
    ) -> HealthCheckResponse:
        start_time = datetime.now(di["timezone"])

        try:
            service_health_results = await self._perform_individual_health_checks()
            overall_status, status_code = self._determine_overall_status(
                service_health_results
            )

            end_time = datetime.now(di["timezone"])
            check_duration = (end_time - start_time).total_seconds() * 1000

            health_response_output = HealthCheckOutput(
                status=overall_status,
                timestamp=end_time.isoformat(),
                duration=check_duration,
                services=service_health_results,
            )

            if overall_status == "unhealthy":
                raise ExternalServiceError(
                    service_name="health_check",
                    message=f"system health check failed with status: {overall_status}",
                    response_status=status_code,
                    response_body=str(health_response_output.model_dump()),
                    trace_id=request.trace_id,
                    request_id=request.request_id,
                )

            return HealthCheckResponse(
                trace_id=request.trace_id,
                request_id=request.request_id,
                data=health_response_output,
            )

        except ExternalServiceError:
            raise

        except Exception as e:
            raise ExternalServiceError(
                service_name="health_check",
                message="health check system failure",
                trace_id=request.trace_id,
                request_id=request.request_id,
            ) from e

    async def _perform_individual_health_checks(self) -> dict[str, dict[str, Any]]:
        """
        Executes all individual service health checks concurrently.
        """

        results = await asyncio.gather(
            self.health_svc.check_database_health(),
            self.health_svc.check_taskiq_health(),
            self.health_svc.check_application_health(),
            return_exceptions=True,
        )

        # Map service names to their normalized results
        return {
            self._SERVICE_DATABASE: HealthService.normalize_health_result(
                results[0], self._SERVICE_DATABASE
            ),
            self._SERVICE_TASKS: HealthService.normalize_health_result(
                results[1], self._SERVICE_TASKS
            ),
            self._SERVICE_APPLICATION: HealthService.normalize_health_result(
                results[2], self._SERVICE_APPLICATION
            ),
        }

    def _determine_overall_status(
        self, service_health_results: dict[str, dict[str, Any]]
    ) -> tuple[Literal["healthy", "degraded", "unhealthy"], int]:
        """
        Determines the overall health status and corresponding HTTP status code
        based on individual service health results.
        """

        statuses = [s.get("status") for s in service_health_results.values()]

        if "unhealthy" in statuses:
            return "unhealthy", status.HTTP_503_SERVICE_UNAVAILABLE

        if "degraded" in statuses:
            return "degraded", status.HTTP_200_OK

        return "healthy", status.HTTP_200_OK
