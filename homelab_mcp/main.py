"""Homelab MCP - Entry point."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

from .core.config import load_config, set_config
from .server import cleanup, create_server

logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for Homelab MCP server."""
    parser = argparse.ArgumentParser(
        description="Homelab MCP - A modular MCP server for homelab service management"
    )
    parser.add_argument(
        "-c", "--config",
        type=str,
        default=None,
        help="Path to configuration file (default: config.yaml or HOMELAB_MCP_CONFIG env var)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Override server host"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Override server port"
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["streamable-http", "sse", "stdio"],
        default=None,
        help="Override transport type"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Apply command-line overrides
    if args.host:
        config.server.host = args.host
    if args.port:
        config.server.port = args.port
    if args.transport:
        config.server.transport = args.transport
    
    # Set global config
    set_config(config)
    
    # Create server
    mcp = create_server(config)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig: int, frame: object) -> None:
        logger.info("Received shutdown signal, cleaning up...")
        asyncio.get_event_loop().run_until_complete(cleanup())
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the server
    logger.info(
        f"Starting Homelab MCP server on {config.server.host}:{config.server.port} "
        f"(transport: {config.server.transport})"
    )
    
    if config.server.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport=config.server.transport,
            host=config.server.host,
            port=config.server.port,
        )


if __name__ == "__main__":
    main()
