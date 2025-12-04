"""Nginx Proxy Manager service implementation."""

import logging
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.config import NginxProxyManagerConfig
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class NginxProxyManagerService(ServiceBase):
    """Nginx Proxy Manager service for managing reverse proxy hosts and SSL certificates."""
    
    name = "nginx_proxy_manager"
    
    def __init__(self, config: NginxProxyManagerConfig) -> None:
        """Initialize NPM service."""
        super().__init__(config)
        self.config: NginxProxyManagerConfig = config
        self._token: str | None = None
        self._token_expires: datetime | None = None
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client for NPM API."""
        return HTTPClient(
            base_url=f"{self.config.url}/api",
            timeout=30.0,
            verify_ssl=False,
        )
    
    async def _get_token(self) -> str:
        """Get or refresh authentication token.
        
        Returns:
            Valid authentication token
        """
        # Check if we have a valid token
        if self._token and self._token_expires and datetime.utcnow() < self._token_expires:
            return self._token
        
        # Get new token
        response = await self.client.post(
            "/tokens",
            json={
                "identity": self.config.username,
                "secret": self.config.password,
            }
        )
        response.raise_for_status()
        data = response.json()
        
        self._token = data["token"]
        # Token expires in 1 day, refresh after 23 hours
        self._token_expires = datetime.utcnow()
        
        return self._token
    
    async def _auth_headers(self) -> dict[str, str]:
        """Get headers with authentication token."""
        token = await self._get_token()
        return {"Authorization": f"Bearer {token}"}
    
    async def health_check(self) -> ServiceHealth:
        """Check NPM service health."""
        try:
            # Try to authenticate and get basic info
            headers = await self._auth_headers()
            response = await self.client.get("/nginx/proxy-hosts", headers=headers)
            response.raise_for_status()
            
            hosts = response.json()
            
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message=f"Connected, {len(hosts)} proxy hosts configured",
                details={"proxy_host_count": len(hosts)},
            )
        except Exception as e:
            logger.error(f"NPM health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register NPM tools with MCP."""
        
        @mcp.tool()
        async def npm_list_proxy_hosts() -> list[dict[str, Any]]:
            """List all proxy hosts configured in Nginx Proxy Manager.
            
            Returns:
                List of proxy host configurations
            """
            headers = await self._auth_headers()
            response = await self.client.get("/nginx/proxy-hosts", headers=headers)
            response.raise_for_status()
            
            hosts = response.json()
            # Simplify output
            return [
                {
                    "id": h["id"],
                    "domain_names": h["domain_names"],
                    "forward_host": h["forward_host"],
                    "forward_port": h["forward_port"],
                    "ssl_enabled": h.get("certificate_id") is not None,
                    "enabled": h["enabled"] == 1,
                    "meta": h.get("meta", {}),
                }
                for h in hosts
            ]
        
        @mcp.tool()
        async def npm_list_ssl_certificates() -> list[dict[str, Any]]:
            """List all SSL certificates in Nginx Proxy Manager.
            
            Returns:
                List of SSL certificates with expiry info
            """
            headers = await self._auth_headers()
            response = await self.client.get("/nginx/certificates", headers=headers)
            response.raise_for_status()
            
            certs = response.json()
            return [
                {
                    "id": c["id"],
                    "nice_name": c.get("nice_name", ""),
                    "domain_names": c["domain_names"],
                    "expires_on": c.get("expires_on"),
                    "provider": c.get("provider", "unknown"),
                }
                for c in certs
            ]
        
        @mcp.tool()
        async def npm_get_proxy_host(host_id: int) -> dict[str, Any]:
            """Get details of a specific proxy host.
            
            Args:
                host_id: The proxy host ID
            
            Returns:
                Proxy host configuration details
            """
            headers = await self._auth_headers()
            response = await self.client.get(f"/nginx/proxy-hosts/{host_id}", headers=headers)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        
        @mcp.tool()
        async def npm_enable_proxy_host(host_id: int) -> dict[str, Any]:
            """Enable a proxy host.
            
            Args:
                host_id: The proxy host ID to enable
            
            Returns:
                Updated proxy host configuration
            """
            headers = await self._auth_headers()
            response = await self.client.post(
                f"/nginx/proxy-hosts/{host_id}/enable",
                headers=headers
            )
            response.raise_for_status()
            return {"success": True, "host_id": host_id, "enabled": True}
        
        @mcp.tool()
        async def npm_disable_proxy_host(host_id: int) -> dict[str, Any]:
            """Disable a proxy host.
            
            Args:
                host_id: The proxy host ID to disable
            
            Returns:
                Updated proxy host configuration
            """
            headers = await self._auth_headers()
            response = await self.client.post(
                f"/nginx/proxy-hosts/{host_id}/disable",
                headers=headers
            )
            response.raise_for_status()
            return {"success": True, "host_id": host_id, "enabled": False}
        
        @mcp.tool()
        async def npm_check_expiring_certificates(days: int = 30) -> list[dict[str, Any]]:
            """Check for SSL certificates expiring within specified days.
            
            Args:
                days: Number of days to check for expiring certs (default 30)
            
            Returns:
                List of certificates expiring soon
            """
            from datetime import timedelta
            
            headers = await self._auth_headers()
            response = await self.client.get("/nginx/certificates", headers=headers)
            response.raise_for_status()
            
            certs = response.json()
            expiring = []
            now = datetime.utcnow()
            threshold = now + timedelta(days=days)
            
            for cert in certs:
                expires_on = cert.get("expires_on")
                if expires_on:
                    try:
                        # Parse ISO format date
                        exp_date = datetime.fromisoformat(expires_on.replace("Z", "+00:00"))
                        if exp_date.replace(tzinfo=None) <= threshold:
                            days_left = (exp_date.replace(tzinfo=None) - now).days
                            expiring.append({
                                "id": cert["id"],
                                "nice_name": cert.get("nice_name", ""),
                                "domain_names": cert["domain_names"],
                                "expires_on": expires_on,
                                "days_until_expiry": days_left,
                                "expired": days_left < 0,
                            })
                    except (ValueError, TypeError):
                        pass
            
            return sorted(expiring, key=lambda x: x["days_until_expiry"])
        
        logger.info("Nginx Proxy Manager tools registered")
