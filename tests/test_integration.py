"""Integration tests for the MCP server."""


import httpx

from homelab_mcp.core.config import Config, ServerConfig
from homelab_mcp.server import create_server


class TestServerIntegration:
    """Integration tests for server functionality."""

    def test_server_creates_with_all_services_disabled(self):
        """Test server creates successfully with no services enabled."""
        config = Config()
        mcp = create_server(config)
        assert mcp is not None

    def test_server_creates_with_custom_port(self):
        """Test server creates with custom port configuration."""
        config = Config(server=ServerConfig(port=9999))
        mcp = create_server(config)
        assert mcp is not None

    def test_server_supports_different_transports(self):
        """Test server accepts different transport configurations."""
        for transport in ["streamable-http", "sse", "stdio"]:
            config = Config(server=ServerConfig(transport=transport))
            mcp = create_server(config)
            assert mcp is not None


class TestHealthEndpoint:
    """Tests for health check functionality."""

    async def test_healthz_returns_ok(self):
        """The HTTP process health endpoint returns a stable success payload."""
        app = create_server(Config()).http_app()

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "homelab-mcp"}

    async def test_health_check_returns_dict(self):
        """Test that health check tool returns proper structure."""
        from homelab_mcp.core.health import health_checker
        
        result = await health_checker.check_all()
        d = result.to_dict()
        
        assert "status" in d
        assert "services" in d
        assert "summary" in d
        assert d["summary"]["total"] >= 0
