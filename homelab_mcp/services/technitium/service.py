"""Technitium DNS Server service implementation."""

import logging
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class TechnitiumConfig:
    """Technitium DNS configuration."""
    def __init__(
        self,
        enabled: bool = False,
        url: str = "",
        api_token: str = "",
    ):
        self.enabled = enabled
        self.url = url
        self.api_token = api_token


class TechnitiumService(ServiceBase):
    """Technitium DNS Server service for authoritative and recursive DNS."""
    
    name = "technitium"
    
    def __init__(self, config: TechnitiumConfig) -> None:
        """Initialize Technitium service."""
        super().__init__(config)
        self.config: TechnitiumConfig = config
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client for Technitium API."""
        return HTTPClient(
            base_url=f"{self.config.url}/api",
            timeout=30.0,
            verify_ssl=False,
        )
    
    async def _api_call(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make authenticated API call to Technitium.
        
        Args:
            endpoint: API endpoint
            params: Query parameters
        
        Returns:
            API response data
        """
        if params is None:
            params = {}
        params["token"] = self.config.api_token
        
        response = await self.client.get(endpoint, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") == "error":
            raise Exception(data.get("errorMessage", "Unknown error"))
        
        return data.get("response", data)
    
    async def health_check(self) -> ServiceHealth:
        """Check Technitium service health."""
        try:
            data = await self._api_call("/dashboard/stats/get")
            
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Technitium DNS running",
                details={
                    "total_queries": data.get("stats", {}).get("totalQueries", 0),
                    "zones": data.get("stats", {}).get("zones", 0),
                    "cached_entries": data.get("stats", {}).get("cachedEntries", 0),
                },
            )
        except Exception as e:
            logger.error(f"Technitium health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register Technitium tools with MCP."""
        
        @mcp.tool()
        async def technitium_get_stats() -> dict[str, Any]:
            """Get Technitium DNS server statistics.
            
            Returns:
                Server statistics including queries, cache, zones
            """
            data = await self._api_call("/dashboard/stats/get")
            stats = data.get("stats", {})
            
            return {
                "total_queries": stats.get("totalQueries", 0),
                "total_no_error": stats.get("totalNoError", 0),
                "total_server_failure": stats.get("totalServerFailure", 0),
                "total_nx_domain": stats.get("totalNxDomain", 0),
                "total_refused": stats.get("totalRefused", 0),
                "total_blocked": stats.get("totalBlocked", 0),
                "total_cached": stats.get("totalCached", 0),
                "zones": stats.get("zones", 0),
                "cached_entries": stats.get("cachedEntries", 0),
                "allowed_zones": stats.get("allowedZones", 0),
                "blocked_zones": stats.get("blockedZones", 0),
            }
        
        @mcp.tool()
        async def technitium_list_zones() -> list[dict[str, Any]]:
            """List all DNS zones.
            
            Returns:
                List of configured DNS zones
            """
            data = await self._api_call("/zones/list")
            
            zones = []
            for zone in data.get("zones", []):
                zones.append({
                    "name": zone.get("name"),
                    "type": zone.get("type"),
                    "disabled": zone.get("disabled", False),
                    "internal": zone.get("internal", False),
                })
            
            return zones
        
        @mcp.tool()
        async def technitium_get_zone_records(zone: str) -> list[dict[str, Any]]:
            """Get all records in a DNS zone.
            
            Args:
                zone: Zone name (e.g., 'example.com')
            
            Returns:
                List of DNS records in the zone
            """
            data = await self._api_call("/zones/records/get", {"domain": zone, "zone": zone})
            
            records = []
            for record in data.get("records", []):
                records.append({
                    "name": record.get("name"),
                    "type": record.get("type"),
                    "ttl": record.get("ttl"),
                    "rdata": record.get("rData"),
                    "disabled": record.get("disabled", False),
                })
            
            return records
        
        @mcp.tool()
        async def technitium_create_zone(
            zone: str,
            zone_type: str = "Primary"
        ) -> dict[str, Any]:
            """Create a new DNS zone.
            
            Args:
                zone: Zone name (e.g., 'example.com')
                zone_type: Zone type (Primary, Secondary, Stub, Forwarder)
            
            Returns:
                Result of the operation
            """
            data = await self._api_call("/zones/create", {
                "zone": zone,
                "type": zone_type,
            })
            return {"success": True, "zone": zone, "type": zone_type}
        
        @mcp.tool()
        async def technitium_add_record(
            zone: str,
            name: str,
            record_type: str,
            value: str,
            ttl: int = 3600
        ) -> dict[str, Any]:
            """Add a DNS record to a zone.
            
            Args:
                zone: Zone name
                name: Record name (e.g., 'www' or '@' for apex)
                record_type: Record type (A, AAAA, CNAME, MX, TXT, etc.)
                value: Record value
                ttl: Time to live in seconds
            
            Returns:
                Result of the operation
            """
            # Build the full domain name
            if name == "@":
                domain = zone
            else:
                domain = f"{name}.{zone}"
            
            params = {
                "zone": zone,
                "domain": domain,
                "type": record_type,
                "ttl": ttl,
            }
            
            # Different record types have different value parameters
            if record_type == "A":
                params["ipAddress"] = value
            elif record_type == "AAAA":
                params["ipAddress"] = value
            elif record_type == "CNAME":
                params["cname"] = value
            elif record_type == "MX":
                params["exchange"] = value
                params["preference"] = 10
            elif record_type == "TXT":
                params["text"] = value
            elif record_type == "NS":
                params["nameServer"] = value
            elif record_type == "PTR":
                params["ptrName"] = value
            else:
                params["value"] = value
            
            await self._api_call("/zones/records/add", params)
            return {"success": True, "zone": zone, "name": name, "type": record_type, "value": value}
        
        @mcp.tool()
        async def technitium_delete_record(
            zone: str,
            name: str,
            record_type: str,
            value: str
        ) -> dict[str, Any]:
            """Delete a DNS record from a zone.
            
            Args:
                zone: Zone name
                name: Record name
                record_type: Record type
                value: Record value to delete
            
            Returns:
                Result of the operation
            """
            if name == "@":
                domain = zone
            else:
                domain = f"{name}.{zone}"
            
            params = {
                "zone": zone,
                "domain": domain,
                "type": record_type,
            }
            
            if record_type == "A" or record_type == "AAAA":
                params["ipAddress"] = value
            elif record_type == "CNAME":
                params["cname"] = value
            elif record_type == "MX":
                params["exchange"] = value
            elif record_type == "TXT":
                params["text"] = value
            else:
                params["value"] = value
            
            await self._api_call("/zones/records/delete", params)
            return {"success": True, "zone": zone, "name": name, "type": record_type, "deleted": value}
        
        @mcp.tool()
        async def technitium_delete_zone(zone: str) -> dict[str, Any]:
            """Delete a DNS zone.
            
            Args:
                zone: Zone name to delete
            
            Returns:
                Result of the operation
            """
            await self._api_call("/zones/delete", {"zone": zone})
            return {"success": True, "zone": zone, "deleted": True}
        
        @mcp.tool()
        async def technitium_enable_zone(zone: str) -> dict[str, Any]:
            """Enable a disabled DNS zone.
            
            Args:
                zone: Zone name
            
            Returns:
                Result of the operation
            """
            await self._api_call("/zones/enable", {"zone": zone})
            return {"success": True, "zone": zone, "enabled": True}
        
        @mcp.tool()
        async def technitium_disable_zone(zone: str) -> dict[str, Any]:
            """Disable a DNS zone.
            
            Args:
                zone: Zone name
            
            Returns:
                Result of the operation
            """
            await self._api_call("/zones/disable", {"zone": zone})
            return {"success": True, "zone": zone, "enabled": False}
        
        @mcp.tool()
        async def technitium_get_cache_stats() -> dict[str, Any]:
            """Get DNS cache statistics.
            
            Returns:
                Cache statistics
            """
            data = await self._api_call("/cache/list")
            return {
                "total_entries": len(data.get("entries", [])),
                "entries": data.get("entries", [])[:50],  # Limit to 50
            }
        
        @mcp.tool()
        async def technitium_flush_cache() -> dict[str, Any]:
            """Flush the DNS cache.
            
            Returns:
                Result of the operation
            """
            await self._api_call("/cache/flush")
            return {"success": True, "message": "DNS cache flushed"}
        
        @mcp.tool()
        async def technitium_get_query_logs(
            page: int = 1,
            entries_per_page: int = 100
        ) -> dict[str, Any]:
            """Get DNS query logs.
            
            Args:
                page: Page number
                entries_per_page: Number of entries per page
            
            Returns:
                Query log entries
            """
            data = await self._api_call("/logs/query", {
                "pageNumber": page,
                "entriesPerPage": entries_per_page,
            })
            
            return {
                "page": page,
                "total_pages": data.get("totalPages", 1),
                "total_entries": data.get("totalEntries", 0),
                "entries": data.get("entries", []),
            }
        
        @mcp.tool()
        async def technitium_get_blocked_list() -> list[dict[str, Any]]:
            """Get list of blocked zones/domains.
            
            Returns:
                List of blocked zones
            """
            data = await self._api_call("/zones/list")
            
            blocked = []
            for zone in data.get("zones", []):
                if zone.get("type") == "Block":
                    blocked.append({
                        "name": zone.get("name"),
                        "disabled": zone.get("disabled", False),
                    })
            
            return blocked
        
        @mcp.tool()
        async def technitium_block_domain(domain: str) -> dict[str, Any]:
            """Block a domain.
            
            Args:
                domain: Domain to block
            
            Returns:
                Result of the operation
            """
            await self._api_call("/zones/create", {
                "zone": domain,
                "type": "Block",
            })
            return {"success": True, "domain": domain, "action": "blocked"}
        
        @mcp.tool()
        async def technitium_get_forwarders() -> list[dict[str, Any]]:
            """Get configured DNS forwarders.
            
            Returns:
                List of DNS forwarders
            """
            data = await self._api_call("/settings/get")
            
            forwarders = data.get("forwarders", [])
            return [{"address": f} for f in forwarders]
        
        @mcp.tool()
        async def technitium_set_forwarders(forwarders: list[str]) -> dict[str, Any]:
            """Set DNS forwarders.
            
            Args:
                forwarders: List of forwarder addresses (e.g., ['8.8.8.8', '1.1.1.1'])
            
            Returns:
                Result of the operation
            """
            await self._api_call("/settings/set", {
                "forwarders": ",".join(forwarders),
            })
            return {"success": True, "forwarders": forwarders}
        
        logger.info("Technitium DNS tools registered")
