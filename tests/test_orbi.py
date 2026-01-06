"""Tests for Orbi WiFi service module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homelab_mcp.core.config import OrbiConfig
from homelab_mcp.core.health import HealthStatus
from homelab_mcp.services.orbi import OrbiService


@pytest.fixture
def orbi_config():
    """Create a test Orbi configuration."""
    return OrbiConfig(
        enabled=True,
        host="192.168.1.1",
        password="testpass",
        username="admin",
        port=80,
        ssl=False,
    )


@pytest.fixture
def orbi_service(orbi_config):
    """Create an Orbi service instance for testing."""
    return OrbiService(orbi_config)


class TestOrbiConfig:
    """Tests for OrbiConfig model."""

    def test_default_values(self):
        """Test default Orbi configuration values."""
        config = OrbiConfig()
        assert config.enabled is False
        assert config.host == ""
        assert config.username == "admin"
        assert config.port == 80
        assert config.ssl is False

    def test_custom_values(self):
        """Test custom Orbi configuration values."""
        config = OrbiConfig(
            enabled=True,
            host="orbilogin.com",
            password="secret",
            username="admin",
            port=443,
            ssl=True,
        )
        assert config.enabled is True
        assert config.host == "orbilogin.com"
        assert config.password == "secret"
        assert config.port == 443
        assert config.ssl is True


class TestOrbiService:
    """Tests for OrbiService class."""

    def test_service_name(self, orbi_service):
        """Test service name is correct."""
        assert orbi_service.name == "orbi"

    def test_netgear_client_creation(self, orbi_service):
        """Test that netgear client is created lazily."""
        assert orbi_service._netgear is None
        
        with patch("homelab_mcp.services.orbi.service.Netgear") as mock_netgear:
            _ = orbi_service.netgear
            mock_netgear.assert_called_once_with(
                password="testpass",
                host="192.168.1.1",
                user="admin",
                port=80,
                ssl=False,
            )

    @pytest.mark.asyncio
    async def test_health_check_success(self, orbi_service):
        """Test health check returns healthy when connected."""
        with patch.object(orbi_service, "_ensure_logged_in", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = True
            
            with patch.object(orbi_service, "_run_sync", new_callable=AsyncMock) as mock_run:
                mock_run.return_value = {
                    "ModelName": "Orbi RBR850",
                    "Firmwareversion": "4.6.8.2",
                }
                
                health = await orbi_service.health_check()
                
                assert health.status == HealthStatus.HEALTHY
                assert "Orbi RBR850" in health.details.get("model", "")

    @pytest.mark.asyncio
    async def test_health_check_login_failure(self, orbi_service):
        """Test health check returns unhealthy when login fails."""
        with patch.object(orbi_service, "_ensure_logged_in", new_callable=AsyncMock) as mock_login:
            mock_login.return_value = False
            
            health = await orbi_service.health_check()
            
            assert health.status == HealthStatus.UNHEALTHY
            assert "login" in health.message.lower()

    @pytest.mark.asyncio
    async def test_health_check_exception(self, orbi_service):
        """Test health check handles exceptions gracefully."""
        with patch.object(orbi_service, "_ensure_logged_in", new_callable=AsyncMock) as mock_login:
            mock_login.side_effect = Exception("Connection refused")
            
            health = await orbi_service.health_check()
            
            assert health.status == HealthStatus.UNHEALTHY
            assert "Connection refused" in health.message

    @pytest.mark.asyncio
    async def test_close_cleanup(self, orbi_service):
        """Test that close properly cleans up resources."""
        orbi_service._logged_in = True
        orbi_service._netgear = MagicMock()
        
        with patch.object(orbi_service, "_run_sync", new_callable=AsyncMock):
            await orbi_service.close()
        
        assert orbi_service._netgear is None
        assert orbi_service._logged_in is False


class TestOrbiServiceTools:
    """Tests for Orbi service MCP tools."""

    def test_tools_register(self, orbi_service):
        """Test that tools are registered without error."""
        mock_mcp = MagicMock()
        mock_mcp.tool = MagicMock(return_value=lambda f: f)
        
        # Should not raise
        orbi_service.register_tools(mock_mcp)
        
        # Verify tool decorator was called multiple times
        assert mock_mcp.tool.call_count >= 8  # We have 8+ tools
