"""NetBox DCIM/IPAM service implementation."""

import logging
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class NetBoxConfig:
    """NetBox configuration."""
    def __init__(
        self,
        enabled: bool = False,
        url: str = "",
        api_token: str = "",
    ):
        self.enabled = enabled
        self.url = url
        self.api_token = api_token


class NetBoxService(ServiceBase):
    """NetBox service for DCIM and IPAM management."""
    
    name = "netbox"
    
    def __init__(self, config: NetBoxConfig) -> None:
        """Initialize NetBox service."""
        super().__init__(config)
        self.config: NetBoxConfig = config
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client for NetBox API."""
        return HTTPClient(
            base_url=f"{self.config.url}/api",
            timeout=30.0,
            verify_ssl=False,
            headers={
                "Authorization": f"Token {self.config.api_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
    
    async def health_check(self) -> ServiceHealth:
        """Check NetBox service health."""
        try:
            response = await self.client.get("/status/")
            response.raise_for_status()
            data = response.json()
            
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="NetBox is running",
                details={
                    "netbox_version": data.get("netbox-version", "unknown"),
                    "python_version": data.get("python-version", "unknown"),
                    "django_version": data.get("django-version", "unknown"),
                },
            )
        except Exception as e:
            logger.error(f"NetBox health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register NetBox tools with MCP."""
        
        # ==================== DCIM Tools ====================
        
        @mcp.tool()
        async def netbox_list_sites() -> list[dict[str, Any]]:
            """List all sites/locations.
            
            Returns:
                List of sites
            """
            response = await self.client.get("/dcim/sites/")
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": s["id"],
                    "name": s["name"],
                    "slug": s["slug"],
                    "status": s.get("status", {}).get("value"),
                    "region": s.get("region", {}).get("name") if s.get("region") else None,
                    "facility": s.get("facility"),
                    "description": s.get("description"),
                }
                for s in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_list_racks(site_id: int | None = None) -> list[dict[str, Any]]:
            """List all racks, optionally filtered by site.
            
            Args:
                site_id: Optional site ID to filter by
            
            Returns:
                List of racks
            """
            params = {}
            if site_id:
                params["site_id"] = site_id
            
            response = await self.client.get("/dcim/racks/", params=params)
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": r["id"],
                    "name": r["name"],
                    "site": r.get("site", {}).get("name"),
                    "status": r.get("status", {}).get("value"),
                    "u_height": r.get("u_height"),
                    "desc_units": r.get("desc_units"),
                }
                for r in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_list_devices(
            site_id: int | None = None,
            rack_id: int | None = None,
            role: str | None = None
        ) -> list[dict[str, Any]]:
            """List all devices with optional filters.
            
            Args:
                site_id: Filter by site
                rack_id: Filter by rack
                role: Filter by device role
            
            Returns:
                List of devices
            """
            params = {}
            if site_id:
                params["site_id"] = site_id
            if rack_id:
                params["rack_id"] = rack_id
            if role:
                params["role"] = role
            
            response = await self.client.get("/dcim/devices/", params=params)
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": d["id"],
                    "name": d["name"],
                    "device_type": d.get("device_type", {}).get("display"),
                    "role": d.get("role", {}).get("name"),
                    "site": d.get("site", {}).get("name"),
                    "rack": d.get("rack", {}).get("name") if d.get("rack") else None,
                    "position": d.get("position"),
                    "status": d.get("status", {}).get("value"),
                    "primary_ip": d.get("primary_ip", {}).get("address") if d.get("primary_ip") else None,
                    "serial": d.get("serial"),
                    "asset_tag": d.get("asset_tag"),
                }
                for d in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_get_device(device_id: int) -> dict[str, Any]:
            """Get detailed information about a device.
            
            Args:
                device_id: Device ID
            
            Returns:
                Device details
            """
            response = await self.client.get(f"/dcim/devices/{device_id}/")
            response.raise_for_status()
            return response.json()
        
        @mcp.tool()
        async def netbox_list_device_types() -> list[dict[str, Any]]:
            """List all device types.
            
            Returns:
                List of device types
            """
            response = await self.client.get("/dcim/device-types/")
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": dt["id"],
                    "manufacturer": dt.get("manufacturer", {}).get("name"),
                    "model": dt["model"],
                    "slug": dt["slug"],
                    "u_height": dt.get("u_height"),
                    "is_full_depth": dt.get("is_full_depth"),
                }
                for dt in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_create_device(
            name: str,
            device_type_id: int,
            role_id: int,
            site_id: int,
            status: str = "active",
            rack_id: int | None = None,
            position: int | None = None,
            serial: str | None = None,
            asset_tag: str | None = None
        ) -> dict[str, Any]:
            """Create a new device.
            
            Args:
                name: Device name
                device_type_id: Device type ID
                role_id: Device role ID
                site_id: Site ID
                status: Status (active, planned, staged, failed, etc.)
                rack_id: Optional rack ID
                position: Optional rack position (U)
                serial: Optional serial number
                asset_tag: Optional asset tag
            
            Returns:
                Created device
            """
            payload: dict[str, Any] = {
                "name": name,
                "device_type": device_type_id,
                "role": role_id,
                "site": site_id,
                "status": status,
            }
            
            if rack_id:
                payload["rack"] = rack_id
            if position:
                payload["position"] = position
            if serial:
                payload["serial"] = serial
            if asset_tag:
                payload["asset_tag"] = asset_tag
            
            response = await self.client.post("/dcim/devices/", json=payload)
            response.raise_for_status()
            return response.json()
        
        # ==================== IPAM Tools ====================
        
        @mcp.tool()
        async def netbox_list_prefixes(vrf_id: int | None = None) -> list[dict[str, Any]]:
            """List IP prefixes/subnets.
            
            Args:
                vrf_id: Optional VRF ID to filter by
            
            Returns:
                List of prefixes
            """
            params = {}
            if vrf_id:
                params["vrf_id"] = vrf_id
            
            response = await self.client.get("/ipam/prefixes/", params=params)
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": p["id"],
                    "prefix": p["prefix"],
                    "status": p.get("status", {}).get("value"),
                    "vrf": p.get("vrf", {}).get("name") if p.get("vrf") else "Global",
                    "site": p.get("site", {}).get("name") if p.get("site") else None,
                    "vlan": p.get("vlan", {}).get("display") if p.get("vlan") else None,
                    "description": p.get("description"),
                    "is_pool": p.get("is_pool"),
                }
                for p in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_list_ip_addresses(
            prefix: str | None = None,
            device_id: int | None = None
        ) -> list[dict[str, Any]]:
            """List IP addresses with optional filters.
            
            Args:
                prefix: Filter by parent prefix
                device_id: Filter by assigned device
            
            Returns:
                List of IP addresses
            """
            params = {}
            if prefix:
                params["parent"] = prefix
            if device_id:
                params["device_id"] = device_id
            
            response = await self.client.get("/ipam/ip-addresses/", params=params)
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": ip["id"],
                    "address": ip["address"],
                    "status": ip.get("status", {}).get("value"),
                    "dns_name": ip.get("dns_name"),
                    "description": ip.get("description"),
                    "assigned_object": ip.get("assigned_object_type"),
                    "assigned_to": ip.get("assigned_object", {}).get("display") if ip.get("assigned_object") else None,
                }
                for ip in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_create_ip_address(
            address: str,
            status: str = "active",
            dns_name: str | None = None,
            description: str | None = None,
            vrf_id: int | None = None
        ) -> dict[str, Any]:
            """Create a new IP address.
            
            Args:
                address: IP address with prefix (e.g., '192.168.1.10/24')
                status: Status (active, reserved, deprecated, dhcp, slaac)
                dns_name: Optional DNS name
                description: Optional description
                vrf_id: Optional VRF ID
            
            Returns:
                Created IP address
            """
            payload: dict[str, Any] = {
                "address": address,
                "status": status,
            }
            
            if dns_name:
                payload["dns_name"] = dns_name
            if description:
                payload["description"] = description
            if vrf_id:
                payload["vrf"] = vrf_id
            
            response = await self.client.post("/ipam/ip-addresses/", json=payload)
            response.raise_for_status()
            return response.json()
        
        @mcp.tool()
        async def netbox_list_vlans(site_id: int | None = None) -> list[dict[str, Any]]:
            """List VLANs.
            
            Args:
                site_id: Optional site ID to filter by
            
            Returns:
                List of VLANs
            """
            params = {}
            if site_id:
                params["site_id"] = site_id
            
            response = await self.client.get("/ipam/vlans/", params=params)
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": v["id"],
                    "vid": v["vid"],
                    "name": v["name"],
                    "status": v.get("status", {}).get("value"),
                    "site": v.get("site", {}).get("name") if v.get("site") else None,
                    "group": v.get("group", {}).get("name") if v.get("group") else None,
                    "description": v.get("description"),
                }
                for v in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_get_available_ips(prefix_id: int, limit: int = 10) -> list[str]:
            """Get available IP addresses in a prefix.
            
            Args:
                prefix_id: Prefix ID
                limit: Number of IPs to return
            
            Returns:
                List of available IP addresses
            """
            response = await self.client.get(
                f"/ipam/prefixes/{prefix_id}/available-ips/",
                params={"limit": limit}
            )
            response.raise_for_status()
            data = response.json()
            
            return [ip["address"] for ip in data]
        
        # ==================== Virtualization Tools ====================
        
        @mcp.tool()
        async def netbox_list_virtual_machines(
            cluster_id: int | None = None,
            status: str | None = None
        ) -> list[dict[str, Any]]:
            """List virtual machines.
            
            Args:
                cluster_id: Filter by cluster
                status: Filter by status
            
            Returns:
                List of VMs
            """
            params = {}
            if cluster_id:
                params["cluster_id"] = cluster_id
            if status:
                params["status"] = status
            
            response = await self.client.get("/virtualization/virtual-machines/", params=params)
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": vm["id"],
                    "name": vm["name"],
                    "status": vm.get("status", {}).get("value"),
                    "cluster": vm.get("cluster", {}).get("name") if vm.get("cluster") else None,
                    "role": vm.get("role", {}).get("name") if vm.get("role") else None,
                    "vcpus": vm.get("vcpus"),
                    "memory": vm.get("memory"),
                    "disk": vm.get("disk"),
                    "primary_ip": vm.get("primary_ip", {}).get("address") if vm.get("primary_ip") else None,
                }
                for vm in data.get("results", [])
            ]
        
        @mcp.tool()
        async def netbox_list_clusters() -> list[dict[str, Any]]:
            """List virtualization clusters.
            
            Returns:
                List of clusters
            """
            response = await self.client.get("/virtualization/clusters/")
            response.raise_for_status()
            data = response.json()
            
            return [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "type": c.get("type", {}).get("name"),
                    "site": c.get("site", {}).get("name") if c.get("site") else None,
                    "device_count": c.get("device_count", 0),
                    "virtualmachine_count": c.get("virtualmachine_count", 0),
                }
                for c in data.get("results", [])
            ]
        
        # ==================== Search & Inventory ====================
        
        @mcp.tool()
        async def netbox_search(query: str) -> dict[str, Any]:
            """Search across all NetBox objects.
            
            Args:
                query: Search query
            
            Returns:
                Search results grouped by object type
            """
            response = await self.client.get("/search/", params={"q": query})
            response.raise_for_status()
            data = response.json()
            
            results: dict[str, list[dict[str, Any]]] = {}
            for item in data.get("results", []):
                obj_type = item.get("object_type", "unknown")
                if obj_type not in results:
                    results[obj_type] = []
                results[obj_type].append({
                    "id": item.get("id"),
                    "display": item.get("display"),
                    "url": item.get("url"),
                })
            
            return {
                "query": query,
                "total_results": len(data.get("results", [])),
                "results_by_type": results,
            }
        
        @mcp.tool()
        async def netbox_get_inventory_summary() -> dict[str, Any]:
            """Get a summary of all inventory in NetBox.
            
            Returns:
                Inventory counts by category
            """
            # Fetch counts from various endpoints
            sites = await self.client.get("/dcim/sites/", params={"limit": 1})
            devices = await self.client.get("/dcim/devices/", params={"limit": 1})
            racks = await self.client.get("/dcim/racks/", params={"limit": 1})
            vms = await self.client.get("/virtualization/virtual-machines/", params={"limit": 1})
            prefixes = await self.client.get("/ipam/prefixes/", params={"limit": 1})
            ip_addresses = await self.client.get("/ipam/ip-addresses/", params={"limit": 1})
            vlans = await self.client.get("/ipam/vlans/", params={"limit": 1})
            
            return {
                "dcim": {
                    "sites": sites.json().get("count", 0),
                    "racks": racks.json().get("count", 0),
                    "devices": devices.json().get("count", 0),
                },
                "virtualization": {
                    "virtual_machines": vms.json().get("count", 0),
                },
                "ipam": {
                    "prefixes": prefixes.json().get("count", 0),
                    "ip_addresses": ip_addresses.json().get("count", 0),
                    "vlans": vlans.json().get("count", 0),
                },
            }
        
        logger.info("NetBox tools registered")
