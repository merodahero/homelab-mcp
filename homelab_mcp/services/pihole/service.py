"""Pi-hole service implementation."""

import logging
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.config import PiholeConfig
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class PiholeService(ServiceBase):
    """Pi-hole service for DNS ad-blocking management."""
    
    name = "pihole"
    
    def __init__(self, config: PiholeConfig) -> None:
        """Initialize Pi-hole service."""
        super().__init__(config)
        self.config: PiholeConfig = config
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client for Pi-hole API."""
        return HTTPClient(
            base_url=f"{self.config.url}/admin/api.php",
            timeout=30.0,
            verify_ssl=False,
        )
    
    async def health_check(self) -> ServiceHealth:
        """Check Pi-hole service health."""
        try:
            response = await self.client.get("", params={"summary": ""})
            response.raise_for_status()
            data = response.json()
            
            status = data.get("status", "unknown")
            
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.HEALTHY if status == "enabled" else HealthStatus.DEGRADED,
                message=f"Pi-hole status: {status}",
                details={
                    "status": status,
                    "domains_blocked": data.get("domains_being_blocked", 0),
                    "queries_today": data.get("dns_queries_today", 0),
                    "blocked_today": data.get("ads_blocked_today", 0),
                },
            )
        except Exception as e:
            logger.error(f"Pi-hole health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register Pi-hole tools with MCP."""
        
        @mcp.tool()
        async def pihole_get_summary() -> dict[str, Any]:
            """Get Pi-hole summary statistics.
            
            Returns:
                Summary of DNS queries, blocked domains, etc.
            """
            response = await self.client.get("", params={"summary": ""})
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return {
                "status": data.get("status"),
                "domains_blocked": data.get("domains_being_blocked"),
                "dns_queries_today": data.get("dns_queries_today"),
                "ads_blocked_today": data.get("ads_blocked_today"),
                "ads_percentage_today": data.get("ads_percentage_today"),
                "unique_domains": data.get("unique_domains"),
                "queries_forwarded": data.get("queries_forwarded"),
                "queries_cached": data.get("queries_cached"),
                "clients_ever_seen": data.get("clients_ever_seen"),
                "unique_clients": data.get("unique_clients"),
                "gravity_last_updated": data.get("gravity_last_updated"),
            }
        
        @mcp.tool()
        async def pihole_get_top_queries(count: int = 10) -> dict[str, Any]:
            """Get top permitted DNS queries.
            
            Args:
                count: Number of top queries to return
            
            Returns:
                Top permitted domains
            """
            response = await self.client.get(
                "",
                params={"topItems": str(count), "auth": self.config.api_key}
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        
        @mcp.tool()
        async def pihole_get_top_blocked(count: int = 10) -> dict[str, Any]:
            """Get top blocked DNS queries.
            
            Args:
                count: Number of top blocked queries to return
            
            Returns:
                Top blocked domains
            """
            response = await self.client.get(
                "",
                params={"topItems": str(count), "auth": self.config.api_key}
            )
            response.raise_for_status()
            data = response.json()
            return {"top_ads": data.get("top_ads", {})}
        
        @mcp.tool()
        async def pihole_enable() -> dict[str, Any]:
            """Enable Pi-hole ad blocking.
            
            Returns:
                Status after enabling
            """
            response = await self.client.get(
                "",
                params={"enable": "", "auth": self.config.api_key}
            )
            response.raise_for_status()
            return {"success": True, "status": "enabled"}
        
        @mcp.tool()
        async def pihole_disable(seconds: int = 0) -> dict[str, Any]:
            """Disable Pi-hole ad blocking.
            
            Args:
                seconds: Duration to disable (0 = indefinitely)
            
            Returns:
                Status after disabling
            """
            params: dict[str, str] = {"auth": self.config.api_key}
            if seconds > 0:
                params["disable"] = str(seconds)
            else:
                params["disable"] = ""
            
            response = await self.client.get("", params=params)
            response.raise_for_status()
            return {
                "success": True,
                "status": "disabled",
                "duration_seconds": seconds if seconds > 0 else "indefinite"
            }
        
        @mcp.tool()
        async def pihole_get_query_types() -> dict[str, Any]:
            """Get breakdown of DNS query types.
            
            Returns:
                Query type statistics (A, AAAA, PTR, etc.)
            """
            response = await self.client.get(
                "",
                params={"getQueryTypes": "", "auth": self.config.api_key}
            )
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        
        logger.info("Pi-hole tools registered")
