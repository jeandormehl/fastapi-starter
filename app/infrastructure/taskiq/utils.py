import glob
import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from taskiq import AsyncBroker, AsyncTaskiqDecoratedTask

from app.common.logging import get_logger


# noinspection PyUnresolvedReferences
class TaskAutodiscovery:
    """
    Utility class for autodiscovering and registering Taskiq tasks.
    """

    def __init__(self, broker: AsyncBroker, app_path: Path, root_path: Path) -> None:
        self.broker = broker
        self.app_path = app_path
        self.root_path = root_path
        self.logger = get_logger(__name__)

    def _find_task_files(self) -> list[str]:
        """
        Recursively find all files ending with _task.py,
        excluding __init__.py files.
        """

        pattern = str(self.app_path / "**" / "*_task.py")
        potential_files = glob.glob(pattern, recursive=True)

        return [f for f in potential_files if Path(f).name != "__init__.py"]

    def _import_task_module(self, file_path: str, module_name: str) -> ModuleType:
        """
        Dynamically import a module from a file path.
        """

        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            msg = f"cannot load task module from {file_path}"
            raise ImportError(msg)

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
            return module

        except Exception as e:
            if module_name in sys.modules:
                del sys.modules[module_name]

            msg = f"failed to execute module {module_name}: {e}"
            raise ImportError(msg)

    def _extract_tasks_from_module(
        self, module: ModuleType
    ) -> dict[str, dict[str, Any]]:
        """
        Extract task functions and their metadata from a module.
        """

        tasks = {}

        for _, obj in inspect.getmembers(module):
            if isinstance(obj, AsyncTaskiqDecoratedTask):
                metadata = {
                    "task_name": obj.task_name,
                    "labels": obj.labels,
                }
                tasks[obj.task_name] = {"func": obj, "meta": metadata}

        return tasks

    def _generate_module_name(self, file_path: str) -> str:
        """
        Generate a unique module name from a file path.
        """

        path_obj = Path(file_path)
        relative_path = path_obj.relative_to(self.root_path)
        module_parts = [*list(relative_path.parts[:-1]), relative_path.stem]

        return ".".join(module_parts).replace("-", "_")

    def _process_task_file(self, file_path: str) -> None:
        """
        Process a single task file and register its tasks.
        """

        module_name = self._generate_module_name(file_path)
        module = self._import_task_module(file_path, module_name)
        tasks = self._extract_tasks_from_module(module)

        for task_name, task_data in tasks.items():
            try:
                self.broker.register_task(
                    task_data["func"],
                    task_name=task_name,
                    **task_data["meta"]["labels"],
                )
                self.logger.info(f"registered new task - {task_name}")

            except Exception as e:
                self.logger.error(f"failed to register task: {task_name}")
                raise e

    def discover_and_register_tasks(self) -> dict[str, Any]:
        """
        Main method to discover and register all tasks.
        """
        task_files = self._find_task_files()

        for file_path in task_files:
            try:
                self._process_task_file(file_path)

            except Exception as e:
                self.logger.error(f"failed to process task file {file_path}: {e}")
                raise e
