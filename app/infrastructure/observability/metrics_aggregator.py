import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import psutil
from kink import di
from prisma import Prisma
from prometheus_client import REGISTRY, CollectorRegistry, generate_latest

from app.core.logging import get_logger
from app.domain.common.utils import DateTimeUtils

logger = get_logger(__name__)


@dataclass
class MetricSource:
    """Represents a source of metrics with enhanced metadata."""

    name: str
    description: str
    endpoint: str | None = None
    collector: Any | None = None
    enabled: bool = True
    last_updated: datetime | None = None
    error_count: int = 0
    success_count: int = 0
    average_collection_time: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)


@dataclass
class AggregatedMetrics:
    """Container for aggregated metrics."""

    prometheus_metrics: str = ''
    prisma_metrics: str = ''
    custom_metrics: dict[str, Any] = field(default_factory=dict)
    health_metrics: dict[str, Any] = field(default_factory=dict)
    performance_metrics: dict[str, Any] = field(default_factory=dict)
    business_metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    collection_duration: float = 0.0


# noinspection PyMethodMayBeStatic
class MetricsAggregator:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or REGISTRY
        self.sources: dict[str, MetricSource] = {}
        self.enabled = True
        self._last_aggregation: AggregatedMetrics | None = None
        self._collection_history: list[AggregatedMetrics] = []
        self._max_history_size = 100
        self._setup_default_sources()

    def _setup_default_sources(self) -> None:
        """Set up default metric sources."""
        self.add_source(
            'prometheus',
            'Prometheus HTTP and system metrics',
            collector=self._collect_prometheus_metrics,
            tags={'type': 'system', 'format': 'prometheus'},
        )

        self.add_source(
            'prisma',
            'Prisma database operation metrics',
            collector=self._collect_prisma_metrics,
            tags={'type': 'database', 'format': 'prometheus'},
        )

        self.add_source(
            'health',
            'Application health and diagnostic metrics',
            collector=self._collect_health_metrics,
            tags={'type': 'health', 'format': 'json'},
        )

        self.add_source(
            'performance',
            'Application performance metrics',
            collector=self._collect_performance_metrics,
            tags={'type': 'performance', 'format': 'json'},
        )

    def add_source(
        self,
        name: str,
        description: str,
        endpoint: str | None = None,
        collector: Any | None = None,
        enabled: bool = True,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Add a new metrics source with enhanced metadata."""
        self.sources[name] = MetricSource(
            name=name,
            description=description,
            endpoint=endpoint,
            collector=collector,
            enabled=enabled,
            tags=tags or {},
        )

    async def _collect_prometheus_metrics(self) -> str:
        """Collect Prometheus metrics."""
        try:
            start_time = DateTimeUtils.now()
            metrics = generate_latest(self.registry).decode('utf-8')
            collection_time = (DateTimeUtils.now() - start_time).total_seconds()

            # Update source statistics
            source = self.sources.get('prometheus')

            if source:
                source.success_count += 1
                source.average_collection_time = (
                    source.average_collection_time * (source.success_count - 1)
                    + collection_time
                ) / source.success_count

            return metrics
        except Exception as e:
            logger.exception(f'failed to collect prometheus metrics: {e}', exc_info=e)

            if 'prometheus' in self.sources:
                self.sources['prometheus'].error_count += 1

            return ''

    async def _collect_prisma_metrics(self) -> str:
        """Collect Prisma database metrics."""

        try:
            start_time = DateTimeUtils.now()
            prisma_client = di[Prisma]

            if not prisma_client:
                return ''

            # Try to get metrics in prometheus format
            metrics = await prisma_client.get_metrics(format='prometheus')
            collection_time = (DateTimeUtils.now() - start_time).total_seconds()

            # Update source statistics
            source = self.sources.get('prisma')
            if source:
                source.success_count += 1
                source.average_collection_time = (
                    source.average_collection_time * (source.success_count - 1)
                    + collection_time
                ) / source.success_count

            return metrics
        except Exception as e:
            logger.exception(f'failed to collect prisma metrics: {e}', exc_info=e)

            if 'prisma' in self.sources:
                self.sources['prisma'].error_count += 1

            return ''

    async def _collect_health_metrics(self) -> dict[str, Any]:
        """Collect comprehensive health metrics."""
        try:
            start_time = DateTimeUtils.now()

            # System metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            # Network metrics
            network = psutil.net_io_counters()

            # Process metrics
            process = psutil.Process(os.getpid())
            process_memory = process.memory_info()

            # Database connection health
            db_health = await self._check_database_health()

            collection_time = (DateTimeUtils.now() - start_time).total_seconds()

            health_data = {
                'system': {
                    'cpu_percent': cpu_percent,
                    'cpu_count': psutil.cpu_count(),
                    'memory_total': memory.total,
                    'memory_available': memory.available,
                    'memory_percent': memory.percent,
                    'memory_used': memory.used,
                    'disk_total': disk.total,
                    'disk_free': disk.free,
                    'disk_used': disk.used,
                    'disk_percent': disk.percent,
                    'network_bytes_sent': network.bytes_sent,
                    'network_bytes_recv': network.bytes_recv,
                    'network_packets_sent': network.packets_sent,
                    'network_packets_recv': network.packets_recv,
                },
                'process': {
                    'pid': process.pid,
                    'memory_rss': process_memory.rss,
                    'memory_vms': process_memory.vms,
                    'cpu_percent': process.cpu_percent(),
                    'num_threads': process.num_threads(),
                    'create_time': process.create_time(),
                    'num_fds': process.num_fds() if hasattr(process, 'num_fds') else 0,
                },
                'database': db_health,
                'uptime_seconds': (
                    DateTimeUtils.now()
                    - datetime.fromtimestamp(process.create_time(), tz=di[ZoneInfo])
                ).total_seconds(),
                'collection_time': collection_time,
            }

            # Update source statistics
            source = self.sources.get('health')

            if source:
                source.success_count += 1
                source.average_collection_time = (
                    source.average_collection_time * (source.success_count - 1)
                    + collection_time
                ) / source.success_count

            return health_data

        except Exception as e:
            logger.exception(f'failed to collect health metrics: {e}', exc_info=e)

            if 'health' in self.sources:
                self.sources['health'].error_count += 1

            return {}

    async def _collect_performance_metrics(self) -> dict[str, Any]:
        """Collect application performance metrics."""

        try:
            start_time = DateTimeUtils.now()

            # Get recent aggregation history for trend analysis
            recent_metrics = (
                self._collection_history[-10:] if self._collection_history else []
            )

            return {
                'metrics_collection': {
                    'average_collection_time': sum(
                        m.collection_duration for m in recent_metrics
                    )
                    / len(recent_metrics)
                    if recent_metrics
                    else 0,
                    'total_collections': len(self._collection_history),
                    'failed_collections': sum(
                        1 for source in self.sources.values() if source.error_count > 0
                    ),
                    'success_rate': self._calculate_success_rate(),
                },
                'source_performance': {
                    name: {
                        'success_count': source.success_count,
                        'error_count': source.error_count,
                        'average_collection_time': source.average_collection_time,
                        'success_rate': source.success_count
                        / (source.success_count + source.error_count)
                        if (source.success_count + source.error_count) > 0
                        else 0,
                    }
                    for name, source in self.sources.items()
                },
                'collection_time': (DateTimeUtils.now() - start_time).total_seconds(),
            }

        except Exception as e:
            logger.exception(f'failed to collect performance metrics: {e}', exc_info=e)

            return {}

    async def _check_database_health(self) -> dict[str, Any]:
        """Check database connectivity and health."""
        try:
            prisma_client = di[Prisma]

            if not prisma_client:
                return {'status': 'unavailable', 'connected': False}

            # Simple connectivity check
            start_time = DateTimeUtils.now()
            await prisma_client.execute_raw('SELECT 1')
            response_time = (DateTimeUtils.now() - start_time).total_seconds()

            return {
                'status': 'healthy',
                'connected': True,
                'response_time': response_time,
            }

        except Exception as e:
            logger.exception(f'database health check failed: {e}', exc_info=e)

            return {
                'status': 'unhealthy',
                'connected': False,
                'error': str(e),
            }

    def _calculate_success_rate(self) -> float:
        """Calculate overall success rate across all sources."""
        total_success = sum(source.success_count for source in self.sources.values())
        total_attempts = sum(
            source.success_count + source.error_count
            for source in self.sources.values()
        )

        return total_success / total_attempts if total_attempts > 0 else 0.0

    async def collect_all_metrics(self) -> AggregatedMetrics:
        """Collect metrics from all enabled sources."""
        if not self.enabled:
            return AggregatedMetrics()

        start_time = DateTimeUtils.now()
        aggregated = AggregatedMetrics()
        collection_tasks = []

        # Create collection tasks for enabled sources
        for source_name, source in self.sources.items():
            if source.enabled and source.collector:
                collection_tasks.append(self._collect_from_source(source_name, source))

        # Collect from all sources concurrently with timeout
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*collection_tasks, return_exceptions=True),
                timeout=30.0,  # 30 second timeout
            )

        except TimeoutError:
            logger.exception('metrics collection timed out')
            results = [Exception('collection timeout')] * len(collection_tasks)

        # Process results
        for source_name, result in zip(self.sources.keys(), results, strict=False):
            source = self.sources[source_name]

            if isinstance(result, BaseException):
                source.error_count += 1
                logger.exception(f'failed to collect from {source_name}: {result}')
                continue

            source.last_updated = DateTimeUtils.now()

            # Store results in appropriate fields based on source type
            if source_name == 'prometheus':
                aggregated.prometheus_metrics = result

            elif source_name == 'prisma':
                aggregated.prisma_metrics = result

            elif source_name == 'health':
                aggregated.health_metrics = result

            elif source_name == 'performance':
                aggregated.performance_metrics = result

            else:
                aggregated.custom_metrics[source_name] = result

        # Calculate collection duration
        collection_duration = (DateTimeUtils.now() - start_time).total_seconds()
        aggregated.collection_duration = collection_duration

        # Add comprehensive metadata
        aggregated.metadata = {
            'sources': {
                name: {
                    'enabled': source.enabled,
                    'last_updated': (
                        source.last_updated.isoformat() if source.last_updated else None
                    ),
                    'error_count': source.error_count,
                    'success_count': source.success_count,
                    'average_collection_time': source.average_collection_time,
                    'description': source.description,
                    'tags': source.tags,
                }
                for name, source in self.sources.items()
            },
            'aggregation_time': aggregated.timestamp.isoformat(),
            'collection_duration': collection_duration,
            'enabled': self.enabled,
            'total_sources': len(self.sources),
            'enabled_sources': sum(1 for s in self.sources.values() if s.enabled),
            'success_rate': self._calculate_success_rate(),
        }

        # Store in history
        self._last_aggregation = aggregated
        self._collection_history.append(aggregated)

        # Trim history if too large
        if len(self._collection_history) > self._max_history_size:
            self._collection_history = self._collection_history[
                -self._max_history_size :
            ]

        return aggregated

    async def _collect_from_source(self, source_name: str, source: MetricSource) -> Any:
        """Collect metrics from a specific source with timing."""
        try:
            if source.collector:
                return await source.collector()

            return None
        except Exception as e:
            logger.exception(f'error collecting from {source_name}: {e}', exc_info=e)

            raise

    def get_prometheus_format(self) -> str:  # noqa: PLR0912
        """Get all metrics in Prometheus format."""
        if not self._last_aggregation:
            return ''

        output_lines = []

        # Add Prometheus metrics
        if self._last_aggregation.prometheus_metrics:
            output_lines.append('# Application Metrics')
            output_lines.append(self._last_aggregation.prometheus_metrics)

        # Add Prisma metrics
        if self._last_aggregation.prisma_metrics:
            output_lines.append('# Prisma Database Metrics')
            output_lines.append(self._last_aggregation.prisma_metrics)

        # Convert health metrics to Prometheus format
        if self._last_aggregation.health_metrics:
            output_lines.append('# Health Metrics')
            health = self._last_aggregation.health_metrics

            # System metrics
            if 'system' in health:
                for key, value in health['system'].items():
                    if isinstance(value, int | float):
                        output_lines.append(f'system_{key} {value}')

            # Process metrics
            if 'process' in health:
                for key, value in health['process'].items():
                    if isinstance(value, int | float):
                        output_lines.append(f'process_{key} {value}')

            # Database metrics
            if 'database' in health and isinstance(health['database'], dict):
                db_status = 1 if health['database'].get('connected', False) else 0
                output_lines.append(f'database_connected {db_status}')
                if 'response_time' in health['database']:
                    output_lines.append(
                        f'database_response_time_seconds '
                        f'{health["database"]["response_time"]}'
                    )

            # Uptime
            if 'uptime_seconds' in health:
                output_lines.append(
                    f'application_uptime_seconds {health["uptime_seconds"]}'
                )

        # Add performance metrics
        if self._last_aggregation.performance_metrics:
            output_lines.append('# Application Performance Metrics')
            perf = self._last_aggregation.performance_metrics

            if 'metrics_collection' in perf:
                mc = perf['metrics_collection']
                for key, value in mc.items():
                    if isinstance(value, int | float):
                        output_lines.append(f'metrics_collection_{key} {value}')

        # Add collection metadata
        output_lines.append('# Collection Metadata')
        output_lines.append(
            f'metrics_collection_duration_seconds '
            f'{self._last_aggregation.collection_duration}'
        )
        output_lines.append(
            f'metrics_sources_total '
            f'{self._last_aggregation.metadata.get("total_sources", 0)}'
        )
        output_lines.append(
            f'metrics_sources_enabled '
            f'{self._last_aggregation.metadata.get("enabled_sources", 0)}'
        )
        output_lines.append(
            f'metrics_success_rate '
            f'{self._last_aggregation.metadata.get("success_rate", 0)}'
        )

        return '\n'.join(output_lines)

    def get_health_summary(self) -> dict[str, Any]:
        """Get comprehensive health summary for monitoring."""
        if not self._last_aggregation:
            return {'status': 'no_data', 'healthy': False}

        total_sources = len(self.sources)
        enabled_sources = sum(1 for s in self.sources.values() if s.enabled)
        error_sources = sum(1 for s in self.sources.values() if s.error_count > 0)
        success_rate = self._calculate_success_rate()

        # Determine health status
        if success_rate >= 0.95:
            status = 'healthy'

        elif success_rate >= 0.8:
            status = 'degraded'

        else:
            status = 'unhealthy'

        healthy = (
            self.enabled
            and enabled_sources > 0
            and success_rate >= 0.8
            and error_sources < total_sources / 2
        )

        return {
            'status': status,
            'healthy': healthy,
            'total_sources': total_sources,
            'enabled_sources': enabled_sources,
            'error_sources': error_sources,
            'success_rate': success_rate,
            'last_aggregation': self._last_aggregation.timestamp.isoformat(),
            'collection_duration': self._last_aggregation.collection_duration,
            'uptime_seconds': (
                self._last_aggregation.health_metrics.get('uptime_seconds', 0)
                if self._last_aggregation.health_metrics
                else 0
            ),
            'database_connected': (
                self._last_aggregation.health_metrics.get('database', {}).get(
                    'connected', False
                )
                if self._last_aggregation.health_metrics
                else False
            ),
        }

    def get_metrics_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent metrics collection history."""
        recent_history = (
            self._collection_history[-limit:] if self._collection_history else []
        )
        return [
            {
                'timestamp': metrics.timestamp.isoformat(),
                'collection_duration': metrics.collection_duration,
                'sources_collected': len(
                    [
                        k
                        for k, v in metrics.metadata.get('sources', {}).items()
                        if v.get('last_updated')
                    ]
                ),
            }
            for metrics in recent_history
        ]
