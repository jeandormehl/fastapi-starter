import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from kink import di
from prisma import Prisma
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest

from app.core.logging import get_logger
from app.domain.common.utils import DateTimeUtils

_logger = get_logger(__name__)


@dataclass
class MetricSource:
    """Represents a source of metrics."""

    name: str
    description: str
    endpoint: str | None = None
    collector: Any | None = None
    enabled: bool = True
    last_updated: datetime | None = None
    error_count: int = 0


@dataclass
class AggregatedMetrics:
    """Container for aggregated metrics from all sources."""

    prometheus_metrics: str = ''
    prisma_metrics: str = ''
    custom_metrics: dict[str, Any] = field(default_factory=dict)
    health_metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# noinspection PyMethodMayBeStatic
class MetricsAggregator:
    """Aggregates metrics from multiple sources into a unified view."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or REGISTRY
        self.sources: dict[str, MetricSource] = {}
        self.enabled = True
        self._last_aggregation: AggregatedMetrics | None = None
        self._setup_default_sources()

    def _setup_default_sources(self) -> None:
        """Set up default metric sources."""
        self.add_source(
            'prometheus',
            'Prometheus HTTP and system metrics',
            collector=self._collect_prometheus_metrics,
        )

        self.add_source(
            'prisma',
            'Prisma database operation metrics',
            collector=self._collect_prisma_metrics,
        )

        self.add_source(
            'health',
            'Application health and diagnostic metrics',
            collector=self._collect_health_metrics,
        )

    def add_source(
        self,
        name: str,
        description: str,
        endpoint: str | None = None,
        collector: Any | None = None,
        enabled: bool = True,
    ) -> None:
        """Add a new metrics source."""
        self.sources[name] = MetricSource(
            name=name,
            description=description,
            endpoint=endpoint,
            collector=collector,
            enabled=enabled,
        )
        _logger.info(f'added metrics source: {name}')

    def disable_source(self, name: str) -> None:
        """Disable a metrics source."""
        if name in self.sources:
            self.sources[name].enabled = False
            _logger.info(f'disabled metrics source: {name}')

    def enable_source(self, name: str) -> None:
        """Enable a metrics source."""
        if name in self.sources:
            self.sources[name].enabled = True
            _logger.info(f'enabled metrics source: {name}')

    async def _collect_prometheus_metrics(self) -> str:
        """Collect Prometheus metrics from the registry."""
        try:
            return generate_latest(self.registry).decode('utf-8')
        except Exception as e:
            _logger.error(f'failed to collect prometheus metrics: {e}')
            return ''

    async def _collect_prisma_metrics(self) -> str:
        """Collect Prisma database metrics."""
        try:
            return await di[Prisma].get_metrics(format='prometheus')
        except Exception as e:
            _logger.error(f'failed to collect prisma metrics: {e}')
            return ''

    async def _collect_health_metrics(self) -> dict[str, Any]:
        """Collect application health metrics."""
        try:
            import os  # noqa: PLC0415

            import psutil  # type: ignore [import-untyped] # noqa: PLC0415

            # System metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Process metrics
            process = psutil.Process(os.getpid())
            process_memory = process.memory_info()

            return {
                'system': {
                    'cpu_percent': cpu_percent,
                    'memory_total': memory.total,
                    'memory_available': memory.available,
                    'memory_percent': memory.percent,
                    'disk_total': disk.total,
                    'disk_free': disk.free,
                    'disk_percent': disk.percent,
                },
                'process': {
                    'pid': process.pid,
                    'memory_rss': process_memory.rss,
                    'memory_vms': process_memory.vms,
                    'cpu_percent': process.cpu_percent(),
                    'num_threads': process.num_threads(),
                    'create_time': process.create_time(),
                },
                'uptime_seconds': (
                    DateTimeUtils.now()
                    - datetime.fromtimestamp(process.create_time(), tz=di[ZoneInfo])
                ).total_seconds(),
            }
        except Exception as e:
            _logger.error(f'failed to collect health metrics: {e}')
            return {}

    async def collect_all_metrics(self) -> AggregatedMetrics:
        """Collect metrics from all enabled sources."""
        if not self.enabled:
            return AggregatedMetrics()

        aggregated = AggregatedMetrics()
        collection_tasks = []

        for source_name, source in self.sources.items():
            if source.enabled and source.collector:
                collection_tasks.append(self._collect_from_source(source_name, source))

        # Collect from all sources concurrently
        results = await asyncio.gather(*collection_tasks, return_exceptions=True)

        # Process results
        for source_name, result in zip(self.sources.keys(), results, strict=False):
            if isinstance(result, BaseException):
                self.sources[source_name].error_count += 1
                _logger.error(f'error collecting from {source_name}: {result}')

                continue

            self.sources[source_name].last_updated = DateTimeUtils.now()

            # Store results in appropriate fields
            if source_name == 'prometheus':
                aggregated.prometheus_metrics = result

            elif source_name == 'prisma':
                aggregated.prisma_metrics = result

            elif source_name == 'health':
                aggregated.health_metrics = result

            else:
                aggregated.custom_metrics[source_name] = result

        # Add metadata
        aggregated.metadata = {
            'sources': {
                name: {
                    'enabled': source.enabled,
                    'last_updated': (
                        source.last_updated.isoformat() if source.last_updated else None
                    ),
                    'error_count': source.error_count,
                    'description': source.description,
                }
                for name, source in self.sources.items()
            },
            'aggregation_time': aggregated.timestamp.isoformat(),
            'enabled': self.enabled,
        }

        self._last_aggregation = aggregated

        return aggregated

    async def _collect_from_source(self, source_name: str, source: MetricSource) -> Any:
        """Collect metrics from a specific source."""
        try:
            if source.collector:
                return await source.collector()
            _logger.warning(f'no collector defined for source: {source_name}')

            return None

        except Exception as e:
            _logger.error(f'failed to collect from {source_name}: {e}')

            raise

    def get_prometheus_format(self) -> str:
        """Get all metrics in Prometheus format."""
        if not self._last_aggregation:
            return ''

        # Start with Prometheus metrics
        output = self._last_aggregation.prometheus_metrics

        # Add Prisma metrics in Prometheus format
        if self._last_aggregation.prisma_metrics:
            output += '\n# Prisma Database Metrics\n'
            output += f'\n{self._last_aggregation.prisma_metrics}'

        # Add health metrics in Prometheus format
        if self._last_aggregation.health_metrics:
            output += '# Application Health Metrics\n'
            health = self._last_aggregation.health_metrics

            # System metrics
            if 'system' in health:
                for key, value in health['system'].items():
                    if isinstance(value, int | float):
                        output += f'system_{key} {value}\n'

            # Process metrics
            if 'process' in health:
                for key, value in health['process'].items():
                    if isinstance(value, int | float):
                        output += f'process_{key} {value}\n'

            # Uptime
            if 'uptime_seconds' in health:
                output += f'application_uptime_seconds {health["uptime_seconds"]}\n'

        return output

    def get_health_summary(self) -> dict[str, Any]:
        """Get a summary of metrics health for monitoring."""
        if not self._last_aggregation:
            return {'status': 'no_data', 'healthy': False}

        total_sources = len(self.sources)
        enabled_sources = sum(1 for s in self.sources.values() if s.enabled)
        error_sources = sum(1 for s in self.sources.values() if s.error_count > 0)

        healthy = (
            self.enabled
            and enabled_sources > 0
            and error_sources < total_sources / 2  # Less than half have errors
        )

        return {
            'status': 'healthy' if healthy else 'degraded',
            'healthy': healthy,
            'total_sources': total_sources,
            'enabled_sources': enabled_sources,
            'error_sources': error_sources,
            'last_aggregation': self._last_aggregation.timestamp.isoformat(),
            'uptime_seconds': (
                self._last_aggregation.health_metrics.get('uptime_seconds', 0)
                if self._last_aggregation.health_metrics
                else 0
            ),
        }
