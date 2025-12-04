"""Health check utilities for Homelab MCP services."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enum."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """Health status for a single service."""
    name: str
    status: HealthStatus
    latency_ms: float | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    last_check: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "details": self.details,
            "last_check": self.last_check.isoformat(),
        }


@dataclass
class OverallHealth:
    """Overall health status for all services."""
    status: HealthStatus
    services: list[ServiceHealth]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    server_version: str = "0.1.0"
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "server_version": self.server_version,
            "services": [s.to_dict() for s in self.services],
            "summary": {
                "total": len(self.services),
                "healthy": sum(1 for s in self.services if s.status == HealthStatus.HEALTHY),
                "degraded": sum(1 for s in self.services if s.status == HealthStatus.DEGRADED),
                "unhealthy": sum(1 for s in self.services if s.status == HealthStatus.UNHEALTHY),
            }
        }


# Type alias for health check functions
HealthCheckFunc = Callable[[], Coroutine[Any, Any, ServiceHealth]]


class HealthChecker:
    """Manages health checks for all registered services."""
    
    def __init__(self) -> None:
        """Initialize health checker."""
        self._checks: dict[str, HealthCheckFunc] = {}
    
    def register(self, name: str, check_func: HealthCheckFunc) -> None:
        """Register a health check function for a service.
        
        Args:
            name: Service name
            check_func: Async function that returns ServiceHealth
        """
        self._checks[name] = check_func
        logger.debug(f"Registered health check for: {name}")
    
    def unregister(self, name: str) -> None:
        """Unregister a health check."""
        self._checks.pop(name, None)
    
    async def check_service(self, name: str) -> ServiceHealth:
        """Run health check for a specific service.
        
        Args:
            name: Service name
        
        Returns:
            Service health status
        """
        if name not in self._checks:
            return ServiceHealth(
                name=name,
                status=HealthStatus.UNKNOWN,
                message=f"No health check registered for {name}",
            )
        
        start_time = time.time()
        try:
            health = await self._checks[name]()
            health.latency_ms = round((time.time() - start_time) * 1000, 2)
            return health
        except Exception as e:
            logger.error(f"Health check failed for {name}: {e}")
            return ServiceHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=round((time.time() - start_time) * 1000, 2),
                message=str(e),
            )
    
    async def check_all(self) -> OverallHealth:
        """Run all health checks concurrently.
        
        Returns:
            Overall health status
        """
        if not self._checks:
            return OverallHealth(
                status=HealthStatus.HEALTHY,
                services=[],
            )
        
        # Run all checks concurrently
        results = await asyncio.gather(
            *[self.check_service(name) for name in self._checks],
            return_exceptions=True,
        )
        
        services: list[ServiceHealth] = []
        for result in results:
            if isinstance(result, Exception):
                services.append(ServiceHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=str(result),
                ))
            else:
                services.append(result)
        
        # Determine overall status
        if any(s.status == HealthStatus.UNHEALTHY for s in services):
            overall_status = HealthStatus.UNHEALTHY
        elif any(s.status == HealthStatus.DEGRADED for s in services):
            overall_status = HealthStatus.DEGRADED
        elif all(s.status == HealthStatus.HEALTHY for s in services):
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN
        
        return OverallHealth(
            status=overall_status,
            services=services,
        )


# Global health checker instance
health_checker = HealthChecker()
