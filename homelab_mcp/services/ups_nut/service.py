"""UPS NUT (Network UPS Tools) service implementation."""

import asyncio
import logging
from typing import Any

from fastmcp import FastMCP

from ...core.client import HTTPClient
from ...core.config import UpsNutConfig
from ...core.health import HealthStatus, ServiceHealth
from ..base import ServiceBase

logger = logging.getLogger(__name__)


class UpsNutService(ServiceBase):
    """UPS NUT service for monitoring UPS power status."""
    
    name = "ups_nut"
    
    def __init__(self, config: UpsNutConfig) -> None:
        """Initialize UPS NUT service."""
        super().__init__(config)
        self.config: UpsNutConfig = config
    
    def _create_client(self) -> HTTPClient:
        """Create HTTP client - not used for NUT, uses raw TCP."""
        # NUT uses a custom TCP protocol, not HTTP
        return HTTPClient(base_url="http://localhost", timeout=10.0)
    
    async def _query_nut(self, command: str) -> str:
        """Send command to NUT server and get response.
        
        Args:
            command: NUT protocol command
        
        Returns:
            Response from NUT server
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.host, self.config.port),
                timeout=10.0
            )
            
            writer.write(f"{command}\n".encode())
            await writer.drain()
            
            response_lines = []
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if not line:
                    break
                decoded = line.decode().strip()
                if decoded.startswith("END") or decoded.startswith("ERR"):
                    break
                response_lines.append(decoded)
            
            writer.close()
            await writer.wait_closed()
            
            return "\n".join(response_lines)
        except Exception as e:
            logger.error(f"NUT query failed: {e}")
            raise
    
    async def _get_ups_vars(self) -> dict[str, str]:
        """Get all UPS variables.
        
        Returns:
            Dictionary of UPS variables
        """
        response = await self._query_nut(f"LIST VAR {self.config.ups_name}")
        
        variables: dict[str, str] = {}
        for line in response.split("\n"):
            if line.startswith("VAR"):
                # Format: VAR upsname varname "value"
                parts = line.split(" ", 3)
                if len(parts) >= 4:
                    var_name = parts[2]
                    var_value = parts[3].strip('"')
                    variables[var_name] = var_value
        
        return variables
    
    async def health_check(self) -> ServiceHealth:
        """Check UPS NUT service health."""
        try:
            variables = await self._get_ups_vars()
            
            status = variables.get("ups.status", "unknown")
            battery_charge = variables.get("battery.charge", "0")
            
            # Determine health based on UPS status
            if "OL" in status:  # Online
                health_status = HealthStatus.HEALTHY
            elif "OB" in status:  # On Battery
                health_status = HealthStatus.DEGRADED
            elif "LB" in status:  # Low Battery
                health_status = HealthStatus.UNHEALTHY
            else:
                health_status = HealthStatus.UNKNOWN
            
            return ServiceHealth(
                name=self.name,
                status=health_status,
                message=f"UPS status: {status}, Battery: {battery_charge}%",
                details={
                    "ups_status": status,
                    "battery_charge": battery_charge,
                    "ups_name": self.config.ups_name,
                },
            )
        except Exception as e:
            logger.error(f"UPS NUT health check failed: {e}")
            return ServiceHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
            )
    
    def register_tools(self, mcp: FastMCP) -> None:
        """Register UPS NUT tools with MCP."""
        
        @mcp.tool()
        async def ups_get_status() -> dict[str, Any]:
            """Get current UPS status and battery information.
            
            Returns:
                UPS status including battery charge, load, and runtime
            """
            variables = await self._get_ups_vars()
            
            return {
                "ups_name": self.config.ups_name,
                "status": variables.get("ups.status", "unknown"),
                "battery": {
                    "charge_percent": float(variables.get("battery.charge", 0)),
                    "voltage": float(variables.get("battery.voltage", 0)),
                    "runtime_seconds": int(variables.get("battery.runtime", 0)),
                },
                "load_percent": float(variables.get("ups.load", 0)),
                "input": {
                    "voltage": float(variables.get("input.voltage", 0)),
                    "frequency": float(variables.get("input.frequency", 0)),
                },
                "output": {
                    "voltage": float(variables.get("output.voltage", 0)),
                },
            }
        
        @mcp.tool()
        async def ups_get_all_variables() -> dict[str, str]:
            """Get all UPS variables from NUT.
            
            Returns:
                All available UPS variables
            """
            return await self._get_ups_vars()
        
        @mcp.tool()
        async def ups_list_devices() -> list[str]:
            """List all UPS devices known to the NUT server.
            
            Returns:
                List of UPS device names
            """
            response = await self._query_nut("LIST UPS")
            
            devices = []
            for line in response.split("\n"):
                if line.startswith("UPS"):
                    parts = line.split(" ", 2)
                    if len(parts) >= 2:
                        devices.append(parts[1])
            
            return devices
        
        @mcp.tool()
        async def ups_check_power_status() -> dict[str, Any]:
            """Quick check if UPS is on mains power or battery.
            
            Returns:
                Power status summary
            """
            variables = await self._get_ups_vars()
            status = variables.get("ups.status", "")
            
            on_battery = "OB" in status
            low_battery = "LB" in status
            charging = "CHRG" in status
            
            runtime_seconds = int(variables.get("battery.runtime", 0))
            runtime_minutes = runtime_seconds // 60
            
            return {
                "on_mains_power": not on_battery,
                "on_battery": on_battery,
                "low_battery": low_battery,
                "charging": charging,
                "battery_charge_percent": float(variables.get("battery.charge", 0)),
                "estimated_runtime_minutes": runtime_minutes,
                "raw_status": status,
            }
        
        logger.info("UPS NUT tools registered")
