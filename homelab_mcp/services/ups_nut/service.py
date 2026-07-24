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
    
    async def _query_nut(self, command: str, use_rw: bool = False) -> str:
        """Send command to NUT server and get response.

        If username/password are configured, performs LOGIN before the command.
        Set use_rw=True to authenticate as the RW user (for SET/INSTCMD); defaults
        to the read-only user.

        Args:
            command: NUT protocol command
            use_rw: Authenticate as RW user (requires config.rw_username/password)

        Returns:
            Response from NUT server
        """
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.host, self.config.port),
                timeout=10.0
            )

            # upsd does NOT send a banner — it waits for the first command.
            # We send USERNAME/PASSWORD first (if creds configured) and read
            # the OK responses. NUT's protocol: each command returns a single
            # line ("OK", "ERR <msg>", or a multi-line response ending in
            # "END <cmd>" or "ERR <msg>").

            async def _read_line() -> str:
                line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                return line.decode().strip()

            # Authenticate if creds are set
            user = self.config.rw_username if use_rw else self.config.username
            pwd = self.config.rw_password if use_rw else self.config.password
            if user and pwd:
                writer.write(f"USERNAME {user}\n".encode())
                await writer.drain()
                resp = await _read_line()
                if resp.startswith("ERR"):
                    raise PermissionError(
                        f"NUT USERNAME {user!r} rejected: {resp}")
                writer.write(f"PASSWORD {pwd}\n".encode())
                await writer.drain()
                resp = await _read_line()
                if resp.startswith("ERR"):
                    raise PermissionError(
                        f"NUT PASSWORD rejected for user {user!r}: {resp}")

            # Now issue the actual command
            writer.write(f"{command}\n".encode())
            await writer.drain()

            response_lines = []
            # NUT responses: GET <cmd> returns a single line (or ERR). LIST
            # commands return BEGIN ... END ... Multi-line reads are space-
            # delimited tokens, not line-delimited, so we use readuntil(" ")
            # when appropriate. Simpler approach: read the first line. If it
            # begins with BEGIN, continue reading until END. Otherwise we
            # already have the single-line response.
            first = await _read_line()
            if first == "":
                # No data — return empty
                writer.close()
                return ""
            if first.startswith("BEGIN"):
                # LIST response — read until END
                while True:
                    line = await _read_line()
                    if line.startswith("END") or line.startswith("ERR"):
                        break
                    if line.startswith("BEGIN LIST VAR") or line.startswith("BEGIN LIST UPS") \
                       or line.startswith("BEGIN LIST CMD") or line.startswith("BEGIN LIST CLIENT"):
                        continue
                    response_lines.append(line)
            elif first.startswith("ERR"):
                raise RuntimeError(f"NUT {command!r} error: {first}")
            else:
                # Single-line response (GET VAR, GET CMD, GET DESC, GET TRACKING, etc.)
                response_lines.append(first)

            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

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

        @mcp.tool()
        async def ups_get_var(name: str) -> str:
            """Read a single NUT variable by name (e.g. 'battery.charge', 'ups.status').

            Args:
                name: Variable name (without UPS prefix, e.g. 'battery.charge').

            Returns:
                The variable's value, or 'null' if not set.
            """
            response = await self._query_nut(f"GET VAR {self.config.ups_name} {name}")
            # Format: VAR <upsname> <varname> "<value>"
            for line in response.split("\n"):
                if line.startswith("VAR"):
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        return parts[3].strip('"')
            return "null"

        @mcp.tool()
        async def ups_list_commands() -> list[str]:
            """List instant commands available on the UPS (test.*, shutdown.*, etc.).

            Returns:
                List of command names.
            """
            response = await self._query_nut(f"LIST CMD {self.config.ups_name}")
            cmds = []
            for line in response.split("\n"):
                if line.startswith("CMD"):
                    # Format: CMD <upsname> <cmdname>
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        cmds.append(parts[2])
            return cmds

        @mcp.tool()
        async def ups_run_command(command: str, use_admin: bool = False) -> str:
            """Run an instant command on the UPS (e.g. 'test.battery.start').

            Args:
                command: Command name as listed by ups_list_commands.
                use_admin: If True, authenticate as the RW user (requires
                    rw_username/rw_password in config). DANGEROUS commands
                    (shutdown.stop, shutdown.return, fsd) require this.

            Returns:
                Server response text. Raises PermissionError if creds missing.
            """
            user = self.config.rw_username if use_admin else self.config.username
            pwd = self.config.rw_password if use_admin else self.config.password
            if use_admin and not (user and pwd):
                raise PermissionError(
                    "use_admin=True but no rw_username/rw_password configured")
            response = await self._query_nut(
                f"INSTCMD {self.config.ups_name} {command}", use_rw=use_admin)
            return response if response else f"command {command!r} dispatched"

        @mcp.tool()
        async def ups_set_var(name: str, value: str, use_admin: bool = False) -> str:
            """SET a writable NUT variable. Requires RW user credentials.

            Args:
                name: Variable name (e.g. 'ups.id').
                value: New value.
                use_admin: If True, use rw_username/rw_password.

            Returns:
                Server response, or an error if the variable is not writable.
            """
            user = self.config.rw_username if use_admin else self.config.username
            pwd = self.config.rw_password if use_admin else self.config.password
            if use_admin and not (user and pwd):
                raise PermissionError(
                    "use_admin=True but no rw_username/rw_password configured")
            response = await self._query_nut(
                f"SET VAR {self.config.ups_name} {name} \"{value}\"", use_rw=use_admin)
            return response if response else f"set {name}={value}"

        @mcp.tool()
        async def ups_get_realpower() -> dict[str, Any]:
            """Read the watts overlay UPS (e.g. srvspm3kil_realpower) if configured.

            Returns:
                {ups, watts, source} or {} if no realpower UPS is exposed.
            """
            rp_name = f"{self.config.ups_name}_realpower"
            response = await self._query_nut(f"LIST UPS")
            devices = []
            for line in response.split("\n"):
                if line.startswith("UPS"):
                    parts = line.split(" ", 2)
                    if len(parts) >= 2:
                        devices.append(parts[1])
            if rp_name not in devices:
                return {"available": False,
                        "reason": f"no UPS named {rp_name!r} on the server"}
            watts_resp = await self._query_nut(f"GET VAR {rp_name} ups.realpower")
            for line in watts_resp.split("\n"):
                if line.startswith("VAR"):
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        try:
                            return {"available": True, "ups": rp_name,
                                    "watts": float(parts[3].strip('"')),
                                    "source": "V*I*0.95 from apcsmart "
                                              f"{self.config.ups_name}"}
                        except ValueError:
                            pass
            return {"available": False, "reason": "ups.realpower not set"}

        @mcp.tool()
        async def ups_list_clients(ups: str = "") -> list[dict[str, str]]:
            """List active upsd clients (IP, hostname).

            Args:
                ups: UPS name to scope to (default: the configured ups_name).

            Returns:
                List of {ups, address} dicts.
            """
            target = ups or self.config.ups_name
            response = await self._query_nut(f"LIST CLIENT {target}")
            clients = []
            for line in response.split("\n"):
                if line.startswith("CLIENT"):
                    # Format: CLIENT <upsname> <address>
                    parts = line.split(" ", 2)
                    if len(parts) >= 3:
                        clients.append({"ups": parts[1], "address": parts[2]})
            return clients

        logger.info("UPS NUT tools registered")
