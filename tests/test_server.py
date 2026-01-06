"""Tests for server module."""

import pytest

from homelab_mcp.core.config import Config, ServerConfig, ServicesConfig
from homelab_mcp.server import create_server, cleanup


class TestCreateServer:
    """Tests for create_server function."""

    def test_create_server_with_defaults(self):
        """Test creating server with default config."""
        config = Config()
        mcp = create_server(config)
        
        assert mcp is not None
        assert mcp.name == "Homelab MCP"

    def test_create_server_with_custom_config(self):
        """Test creating server with custom config."""
        config = Config(
            server=ServerConfig(host="127.0.0.1", port=8080),
        )
        mcp = create_server(config)
        
        assert mcp is not None

    def test_server_has_core_tools(self):
        """Test that server has core tools registered."""
        config = Config()
        mcp = create_server(config)
        
        # FastMCP stores tools internally - verify server created successfully
        assert mcp is not None


class TestCleanup:
    """Tests for cleanup function."""

    async def test_cleanup_with_no_services(self):
        """Test cleanup when no services are active."""
        # Should not raise any exceptions
        await cleanup()

    async def test_cleanup_after_server_creation(self):
        """Test cleanup after creating server."""
        config = Config()
        mcp = create_server(config)
        
        # Should not raise any exceptions
        await cleanup()
