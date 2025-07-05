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

from .prisma_instrumentation import (
    PrismaInstrumentation,
)

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
    prisma_instrumentation_metrics: dict[str, Any] = field(default_factory=dict)
    custom_metrics: dict[str, Any] = field(default_factory=dict)
    health_metrics: dict[str, Any] = field(default_factory=dict)
    performance_metrics: dict[str, Any] = field(default_factory=dict)
    business_metrics: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    collection_duration: float = 0.0


# noinspection PyMethodMayBeStatic, PyBroadException
class MetricsAggregator:
    def __init__(
        self,
        registry: CollectorRegistry | None = None,
        prisma_instrumentation: PrismaInstrumentation | None = None,
    ) -> None:
        self.registry = registry or REGISTRY
        self.prisma_instrumentation = (
            prisma_instrumentation or di[PrismaInstrumentation]
        )
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

        # Add Prisma instrumentation metrics source
        if self.prisma_instrumentation:
            self.add_source(
                'prisma_instrumentation',
                'Prisma instrumentation metrics and statistics',
                collector=self._collect_prisma_instrumentation_metrics,
                tags={'type': 'database', 'format': 'json'},
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

    async def _collect_prisma_instrumentation_metrics(self) -> dict[str, Any]:
        """Collect enhanced Prisma instrumentation metrics and statistics."""
        if not self.prisma_instrumentation:
            return {}

        try:
            start_time = DateTimeUtils.now()

            # Get operation statistics
            operation_stats = self.prisma_instrumentation.get_operation_stats()

            # Get health metrics
            health_metrics = self.prisma_instrumentation.get_health_metrics()

            # Calculate aggregated insights
            insights = self._calculate_prisma_insights(operation_stats)

            collection_time = (DateTimeUtils.now() - start_time).total_seconds()

            instrumentation_data = {
                'operation_statistics': operation_stats,
                'health_metrics': health_metrics,
                'insights': insights,
                'collection_metadata': {
                    'collection_time': collection_time,
                    'total_operations_tracked': len(operation_stats),
                    'instrumented_clients': health_metrics.get(
                        'instrumented_clients', 0
                    ),
                },
                'performance_analysis': {
                    'slowest_operations': self._get_slowest_operations(operation_stats),
                    'most_complex_operations': self._get_most_complex_operations(
                        operation_stats
                    ),
                    'highest_volume_operations': self._get_highest_volume_operations(
                        operation_stats
                    ),
                    'error_prone_operations': self._get_error_prone_operations(
                        operation_stats
                    ),
                },
                'thresholds': {
                    'slow_query_threshold': health_metrics.get(
                        'slow_query_threshold', 1.0
                    ),
                    'very_slow_query_threshold': health_metrics.get(
                        'very_slow_query_threshold', 5.0
                    ),
                },
            }

            # Update source statistics
            source = self.sources.get('prisma_instrumentation')
            if source:
                source.success_count += 1
                source.average_collection_time = (
                    source.average_collection_time * (source.success_count - 1)
                    + collection_time
                ) / source.success_count

            return instrumentation_data

        except Exception:
            if 'prisma_instrumentation' in self.sources:
                self.sources['prisma_instrumentation'].error_count += 1

            return {}

    def _calculate_prisma_insights(
        self, operation_stats: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Calculate insights from Prisma operation statistics."""
        if not operation_stats:
            return {}

        total_operations = sum(
            stats['total_calls'] for stats in operation_stats.values()
        )
        total_successful = sum(
            stats['successful_calls'] for stats in operation_stats.values()
        )
        total_slow_queries = sum(
            stats.get('slow_queries', 0) for stats in operation_stats.values()
        )
        total_very_slow_queries = sum(
            stats.get('very_slow_queries', 0) for stats in operation_stats.values()
        )

        # Calculate averages
        avg_duration = (
            sum(stats['average_duration'] for stats in operation_stats.values())
            / len(operation_stats)
            if operation_stats
            else 0
        )
        avg_complexity = (
            sum(
                stats.get('average_complexity', 0) for stats in operation_stats.values()
            )
            / len(operation_stats)
            if operation_stats
            else 0
        )

        # Find patterns
        read_operations = [
            k
            for k in operation_stats
            if any(op in k.lower() for op in ['find', 'count', 'aggregate'])
        ]
        write_operations = [
            k
            for k in operation_stats
            if any(op in k.lower() for op in ['create', 'update', 'delete', 'upsert'])
        ]

        read_stats = {k: v for k, v in operation_stats.items() if k in read_operations}
        write_stats = {
            k: v for k, v in operation_stats.items() if k in write_operations
        }

        return {
            'overall': {
                'total_operations': total_operations,
                'success_rate': total_successful / total_operations
                if total_operations > 0
                else 0,
                'slow_query_rate': total_slow_queries / total_operations
                if total_operations > 0
                else 0,
                'very_slow_query_rate': total_very_slow_queries / total_operations
                if total_operations > 0
                else 0,
                'average_duration': avg_duration,
                'average_complexity': avg_complexity,
            },
            'operation_patterns': {
                'read_operations_count': len(read_operations),
                'write_operations_count': len(write_operations),
                'read_vs_write_ratio': len(read_operations) / len(write_operations)
                if write_operations
                else float('inf'),
            },
            'performance_patterns': {
                'read_operations_avg_duration': sum(
                    stats['average_duration'] for stats in read_stats.values()
                )
                / len(read_stats)
                if read_stats
                else 0,
                'write_operations_avg_duration': sum(
                    stats['average_duration'] for stats in write_stats.values()
                )
                / len(write_stats)
                if write_stats
                else 0,
                'read_operations_avg_complexity': sum(
                    stats.get('average_complexity', 0) for stats in read_stats.values()
                )
                / len(read_stats)
                if read_stats
                else 0,
                'write_operations_avg_complexity': sum(
                    stats.get('average_complexity', 0) for stats in write_stats.values()
                )
                / len(write_stats)
                if write_stats
                else 0,
            },
        }

    def _get_slowest_operations(
        self, operation_stats: dict[str, dict[str, Any]], limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get the slowest operations by average duration."""
        sorted_ops = sorted(
            operation_stats.items(),
            key=lambda x: x[1]['average_duration'],
            reverse=True,
        )

        return [
            {
                'operation': op_name,
                'average_duration': stats['average_duration'],
                'max_duration': stats['max_duration'],
                'total_calls': stats['total_calls'],
                'slow_queries': stats.get('slow_queries', 0),
            }
            for op_name, stats in sorted_ops[:limit]
        ]

    def _get_most_complex_operations(
        self, operation_stats: dict[str, dict[str, Any]], limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get the most complex operations by average complexity."""
        sorted_ops = sorted(
            operation_stats.items(),
            key=lambda x: x[1].get('average_complexity', 0),
            reverse=True,
        )

        return [
            {
                'operation': op_name,
                'average_complexity': stats.get('average_complexity', 0),
                'max_complexity': stats.get('max_complexity', 0),
                'total_calls': stats['total_calls'],
                'average_duration': stats['average_duration'],
            }
            for op_name, stats in sorted_ops[:limit]
            if stats.get('average_complexity', 0) > 0
        ]

    def _get_highest_volume_operations(
        self, operation_stats: dict[str, dict[str, Any]], limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get the highest volume operations by total calls."""
        sorted_ops = sorted(
            operation_stats.items(), key=lambda x: x[1]['total_calls'], reverse=True
        )

        return [
            {
                'operation': op_name,
                'total_calls': stats['total_calls'],
                'average_duration': stats['average_duration'],
                'total_duration': stats['total_duration'],
                'success_rate': stats['success_rate'],
            }
            for op_name, stats in sorted_ops[:limit]
        ]

    def _get_error_prone_operations(
        self, operation_stats: dict[str, dict[str, Any]], limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get the most error-prone operations by failure rate."""
        error_ops = [
            (op_name, stats)
            for op_name, stats in operation_stats.items()
            if stats['failed_calls'] > 0
        ]

        sorted_ops = sorted(
            error_ops,
            key=lambda x: x[1]['failed_calls'] / x[1]['total_calls'],
            reverse=True,
        )

        return [
            {
                'operation': op_name,
                'failed_calls': stats['failed_calls'],
                'total_calls': stats['total_calls'],
                'failure_rate': stats['failed_calls'] / stats['total_calls'],
                'success_rate': stats['success_rate'],
            }
            for op_name, stats in sorted_ops[:limit]
        ]

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

            # Prisma instrumentation health
            prisma_instrumentation_health = {}
            if self.prisma_instrumentation:
                prisma_instrumentation_health = (
                    self.prisma_instrumentation.get_health_metrics()
                )

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
                'prisma_instrumentation': prisma_instrumentation_health,
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

            # Prisma performance analysis
            prisma_performance = {}
            if (
                self.prisma_instrumentation
                and self._last_aggregation
                and self._last_aggregation.prisma_instrumentation_metrics
            ):
                prisma_insights = (
                    self._last_aggregation.prisma_instrumentation_metrics.get(
                        'insights', {}
                    )
                )
                prisma_performance = {
                    'overall_success_rate': prisma_insights.get('overall', {}).get(
                        'success_rate', 0
                    ),
                    'slow_query_rate': prisma_insights.get('overall', {}).get(
                        'slow_query_rate', 0
                    ),
                    'very_slow_query_rate': prisma_insights.get('overall', {}).get(
                        'very_slow_query_rate', 0
                    ),
                    'average_duration': prisma_insights.get('overall', {}).get(
                        'average_duration', 0
                    ),
                    'average_complexity': prisma_insights.get('overall', {}).get(
                        'average_complexity', 0
                    ),
                    'read_vs_write_ratio': prisma_insights.get(
                        'operation_patterns', {}
                    ).get('read_vs_write_ratio', 0),
                }

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
                'prisma_performance': prisma_performance,
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

    async def collect_all_metrics(self) -> AggregatedMetrics:  # noqa: PLR0912
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

            elif source_name == 'prisma_instrumentation':
                aggregated.prisma_instrumentation_metrics = result

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
                    'last_updated': source.last_updated.isoformat()
                    if source.last_updated
                    else None,
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
            'prisma_instrumentation_enabled': self.prisma_instrumentation is not None,
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

    def get_prometheus_format(self) -> str:  # noqa: PLR0912, PLR0915
        """Get all metrics in Prometheus format."""
        if not self._last_aggregation:
            return ''

        output_lines = []

        # Add Prometheus metrics
        if self._last_aggregation.prometheus_metrics:
            output_lines.append('# FastAPI Application Metrics')
            output_lines.append(self._last_aggregation.prometheus_metrics)

        # Add Prisma metrics
        if self._last_aggregation.prisma_metrics:
            output_lines.append('# Prisma Database Metrics')
            output_lines.append(self._last_aggregation.prisma_metrics)

        # Add Prisma instrumentation metrics in Prometheus format
        if self._last_aggregation.prisma_instrumentation_metrics:
            output_lines.append('# Enhanced Prisma Instrumentation Metrics')
            prisma_data = self._last_aggregation.prisma_instrumentation_metrics

            # Overall insights
            if 'insights' in prisma_data and 'overall' in prisma_data['insights']:
                overall = prisma_data['insights']['overall']
                output_lines.append(
                    f'prisma_instrumentation_total_operations '
                    f'{overall.get("total_operations", 0)}'
                )
                output_lines.append(
                    f'prisma_instrumentation_success_rate '
                    f'{overall.get("success_rate", 0)}'
                )
                output_lines.append(
                    f'prisma_instrumentation_slow_query_rate '
                    f'{overall.get("slow_query_rate", 0)}'
                )
                output_lines.append(
                    f'prisma_instrumentation_very_slow_query_rate '
                    f'{overall.get("very_slow_query_rate", 0)}'
                )
                output_lines.append(
                    f'prisma_instrumentation_average_duration_seconds '
                    f'{overall.get("average_duration", 0)}'
                )
                output_lines.append(
                    f'prisma_instrumentation_average_complexity '
                    f'{overall.get("average_complexity", 0)}'
                )

            # Health metrics
            if 'health_metrics' in prisma_data:
                health = prisma_data['health_metrics']
                output_lines.append(
                    f'prisma_instrumentation_instrumented_clients '
                    f'{health.get("instrumented_clients", 0)}'
                )
                output_lines.append(
                    f'prisma_instrumentation_slow_queries_total '
                    f'{health.get("slow_queries", 0)}'
                )
                output_lines.append(
                    f'prisma_instrumentation_very_slow_queries_total '
                    f'{health.get("very_slow_queries", 0)}'
                )

        # Convert health metrics to Prometheus format
        if self._last_aggregation.health_metrics:
            output_lines.append('# Application Health Metrics')
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

            # Prisma instrumentation health metrics
            if 'prisma_instrumentation' in health and isinstance(
                health['prisma_instrumentation'], dict
            ):
                pi_health = health['prisma_instrumentation']
                for key, value in pi_health.items():
                    if isinstance(value, int | float):
                        output_lines.append(f'prisma_instrumentation_{key} {value}')

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

            # Prisma performance metrics
            if 'prisma_performance' in perf:
                pp = perf['prisma_performance']
                for key, value in pp.items():
                    if isinstance(value, int | float):
                        output_lines.append(f'prisma_performance_{key} {value}')

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
        output_lines.append(
            f'metrics_prisma_instrumentation_enabled '
            f'{
                1
                if self._last_aggregation.metadata.get(
                    "prisma_instrumentation_enabled", False
                )
                else 0
            }'
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

        # Include Prisma instrumentation health
        prisma_instrumentation_healthy = True
        if self.prisma_instrumentation and self._last_aggregation.health_metrics:
            pi_health = self._last_aggregation.health_metrics.get(
                'prisma_instrumentation', {}
            )
            prisma_success_rate = pi_health.get('success_rate', 0)
            prisma_instrumentation_healthy = prisma_success_rate >= 0.8

        # Determine health status
        if success_rate >= 0.95 and prisma_instrumentation_healthy:
            status = 'healthy'
        elif success_rate >= 0.8 and prisma_instrumentation_healthy:
            status = 'degraded'
        else:
            status = 'unhealthy'

        healthy = (
            self.enabled
            and enabled_sources > 0
            and success_rate >= 0.8
            and error_sources < total_sources / 2
            and prisma_instrumentation_healthy
        )

        return {
            'status': status,
            'healthy': healthy,
            'total_sources': total_sources,
            'enabled_sources': enabled_sources,
            'error_sources': error_sources,
            'success_rate': success_rate,
            'prisma_instrumentation_healthy': prisma_instrumentation_healthy,
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
                'prisma_instrumentation_included': bool(
                    metrics.prisma_instrumentation_metrics
                ),
            }
            for metrics in recent_history
        ]

    # Get detailed Prisma analysis
    def get_prisma_analysis(self) -> dict[str, Any]:
        """Get detailed Prisma performance analysis."""
        if (
            not self._last_aggregation
            or not self._last_aggregation.prisma_instrumentation_metrics
        ):
            return {'status': 'no_data', 'analysis_available': False}

        prisma_data = self._last_aggregation.prisma_instrumentation_metrics

        return {
            'status': 'available',
            'analysis_available': True,
            'insights': prisma_data.get('insights', {}),
            'performance_analysis': prisma_data.get('performance_analysis', {}),
            'operation_statistics': prisma_data.get('operation_statistics', {}),
            'health_metrics': prisma_data.get('health_metrics', {}),
            'collection_metadata': prisma_data.get('collection_metadata', {}),
        }
