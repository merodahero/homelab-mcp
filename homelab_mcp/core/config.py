"""Configuration management for Homelab MCP."""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    """MCP server configuration."""
    host: str = "0.0.0.0"
    port: int = 6971
    transport: str = "streamable-http"


class NginxProxyManagerConfig(BaseModel):
    """Nginx Proxy Manager service configuration."""
    enabled: bool = False
    url: str = ""
    username: str = ""
    password: str = ""


class PiholeConfig(BaseModel):
    """Pi-hole service configuration."""
    enabled: bool = False
    url: str = ""
    api_key: str = ""


class UptimeKumaConfig(BaseModel):
    """Uptime Kuma service configuration."""
    enabled: bool = False
    url: str = ""
    username: str = ""
    password: str = ""


class UpsNutConfig(BaseModel):
    """UPS NUT service configuration."""
    enabled: bool = False
    host: str = ""
    port: int = 3493
    ups_name: str = "ups"


class PortainerConfig(BaseModel):
    """Portainer service configuration."""
    enabled: bool = False
    url: str = ""
    api_key: str = ""


class ServicesConfig(BaseModel):
    """All services configuration."""
    nginx_proxy_manager: NginxProxyManagerConfig = Field(default_factory=NginxProxyManagerConfig)
    pihole: PiholeConfig = Field(default_factory=PiholeConfig)
    uptime_kuma: UptimeKumaConfig = Field(default_factory=UptimeKumaConfig)
    ups_nut: UpsNutConfig = Field(default_factory=UpsNutConfig)
    portainer: PortainerConfig = Field(default_factory=PortainerConfig)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class Config(BaseModel):
    """Root configuration model."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(config_path: str | Path | None = None) -> Config:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to config file. If None, checks HOMELAB_MCP_CONFIG env var,
                    then falls back to ./config.yaml
    
    Returns:
        Loaded configuration
    """
    if config_path is None:
        config_path = os.environ.get("HOMELAB_MCP_CONFIG", "config.yaml")
    
    path = Path(config_path)
    
    if not path.exists():
        # Return default config if no file exists
        return Config()
    
    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f) or {}
    
    return Config(**data)


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config
