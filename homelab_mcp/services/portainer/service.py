"""Portainer service implementation."""

import logging
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.config import PortainerConfig
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class PortainerService(ServiceBase):
    """Portainer service for Docker management across multiple hosts."""
    
    name = "portainer"
    
    def __init__(self, config: PortainerConfig) -> None:
        """Initialize Portainer service."""
        super().__init__(config)
        self.config: PortainerConfig = config
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client for Portainer API."""
        return HTTPClient(
            base_url=f"{self.config.url}/api",
            timeout=30.0,
            verify_ssl=False,
            headers={"X-API-Key": self.config.api_key},
        )
    
    async def health_check(self) -> ServiceHealth:
        """Check Portainer service health."""
        try:
            response = await self.client.get("/system/status")
            response.raise_for_status()
            data = response.json()
            
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Portainer is running",
                details={
                    "version": data.get("Version", "unknown"),
                    "instance_id": data.get("InstanceID", "unknown"),
                },
            )
        except Exception as e:
            logger.error(f"Portainer health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register Portainer tools with MCP."""
        
        @mcp.tool()
        async def portainer_list_endpoints() -> list[dict[str, Any]]:
            """List all Docker endpoints/environments managed by Portainer.
            
            Returns:
                List of endpoints with their status
            """
            response = await self.client.get("/endpoints")
            response.raise_for_status()
            
            endpoints = response.json()
            return [
                {
                    "id": e["Id"],
                    "name": e["Name"],
                    "type": e.get("Type", 0),
                    "url": e.get("URL", ""),
                    "status": "up" if e.get("Status") == 1 else "down",
                    "snapshots": len(e.get("Snapshots", [])),
                }
                for e in endpoints
            ]
        
        @mcp.tool()
        async def portainer_list_containers(endpoint_id: int) -> list[dict[str, Any]]:
            """List all containers on a specific endpoint.
            
            Args:
                endpoint_id: The endpoint/environment ID
            
            Returns:
                List of containers with their status
            """
            response = await self.client.get(
                f"/endpoints/{endpoint_id}/docker/containers/json",
                params={"all": "true"}
            )
            response.raise_for_status()
            
            containers = response.json()
            return [
                {
                    "id": c["Id"][:12],
                    "names": [n.lstrip("/") for n in c.get("Names", [])],
                    "image": c.get("Image", ""),
                    "state": c.get("State", ""),
                    "status": c.get("Status", ""),
                    "created": c.get("Created", 0),
                }
                for c in containers
            ]
        
        @mcp.tool()
        async def portainer_get_endpoint_stats(endpoint_id: int) -> dict[str, Any]:
            """Get statistics for a Docker endpoint.
            
            Args:
                endpoint_id: The endpoint/environment ID
            
            Returns:
                Endpoint statistics including container counts
            """
            # Get containers
            containers_resp = await self.client.get(
                f"/endpoints/{endpoint_id}/docker/containers/json",
                params={"all": "true"}
            )
            containers_resp.raise_for_status()
            containers = containers_resp.json()
            
            # Get images
            images_resp = await self.client.get(
                f"/endpoints/{endpoint_id}/docker/images/json"
            )
            images_resp.raise_for_status()
            images = images_resp.json()
            
            # Get volumes
            volumes_resp = await self.client.get(
                f"/endpoints/{endpoint_id}/docker/volumes"
            )
            volumes_resp.raise_for_status()
            volumes = volumes_resp.json()
            
            running = sum(1 for c in containers if c.get("State") == "running")
            stopped = sum(1 for c in containers if c.get("State") == "exited")
            
            return {
                "containers": {
                    "total": len(containers),
                    "running": running,
                    "stopped": stopped,
                },
                "images": {
                    "total": len(images),
                },
                "volumes": {
                    "total": len(volumes.get("Volumes", [])),
                },
            }
        
        @mcp.tool()
        async def portainer_container_action(
            endpoint_id: int,
            container_id: str,
            action: str
        ) -> dict[str, Any]:
            """Perform an action on a container.
            
            Args:
                endpoint_id: The endpoint/environment ID
                container_id: Container ID or name
                action: Action to perform (start, stop, restart, kill, pause, unpause)
            
            Returns:
                Result of the action
            """
            valid_actions = ["start", "stop", "restart", "kill", "pause", "unpause"]
            if action not in valid_actions:
                return {"error": f"Invalid action. Must be one of: {valid_actions}"}
            
            response = await self.client.post(
                f"/endpoints/{endpoint_id}/docker/containers/{container_id}/{action}"
            )
            
            if response.status_code == 204:
                return {"success": True, "container_id": container_id, "action": action}
            else:
                return {
                    "success": False,
                    "container_id": container_id,
                    "action": action,
                    "error": response.text,
                }
        
        @mcp.tool()
        async def portainer_list_stacks(endpoint_id: int | None = None) -> list[dict[str, Any]]:
            """List all stacks (docker-compose deployments).
            
            Args:
                endpoint_id: Optional endpoint ID to filter by
            
            Returns:
                List of stacks
            """
            params = {}
            if endpoint_id:
                params["filters"] = f'{{"EndpointID":{endpoint_id}}}'
            
            response = await self.client.get("/stacks", params=params)
            response.raise_for_status()
            
            stacks = response.json()
            return [
                {
                    "id": s["Id"],
                    "name": s["Name"],
                    "type": s.get("Type", 0),
                    "endpoint_id": s.get("EndpointId"),
                    "status": "active" if s.get("Status") == 1 else "inactive",
                }
                for s in stacks
            ]
        
        logger.info("Portainer tools registered")
