from app.common.base_response import BaseResponse
from app.domain.v1.task_logs.schemas import TaskLogCleanupOutput


class TaskLogCleanupResponse(BaseResponse):
    data: TaskLogCleanupOutput
