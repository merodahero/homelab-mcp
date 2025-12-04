"""Base class for Homelab MCP services."""

import logging
from abc import ABC, abstractmethod
from typing import Any

from fastmcp import FastMCP

from ..core.client import HTTPClient
from ..core.health import HealthChecker, ServiceHealth

logger = logging.getLogger(__name__)


class ServiceBase(ABC):
    """Base class for all homelab services.
    
    Each service should:
    1. Implement register_tools() to add MCP tools
    2. Implement health_check() for monitoring
    3. Use the shared HTTPClient for API calls
    """
    
    name: str = "base"
    
    def __init__(self, config: Any) -> None:
        """Initialize service with configuration.
        
        Args:
            config: Service-specific configuration
        """
        self.config = config
        self._client: HTTPClient | None = None
    
    @property
    def client(self) -> HTTPClient:
        """Get the HTTP client for this service."""
        if self._client is None:
            self._client = self._create_client()
        return self._client
    
    @abstractmethod
    def _create_client(self) -> HTTPClient:
        """Create the HTTP client for this service.
        
        Returns:
            Configured HTTPClient instance
        """
        pass
    
    @abstractmethod
    def register_tools(self, mcp: FastMCP) -> None:
        """Register MCP tools for this service.
        
        Args:
            mcp: FastMCP instance to register tools with
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> ServiceHealth:
        """Perform health check for this service.
        
        Returns:
            ServiceHealth with current status
        """
        pass
    
    def register_health_check(self, health_checker: HealthChecker) -> None:
        """Register this service's health check.
        
        Args:
            health_checker: HealthChecker instance
        """
        health_checker.register(self.name, self.health_check)
        logger.info(f"Registered health check for service: {self.name}")
    
    async def close(self) -> None:
        """Clean up resources."""
        if self._client:
            await self._client.close()
            self._client = None
