"""AdGuard Home service implementation."""

import base64
import logging
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class AdGuardHomeConfig:
    """AdGuard Home configuration."""
    def __init__(
        self,
        enabled: bool = False,
        url: str = "",
        username: str = "",
        password: str = "",
    ):
        self.enabled = enabled
        self.url = url
        self.username = username
        self.password = password


class AdGuardHomeService(ServiceBase):
    """AdGuard Home service for DNS ad-blocking and privacy protection."""
    
    name = "adguard_home"
    
    def __init__(self, config: AdGuardHomeConfig) -> None:
        """Initialize AdGuard Home service."""
        super().__init__(config)
        self.config: AdGuardHomeConfig = config
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client for AdGuard Home API."""
        # AdGuard uses Basic Auth
        credentials = base64.b64encode(
            f"{self.config.username}:{self.config.password}".encode()
        ).decode()
        
        return HTTPClient(
            base_url=f"{self.config.url}/control",
            timeout=30.0,
            verify_ssl=False,
            headers={"Authorization": f"Basic {credentials}"},
        )
    
    async def health_check(self) -> ServiceHealth:
        """Check AdGuard Home service health."""
        try:
            response = await self.client.get("/status")
            response.raise_for_status()
            data = response.json()
            
            protection_enabled = data.get("protection_enabled", False)
            
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.HEALTHY if protection_enabled else HealthStatus.DEGRADED,
                message=f"Protection: {'enabled' if protection_enabled else 'disabled'}",
                details={
                    "protection_enabled": protection_enabled,
                    "running": data.get("running", False),
                    "version": data.get("version", "unknown"),
                    "dns_port": data.get("dns_port", 53),
                },
            )
        except Exception as e:
            logger.error(f"AdGuard Home health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register AdGuard Home tools with MCP."""
        
        @mcp.tool()
        async def adguard_get_status() -> dict[str, Any]:
            """Get AdGuard Home status and configuration.
            
            Returns:
                Current status including protection state, version, ports
            """
            response = await self.client.get("/status")
            response.raise_for_status()
            return response.json()
        
        @mcp.tool()
        async def adguard_get_stats() -> dict[str, Any]:
            """Get AdGuard Home DNS query statistics.
            
            Returns:
                Statistics including queries, blocked, top clients
            """
            response = await self.client.get("/stats")
            response.raise_for_status()
            data = response.json()
            
            return {
                "total_queries": data.get("num_dns_queries", 0),
                "blocked_queries": data.get("num_blocked_filtering", 0),
                "blocked_percentage": round(
                    data.get("num_blocked_filtering", 0) / max(data.get("num_dns_queries", 1), 1) * 100, 2
                ),
                "replaced_safebrowsing": data.get("num_replaced_safebrowsing", 0),
                "replaced_parental": data.get("num_replaced_parental", 0),
                "avg_processing_time_ms": round(data.get("avg_processing_time", 0) * 1000, 2),
                "top_queried_domains": data.get("top_queried_domains", [])[:10],
                "top_blocked_domains": data.get("top_blocked_domains", [])[:10],
                "top_clients": data.get("top_clients", [])[:10],
            }
        
        @mcp.tool()
        async def adguard_enable_protection() -> dict[str, Any]:
            """Enable AdGuard Home DNS protection.
            
            Returns:
                Result of the operation
            """
            response = await self.client.post("/dns_config", json={"protection_enabled": True})
            response.raise_for_status()
            return {"success": True, "protection_enabled": True}
        
        @mcp.tool()
        async def adguard_disable_protection(duration_ms: int = 0) -> dict[str, Any]:
            """Disable AdGuard Home DNS protection.
            
            Args:
                duration_ms: Duration in milliseconds (0 = indefinitely)
            
            Returns:
                Result of the operation
            """
            payload: dict[str, Any] = {"protection_enabled": False}
            if duration_ms > 0:
                payload["protection_disabled_until"] = duration_ms
            
            response = await self.client.post("/dns_config", json=payload)
            response.raise_for_status()
            return {"success": True, "protection_enabled": False, "duration_ms": duration_ms}
        
        @mcp.tool()
        async def adguard_get_query_log(limit: int = 100) -> list[dict[str, Any]]:
            """Get recent DNS query log.
            
            Args:
                limit: Number of entries to return (max 500)
            
            Returns:
                List of recent DNS queries
            """
            response = await self.client.get("/querylog", params={"limit": min(limit, 500)})
            response.raise_for_status()
            data = response.json()
            
            queries = []
            for entry in data.get("data", [])[:limit]:
                queries.append({
                    "time": entry.get("time"),
                    "client": entry.get("client"),
                    "question": entry.get("question", {}).get("name"),
                    "type": entry.get("question", {}).get("type"),
                    "answer": entry.get("answer", []),
                    "reason": entry.get("reason"),
                    "blocked": entry.get("reason") != "NotFilteredNotFound",
                    "upstream": entry.get("upstream"),
                    "elapsed_ms": entry.get("elapsed_ms"),
                })
            
            return queries
        
        @mcp.tool()
        async def adguard_list_filters() -> list[dict[str, Any]]:
            """List all configured filter lists.
            
            Returns:
                List of filter configurations
            """
            response = await self.client.get("/filtering/status")
            response.raise_for_status()
            data = response.json()
            
            filters = []
            for f in data.get("filters", []):
                filters.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "url": f.get("url"),
                    "enabled": f.get("enabled"),
                    "rules_count": f.get("rules_count", 0),
                    "last_updated": f.get("last_updated"),
                })
            
            return filters
        
        @mcp.tool()
        async def adguard_add_filter(name: str, url: str, enabled: bool = True) -> dict[str, Any]:
            """Add a new filter list.
            
            Args:
                name: Display name for the filter
                url: URL to the filter list
                enabled: Whether to enable the filter
            
            Returns:
                Result of the operation
            """
            response = await self.client.post(
                "/filtering/add_url",
                json={"name": name, "url": url, "whitelist": False}
            )
            response.raise_for_status()
            return {"success": True, "name": name, "url": url, "enabled": enabled}
        
        @mcp.tool()
        async def adguard_get_clients() -> list[dict[str, Any]]:
            """Get list of configured clients with their settings.
            
            Returns:
                List of client configurations
            """
            response = await self.client.get("/clients")
            response.raise_for_status()
            data = response.json()
            
            clients = []
            for c in data.get("clients", []):
                clients.append({
                    "name": c.get("name"),
                    "ids": c.get("ids", []),
                    "use_global_settings": c.get("use_global_settings", True),
                    "filtering_enabled": c.get("filtering_enabled", True),
                    "parental_enabled": c.get("parental_enabled", False),
                    "safebrowsing_enabled": c.get("safebrowsing_enabled", False),
                    "blocked_services": c.get("blocked_services", []),
                })
            
            # Also include auto-discovered clients
            for c in data.get("auto_clients", []):
                clients.append({
                    "name": c.get("name", c.get("ip")),
                    "ids": [c.get("ip")],
                    "source": c.get("source"),
                    "auto_discovered": True,
                })
            
            return clients
        
        @mcp.tool()
        async def adguard_block_service(service: str) -> dict[str, Any]:
            """Block a specific service globally.
            
            Args:
                service: Service to block (e.g., 'facebook', 'tiktok', 'youtube')
            
            Returns:
                Result of the operation
            """
            # Get current blocked services
            response = await self.client.get("/blocked_services/list")
            response.raise_for_status()
            current = response.json()
            
            if service not in current:
                current.append(service)
                response = await self.client.post("/blocked_services/set", json=current)
                response.raise_for_status()
            
            return {"success": True, "service": service, "action": "blocked"}
        
        @mcp.tool()
        async def adguard_unblock_service(service: str) -> dict[str, Any]:
            """Unblock a specific service globally.
            
            Args:
                service: Service to unblock
            
            Returns:
                Result of the operation
            """
            response = await self.client.get("/blocked_services/list")
            response.raise_for_status()
            current = response.json()
            
            if service in current:
                current.remove(service)
                response = await self.client.post("/blocked_services/set", json=current)
                response.raise_for_status()
            
            return {"success": True, "service": service, "action": "unblocked"}
        
        @mcp.tool()
        async def adguard_get_dns_config() -> dict[str, Any]:
            """Get DNS server configuration.
            
            Returns:
                DNS configuration including upstreams, bootstrap servers
            """
            response = await self.client.get("/dns_info")
            response.raise_for_status()
            data = response.json()
            
            return {
                "upstream_dns": data.get("upstream_dns", []),
                "bootstrap_dns": data.get("bootstrap_dns", []),
                "protection_enabled": data.get("protection_enabled"),
                "ratelimit": data.get("ratelimit"),
                "blocking_mode": data.get("blocking_mode"),
                "edns_cs_enabled": data.get("edns_cs_enabled"),
                "dnssec_enabled": data.get("dnssec_enabled"),
                "cache_size": data.get("cache_size"),
                "cache_ttl_min": data.get("cache_ttl_min"),
                "cache_ttl_max": data.get("cache_ttl_max"),
            }
        
        @mcp.tool()
        async def adguard_set_upstream_dns(upstreams: list[str]) -> dict[str, Any]:
            """Set upstream DNS servers.
            
            Args:
                upstreams: List of upstream DNS servers (e.g., ['8.8.8.8', '1.1.1.1'])
            
            Returns:
                Result of the operation
            """
            response = await self.client.post(
                "/dns_config",
                json={"upstream_dns": upstreams}
            )
            response.raise_for_status()
            return {"success": True, "upstream_dns": upstreams}
        
        logger.info("AdGuard Home tools registered")
