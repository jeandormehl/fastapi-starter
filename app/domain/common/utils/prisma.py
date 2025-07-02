from typing import Any, ClassVar

from prisma import Json


class PrismaUtils:
    MODEL_JSON_FIELDS: ClassVar = {
        # 'RequestLog': {
        #     'body',
        #     'headers',
        #     'path_params',
        #     'query_params',
        #     'response_body',
        #     'response_headers',
        # },
        # 'TaskLog': {
        #     'task_args',
        #     'task_error',
        #     'task_kwargs',
        #     'task_labels',
        #     'task_result',
        # },
        # 'IdempotencyCache': {
        #     'response_body',
        #     'response_headers',
        #     'task_result',
        # },
        # Add other models as needed
    }

    @classmethod
    def prepare_json(cls, data: dict[str, Any], model_name: str) -> dict[str, Any]:
        json_fields = cls.MODEL_JSON_FIELDS.get(model_name, set())

        if not json_fields:
            return data

        prepared_data = data.copy()

        for field in json_fields:
            if field not in prepared_data:
                continue
            if prepared_data[field] is None:
                prepared_data[field] = Json(None)
                continue
            if (
                field in prepared_data and prepared_data[field] is not None
            ) and isinstance(prepared_data[field], dict | list):
                prepared_data[field] = Json(prepared_data[field])

        return prepared_data
