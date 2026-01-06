"""Tests for configuration module."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from homelab_mcp.core.config import (
    Config,
    LoggingConfig,
    ServerConfig,
    ServicesConfig,
    load_config,
    get_config,
    set_config,
)


class TestServerConfig:
    """Tests for ServerConfig model."""

    def test_default_values(self):
        """Test default server configuration values."""
        config = ServerConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 6971
        assert config.transport == "streamable-http"

    def test_custom_values(self):
        """Test custom server configuration values."""
        config = ServerConfig(host="127.0.0.1", port=8080, transport="sse")
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.transport == "sse"


class TestLoggingConfig:
    """Tests for LoggingConfig model."""

    def test_default_values(self):
        """Test default logging configuration values."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert "%(asctime)s" in config.format

    def test_custom_level(self):
        """Test custom log level."""
        config = LoggingConfig(level="DEBUG")
        assert config.level == "DEBUG"


class TestServicesConfig:
    """Tests for ServicesConfig model."""

    def test_all_services_disabled_by_default(self):
        """Test that all services are disabled by default."""
        config = ServicesConfig()
        assert config.nginx_proxy_manager.enabled is False
        assert config.pihole.enabled is False
        assert config.uptime_kuma.enabled is False
        assert config.ups_nut.enabled is False
        assert config.portainer.enabled is False
        assert config.adguard_home.enabled is False
        assert config.technitium.enabled is False
        assert config.netbox.enabled is False


class TestConfig:
    """Tests for root Config model."""

    def test_default_config(self):
        """Test default root configuration."""
        config = Config()
        assert isinstance(config.server, ServerConfig)
        assert isinstance(config.services, ServicesConfig)
        assert isinstance(config.logging, LoggingConfig)

    def test_nested_config(self):
        """Test nested configuration from dict."""
        data = {
            "server": {"port": 9000},
            "services": {
                "pihole": {"enabled": True, "url": "http://localhost:80"}
            },
            "logging": {"level": "DEBUG"},
        }
        config = Config(**data)
        assert config.server.port == 9000
        assert config.services.pihole.enabled is True
        assert config.services.pihole.url == "http://localhost:80"
        assert config.logging.level == "DEBUG"


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_nonexistent_file_returns_defaults(self):
        """Test that loading nonexistent file returns default config."""
        config = load_config("/nonexistent/path/config.yaml")
        assert config.server.port == 6971
        assert config.services.pihole.enabled is False

    def test_load_from_yaml_file(self):
        """Test loading configuration from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({
                "server": {"port": 7777},
                "services": {"pihole": {"enabled": True}},
            }, f)
            f.flush()
            
            try:
                config = load_config(f.name)
                assert config.server.port == 7777
                assert config.services.pihole.enabled is True
            finally:
                os.unlink(f.name)

    def test_load_from_env_var(self, monkeypatch):
        """Test loading configuration from HOMELAB_MCP_CONFIG env var."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"server": {"port": 8888}}, f)
            f.flush()
            
            try:
                monkeypatch.setenv("HOMELAB_MCP_CONFIG", f.name)
                config = load_config()
                assert config.server.port == 8888
            finally:
                os.unlink(f.name)


class TestGlobalConfig:
    """Tests for global config get/set."""

    def test_set_and_get_config(self):
        """Test setting and getting global config."""
        custom_config = Config(server=ServerConfig(port=5555))
        set_config(custom_config)
        
        retrieved = get_config()
        assert retrieved.server.port == 5555
