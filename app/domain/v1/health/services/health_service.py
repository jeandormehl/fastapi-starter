import time
from datetime import datetime
from typing import Any

from kink import di

from app import __version__
from app.core.config import Configuration
from app.infrastructure.database.db import Database
from app.infrastructure.taskiq.task_manager import TaskManager


class HealthService:
    """Centralized health checking service"""

    def __init__(self, config: Configuration) -> None:
        self.config = config

    async def check_database_health(self) -> dict[str, Any]:
        """Check database connectivity and status"""
        try:
            await Database.connect_db()
            db = di[Database]

            start_time = time.time()
            await db.query_raw("SELECT 1 as health_check")
            duration = time.time() - start_time

            return {
                "status": "healthy",
                "connected": db.is_connected(),
                "response_time_ms": round(duration * 1000, 2),
                "details": "database connection successful",
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e),
                "details": "database connection failed",
            }

    async def check_taskiq_health(self) -> dict[str, Any]:
        """Check TaskIQ broker and task manager health"""
        try:
            task_manager = di[TaskManager]
            health_data = await task_manager.health_check()

            # Determine overall health based on task manager status
            is_healthy = health_data.get("is_running", False)

            return {
                "status": "healthy" if is_healthy else "degraded",
                "task_manager": health_data,
                "details": "task_manager operational"
                if is_healthy
                else "task_manager not running",
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": "task_manager health check failed",
            }

    async def check_application_health(self) -> dict[str, Any]:
        """Check basic application health"""

        try:
            return {
                "status": "healthy",
                "server_time": datetime.now(di["timezone"]).isoformat(),
                "environment": self.config.app_environment,
                "version": __version__,
                "details": "application running normally",
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "details": "application health check failed",
            }

    @classmethod
    def normalize_health_result(cls, result: Any | Exception, service_name: str) -> Any:
        if isinstance(result, Exception):
            return {
                "status": "unhealthy",
                "error": str(result),
                "details": f"{service_name} health check raised an exception",
            }

        return result
