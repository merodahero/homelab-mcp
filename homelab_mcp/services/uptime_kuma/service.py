"""Uptime Kuma service implementation."""

import logging
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.config import UptimeKumaConfig
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class UptimeKumaService(ServiceBase):
    """Uptime Kuma service for monitoring service availability."""
    
    name = "uptime_kuma"
    
    def __init__(self, config: UptimeKumaConfig) -> None:
        """Initialize Uptime Kuma service."""
        super().__init__(config)
        self.config: UptimeKumaConfig = config
        self._token: str | None = None
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client for Uptime Kuma API."""
        return HTTPClient(
            base_url=self.config.url,
            timeout=30.0,
            verify_ssl=False,
        )
    
    async def _login(self) -> str:
        """Login and get session token.
        
        Note: Uptime Kuma uses socket.io for most operations.
        This is a simplified REST-based approach using the status page API.
        """
        # For now, we'll use the public status page API which doesn't require auth
        # Full API access would require socket.io integration
        return ""
    
    async def health_check(self) -> ServiceHealth:
        """Check Uptime Kuma service health."""
        try:
            # Check if the service is reachable
            response = await self.client.get("/api/status-page/heartbeat/main")
            
            if response.status_code == 200:
                data = response.json()
                return ServiceHealth(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Uptime Kuma is running",
                    details={"heartbeat_list": len(data.get("heartbeatList", {}))},
                )
            else:
                # Try the main page
                response = await self.client.get("/")
                if response.status_code == 200:
                    return ServiceHealth(
                        name=self.name,
                        status=HealthStatus.HEALTHY,
                        message="Uptime Kuma is running (status page not configured)",
                    )
                    
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.DEGRADED,
                message=f"Unexpected status code: {response.status_code}",
            )
        except Exception as e:
            logger.error(f"Uptime Kuma health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register Uptime Kuma tools with MCP."""
        
        @mcp.tool()
        async def uptime_get_status_page(slug: str = "main") -> dict[str, Any]:
            """Get status page information.
            
            Args:
                slug: Status page slug (default: main)
            
            Returns:
                Status page data with monitor statuses
            """
            response = await self.client.get(f"/api/status-page/{slug}")
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        
        @mcp.tool()
        async def uptime_get_heartbeats(slug: str = "main") -> dict[str, Any]:
            """Get heartbeat data for all monitors on a status page.
            
            Args:
                slug: Status page slug (default: main)
            
            Returns:
                Heartbeat data for monitors
            """
            response = await self.client.get(f"/api/status-page/heartbeat/{slug}")
            response.raise_for_status()
            data = response.json()
            
            # Process heartbeat data
            result: dict[str, Any] = {
                "monitors": {},
                "summary": {
                    "total": 0,
                    "up": 0,
                    "down": 0,
                    "pending": 0,
                }
            }
            
            heartbeat_list = data.get("heartbeatList", {})
            for monitor_id, heartbeats in heartbeat_list.items():
                if heartbeats:
                    latest = heartbeats[-1] if isinstance(heartbeats, list) else heartbeats
                    status = latest.get("status", 0)
                    result["monitors"][monitor_id] = {
                        "status": "up" if status == 1 else "down" if status == 0 else "pending",
                        "ping": latest.get("ping"),
                        "time": latest.get("time"),
                    }
                    result["summary"]["total"] += 1
                    if status == 1:
                        result["summary"]["up"] += 1
                    elif status == 0:
                        result["summary"]["down"] += 1
                    else:
                        result["summary"]["pending"] += 1
            
            return result
        
        @mcp.tool()
        async def uptime_get_monitor_summary() -> dict[str, Any]:
            """Get a summary of all monitors from the default status page.
            
            Returns:
                Summary of monitor statuses
            """
            try:
                response = await self.client.get("/api/status-page/heartbeat/main")
                response.raise_for_status()
                data = response.json()
                
                up_count = 0
                down_count = 0
                monitors = []
                
                heartbeat_list = data.get("heartbeatList", {})
                for monitor_id, heartbeats in heartbeat_list.items():
                    if heartbeats and isinstance(heartbeats, list) and len(heartbeats) > 0:
                        latest = heartbeats[-1]
                        is_up = latest.get("status") == 1
                        if is_up:
                            up_count += 1
                        else:
                            down_count += 1
                        monitors.append({
                            "id": monitor_id,
                            "status": "up" if is_up else "down",
                            "ping_ms": latest.get("ping"),
                        })
                
                return {
                    "total_monitors": len(monitors),
                    "up": up_count,
                    "down": down_count,
                    "uptime_percentage": round(up_count / len(monitors) * 100, 2) if monitors else 0,
                    "monitors": monitors,
                }
            except Exception as e:
                return {"error": str(e), "message": "Could not fetch monitor summary"}
        
        logger.info("Uptime Kuma tools registered")
