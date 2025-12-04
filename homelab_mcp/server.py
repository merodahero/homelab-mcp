"""Homelab MCP Server - Main server setup and service registration."""

import logging
from typing import Any

from fastmcp import FastMCP

from .core.config import Config, get_config
from .core.health import HealthStatus, ServiceHealth, health_checker
from .services.base import ServiceBase
from .services.nginx_proxy_manager import NginxProxyManagerService
from .services.pihole import PiholeService
from .services.portainer import PortainerService
from .services.ups_nut import UpsNutService
from .services.uptime_kuma import UptimeKumaService

logger = logging.getLogger(__name__)

# Track active services for cleanup
_active_services: list[ServiceBase] = []


def create_server(config: Config | None = None) -> FastMCP:
    """Create and configure the MCP server.
    
    Args:
        config: Optional configuration. If None, loads from default location.
    
    Returns:
        Configured FastMCP server instance
    """
    if config is None:
        config = get_config()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.logging.level.upper()),
        format=config.logging.format,
    )
    
    # Create MCP server
    mcp = FastMCP(
        "Homelab MCP",
        description="A modular MCP server for homelab service management",
    )
    
    # Register core health check tool
    @mcp.tool()
    async def homelab_health_check() -> dict[str, Any]:
        """Check health status of all enabled homelab services.
        
        Returns:
            Overall health status with per-service details
        """
        overall = await health_checker.check_all()
        return overall.to_dict()
    
    @mcp.tool()
    async def homelab_list_services() -> dict[str, Any]:
        """List all configured homelab services and their enabled status.
        
        Returns:
            Dictionary of services and their configuration status
        """
        services_config = config.services
        return {
            "nginx_proxy_manager": {
                "enabled": services_config.nginx_proxy_manager.enabled,
                "url": services_config.nginx_proxy_manager.url if services_config.nginx_proxy_manager.enabled else None,
            },
            "pihole": {
                "enabled": services_config.pihole.enabled,
                "url": services_config.pihole.url if services_config.pihole.enabled else None,
            },
            "uptime_kuma": {
                "enabled": services_config.uptime_kuma.enabled,
                "url": services_config.uptime_kuma.url if services_config.uptime_kuma.enabled else None,
            },
            "ups_nut": {
                "enabled": services_config.ups_nut.enabled,
                "host": services_config.ups_nut.host if services_config.ups_nut.enabled else None,
            },
            "portainer": {
                "enabled": services_config.portainer.enabled,
                "url": services_config.portainer.url if services_config.portainer.enabled else None,
            },
        }
    
    # Register enabled services
    _register_services(mcp, config)
    
    logger.info(f"Homelab MCP server created with {len(_active_services)} active services")
    
    return mcp


def _register_services(mcp: FastMCP, config: Config) -> None:
    """Register all enabled services with the MCP server.
    
    Args:
        mcp: FastMCP server instance
        config: Configuration
    """
    global _active_services
    _active_services = []
    
    # Nginx Proxy Manager
    if config.services.nginx_proxy_manager.enabled:
        try:
            service = NginxProxyManagerService(config.services.nginx_proxy_manager)
            service.register_tools(mcp)
            service.register_health_check(health_checker)
            _active_services.append(service)
            logger.info("Nginx Proxy Manager service enabled")
        except Exception as e:
            logger.error(f"Failed to register Nginx Proxy Manager: {e}")
    
    # Pi-hole
    if config.services.pihole.enabled:
        try:
            service = PiholeService(config.services.pihole)
            service.register_tools(mcp)
            service.register_health_check(health_checker)
            _active_services.append(service)
            logger.info("Pi-hole service enabled")
        except Exception as e:
            logger.error(f"Failed to register Pi-hole: {e}")
    
    # Uptime Kuma
    if config.services.uptime_kuma.enabled:
        try:
            service = UptimeKumaService(config.services.uptime_kuma)
            service.register_tools(mcp)
            service.register_health_check(health_checker)
            _active_services.append(service)
            logger.info("Uptime Kuma service enabled")
        except Exception as e:
            logger.error(f"Failed to register Uptime Kuma: {e}")
    
    # UPS NUT
    if config.services.ups_nut.enabled:
        try:
            service = UpsNutService(config.services.ups_nut)
            service.register_tools(mcp)
            service.register_health_check(health_checker)
            _active_services.append(service)
            logger.info("UPS NUT service enabled")
        except Exception as e:
            logger.error(f"Failed to register UPS NUT: {e}")
    
    # Portainer
    if config.services.portainer.enabled:
        try:
            service = PortainerService(config.services.portainer)
            service.register_tools(mcp)
            service.register_health_check(health_checker)
            _active_services.append(service)
            logger.info("Portainer service enabled")
        except Exception as e:
            logger.error(f"Failed to register Portainer: {e}")


async def cleanup() -> None:
    """Clean up all active services."""
    for service in _active_services:
        try:
            await service.close()
        except Exception as e:
            logger.error(f"Error closing service {service.name}: {e}")
