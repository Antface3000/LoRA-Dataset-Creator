"""Lightweight telemetry helpers for stage timing and throughput metrics."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterator

logger = logging.getLogger(__name__)


@dataclass
class _Metric:
    total_seconds: float = 0.0
    count: int = 0


class MetricsCollector:
    """Collects per-stage timing and emits concise throughput logs."""

    def __init__(self) -> None:
        self._metrics: Dict[str, _Metric] = {}

    @contextmanager
    def time_stage(self, stage_name: str, units: int = 1) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            metric = self._metrics.setdefault(stage_name, _Metric())
            metric.total_seconds += elapsed
            metric.count += max(units, 0)
            unit_rate = (metric.count / metric.total_seconds) if metric.total_seconds > 0 else 0.0
            logger.info(
                "[metrics] stage=%s elapsed=%.3fs total=%.3fs units=%d rate=%.2f items/s",
                stage_name,
                elapsed,
                metric.total_seconds,
                metric.count,
                unit_rate,
            )

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for stage_name, metric in self._metrics.items():
            rate = (metric.count / metric.total_seconds) if metric.total_seconds > 0 else 0.0
            out[stage_name] = {
                "total_seconds": metric.total_seconds,
                "count": float(metric.count),
                "rate_items_per_sec": rate,
            }
        return out


_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    return _collector
