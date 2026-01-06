"""Netgear Orbi WiFi service implementation."""

import asyncio
import logging
from typing import Any

from fastmcp import FastMCP
from pynetgear import Netgear

from ...core.client import HTTPClient
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class OrbiConfig:
    """Orbi service configuration."""
    enabled: bool = False
    host: str = ""
    password: str = ""
    username: str = "admin"
    port: int = 80
    ssl: bool = False


class OrbiService(ServiceBase):
    """Netgear Orbi WiFi mesh system service.
    
    Provides tools for managing Orbi router and satellites:
    - List connected devices
    - Traffic monitoring
    - Block/allow devices
    - Guest WiFi control
    - System info and firmware check
    - Reboot
    """
    
    name = "orbi"
    
    def __init__(self, config: Any) -> None:
        """Initialize Orbi service."""
        super().__init__(config)
        self._netgear: Netgear | None = None
        self._logged_in = False
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client - not used for Orbi (uses pynetgear)."""
        return HTTPClient(
            base_url=f"http://{self.config.host}",
            timeout=30.0,
        )
    
    @property
    def netgear(self) -> Netgear:
        """Get or create pynetgear client."""
        if self._netgear is None:
            self._netgear = Netgear(
                password=self.config.password,
                host=self.config.host,
                user=self.config.username,
                port=self.config.port,
                ssl=self.config.ssl,
            )
        return self._netgear
    
    async def _ensure_logged_in(self) -> bool:
        """Ensure we're logged into the router."""
        if not self._logged_in:
            loop = asyncio.get_event_loop()
            self._logged_in = await loop.run_in_executor(
                None, self.netgear.login
            )
        return self._logged_in
    
    async def _run_sync(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous pynetgear function in executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: func(*args, **kwargs)
        )
    
    async def health_check(self) -> ServiceHealth:
        """Check Orbi service health."""
        try:
            logged_in = await self._ensure_logged_in()
            
            if not logged_in:
                return ServiceHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message="Failed to login to Orbi router",
                )
            
            info = await self._run_sync(self.netgear.get_info)
            
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Connected to Orbi router",
                details={
                    "model": info.get("ModelName", "Unknown") if info else "Unknown",
                    "firmware": info.get("Firmwareversion", "Unknown") if info else "Unknown",
                },
            )
        except Exception as e:
            logger.error(f"Orbi health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    async def close(self) -> None:
        """Clean up resources."""
        if self._netgear and self._logged_in:
            try:
                await self._run_sync(self._netgear.logout)
            except Exception as e:
                logger.debug(f"Error during Orbi logout: {e}")
        self._netgear = None
        self._logged_in = False
        await super().close()
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register Orbi tools with MCP."""
        
        @mcp.tool()
        async def orbi_get_info() -> dict[str, Any]:
            """Get Orbi router system information.
            
            Returns:
                Router model, serial number, firmware version, etc.
            """
            await self._ensure_logged_in()
            info = await self._run_sync(self.netgear.get_info)
            if info is None:
                return {"error": "Failed to get router info"}
            return dict(info)
        
        @mcp.tool()
        async def orbi_get_attached_devices() -> dict[str, Any]:
            """Get all devices currently connected to the Orbi network.
            
            Returns:
                List of connected devices with IP, MAC, name, connection type, etc.
            """
            await self._ensure_logged_in()
            devices = await self._run_sync(self.netgear.get_attached_devices_2)
            
            if devices is None:
                devices = await self._run_sync(self.netgear.get_attached_devices)
            
            if devices is None:
                return {"error": "Failed to get attached devices", "devices": []}
            
            device_list = []
            for device in devices:
                device_list.append({
                    "name": getattr(device, "name", "Unknown"),
                    "ip": getattr(device, "ip", ""),
                    "mac": getattr(device, "mac", ""),
                    "type": getattr(device, "type", ""),
                    "link_rate": getattr(device, "link_rate", ""),
                    "signal": getattr(device, "signal", ""),
                    "ssid": getattr(device, "ssid", ""),
                    "connection_type": getattr(device, "connection_type", getattr(device, "conn_ap_mac", "")),
                    "allow_or_block": getattr(device, "allow_or_block", ""),
                })
            
            return {
                "device_count": len(device_list),
                "devices": device_list,
            }
        
        @mcp.tool()
        async def orbi_get_traffic_meter() -> dict[str, Any]:
            """Get traffic meter statistics from the Orbi router.
            
            Returns:
                Today's and month's upload/download statistics.
            """
            await self._ensure_logged_in()
            traffic = await self._run_sync(self.netgear.get_traffic_meter)
            
            if traffic is None:
                return {"error": "Traffic meter not available or not enabled"}
            
            return dict(traffic)
        
        @mcp.tool()
        async def orbi_block_device(mac_address: str) -> dict[str, Any]:
            """Block a device from accessing the network.
            
            Args:
                mac_address: MAC address of the device to block (format: AA:BB:CC:DD:EE:FF)
            
            Returns:
                Success status of the block operation.
            """
            await self._ensure_logged_in()
            success = await self._run_sync(
                self.netgear.allow_block_device,
                mac_address,
                "Block"
            )
            return {
                "success": success,
                "action": "block",
                "mac_address": mac_address,
            }
        
        @mcp.tool()
        async def orbi_allow_device(mac_address: str) -> dict[str, Any]:
            """Allow a previously blocked device to access the network.
            
            Args:
                mac_address: MAC address of the device to allow (format: AA:BB:CC:DD:EE:FF)
            
            Returns:
                Success status of the allow operation.
            """
            await self._ensure_logged_in()
            success = await self._run_sync(
                self.netgear.allow_block_device,
                mac_address,
                "Allow"
            )
            return {
                "success": success,
                "action": "allow",
                "mac_address": mac_address,
            }
        
        @mcp.tool()
        async def orbi_check_firmware() -> dict[str, Any]:
            """Check if new firmware is available for the Orbi router.
            
            Returns:
                Current and available firmware versions.
            """
            await self._ensure_logged_in()
            firmware = await self._run_sync(self.netgear.check_new_firmware)
            
            if firmware is None:
                return {"error": "Failed to check firmware", "update_available": False}
            
            return {
                "current_version": firmware.get("CurrentVersion", "Unknown"),
                "new_version": firmware.get("NewVersion", None),
                "update_available": firmware.get("NewVersion") is not None,
                "release_note": firmware.get("ReleaseNote", ""),
            }
        
        @mcp.tool()
        async def orbi_get_guest_wifi_status() -> dict[str, Any]:
            """Get the status of guest WiFi networks.
            
            Returns:
                Status of 2.4GHz and 5GHz guest networks.
            """
            await self._ensure_logged_in()
            
            guest_2g = await self._run_sync(self.netgear.get_guest_access_enabled)
            guest_5g = await self._run_sync(self.netgear.get_5g_guest_access_enabled)
            
            return {
                "guest_2g_enabled": guest_2g,
                "guest_5g_enabled": guest_5g,
            }
        
        @mcp.tool()
        async def orbi_set_guest_wifi(
            enabled: bool,
            band: str = "both"
        ) -> dict[str, Any]:
            """Enable or disable guest WiFi networks.
            
            Args:
                enabled: True to enable, False to disable
                band: Which band to control - "2.4ghz", "5ghz", or "both"
            
            Returns:
                Result of the operation.
            """
            await self._ensure_logged_in()
            
            results = {}
            band = band.lower()
            
            if band in ("2.4ghz", "both"):
                success = await self._run_sync(
                    self.netgear.set_guest_access_enabled,
                    enabled
                )
                results["guest_2g"] = {"enabled": enabled, "success": success}
            
            if band in ("5ghz", "both"):
                success = await self._run_sync(
                    self.netgear.set_5g_guest_access_enabled,
                    enabled
                )
                results["guest_5g"] = {"enabled": enabled, "success": success}
            
            return results
        
        @mcp.tool()
        async def orbi_reboot() -> dict[str, Any]:
            """Reboot the Orbi router.
            
            Warning: This will cause a temporary network outage.
            
            Returns:
                Confirmation of reboot command sent.
            """
            await self._ensure_logged_in()
            success = await self._run_sync(self.netgear.reboot)
            self._logged_in = False  # Will need to re-login after reboot
            
            return {
                "success": success,
                "message": "Reboot command sent. Network will be temporarily unavailable.",
            }
        
        logger.info("Orbi tools registered")
