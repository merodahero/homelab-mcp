# Homelab MCP

A modular MCP (Model Context Protocol) server for homelab service management. Provides unified access to multiple homelab services through a single MCP interface.

## Features

- **Modular Architecture**: Enable only the services you need
- **Unified Health Checks**: Monitor all services from one endpoint
- **Docker Ready**: Easy deployment to Unraid, Proxmox, or Kubernetes
- **Extensible**: Easy to add new service integrations

## Supported Services

| Service | Description | Status |
|---------|-------------|--------|
| **Nginx Proxy Manager** | Reverse proxy management, SSL certificates | ✅ Ready |
| **Pi-hole** | DNS ad-blocking, query stats | ✅ Ready |
| **Uptime Kuma** | Service availability monitoring | ✅ Ready |
| **Portainer** | Docker management across hosts | ✅ Ready |
| **UPS NUT** | UPS power monitoring | ✅ Ready |
| **Netgear Orbi** | WiFi mesh system management | ✅ Ready |
| **AdGuard Home** | DNS ad-blocking alternative | ✅ Ready |
| **Technitium** | DNS server management | ✅ Ready |
| **NetBox** | DCIM/IPAM network documentation | ✅ Ready |

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/HavartiBard/homelab-mcp.git
cd homelab-mcp

# Copy and edit configuration
cp config.example.yaml config.yaml
# Edit config.yaml with your service URLs and credentials
```

### 2. Run with Docker

```bash
docker compose up -d
```

### 3. Run Locally (Development)

```bash
# Install dependencies
pip install -e .

# Run server
python -m homelab_mcp.main
```

## Configuration

Edit `config.yaml` to enable services and configure credentials:

```yaml
server:
  host: "0.0.0.0"
  port: 6971
  transport: "streamable-http"

services:
  nginx_proxy_manager:
    enabled: true
    url: "http://192.168.1.100:81"
    username: "admin@example.com"
    password: "your-password"

  pihole:
    enabled: true
    url: "http://192.168.1.53"
    api_key: "your-api-key"

  # ... more services
```

## Available Tools

### Core Tools
- `homelab_health_check` - Check health of all enabled services
- `homelab_list_services` - List configured services and status

### Nginx Proxy Manager
- `npm_list_proxy_hosts` - List all proxy hosts
- `npm_list_ssl_certificates` - List SSL certificates
- `npm_get_proxy_host` - Get proxy host details
- `npm_enable_proxy_host` / `npm_disable_proxy_host` - Toggle hosts
- `npm_check_expiring_certificates` - Find expiring SSL certs

### Pi-hole
- `pihole_get_summary` - DNS query statistics
- `pihole_get_top_queries` / `pihole_get_top_blocked` - Top domains
- `pihole_enable` / `pihole_disable` - Toggle ad blocking
- `pihole_get_query_types` - Query type breakdown

### Uptime Kuma
- `uptime_get_status_page` - Get status page info
- `uptime_get_heartbeats` - Monitor heartbeat data
- `uptime_get_monitor_summary` - Summary of all monitors

### Portainer
- `portainer_list_endpoints` - List Docker environments
- `portainer_list_containers` - List containers on endpoint
- `portainer_get_endpoint_stats` - Container/image/volume stats
- `portainer_container_action` - Start/stop/restart containers
- `portainer_list_stacks` - List docker-compose stacks

### UPS NUT
- `ups_get_status` - Battery, load, runtime info
- `ups_get_all_variables` - All UPS variables
- `ups_list_devices` - List UPS devices
- `ups_check_power_status` - Quick power status check

### Netgear Orbi
- `orbi_get_info` - Router model, serial number, firmware version
- `orbi_get_attached_devices` - List all connected devices with IP, MAC, signal strength
- `orbi_get_traffic_meter` - Bandwidth usage statistics (today/month)
- `orbi_block_device` - Block a device by MAC address
- `orbi_allow_device` - Unblock a previously blocked device
- `orbi_check_firmware` - Check for available firmware updates
- `orbi_get_guest_wifi_status` - Get guest network status (2.4GHz/5GHz)
- `orbi_set_guest_wifi` - Enable/disable guest WiFi networks
- `orbi_reboot` - Reboot the router (causes temporary network outage)

## Deployment

### Docker Compose (Recommended)

```bash
docker compose up -d
```

### Unraid

1. Copy files to `/mnt/user/appdata/homelab-mcp/`
2. Build and run:
```bash
docker build -t homelab-mcp .
docker run -d --name homelab-mcp \
  -p 6971:6971 \
  -v /mnt/user/appdata/homelab-mcp/config.yaml:/app/config.yaml:ro \
  homelab-mcp
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: homelab-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: homelab-mcp
  template:
    metadata:
      labels:
        app: homelab-mcp
    spec:
      containers:
      - name: homelab-mcp
        image: homelab-mcp:latest
        ports:
        - containerPort: 6971
        volumeMounts:
        - name: config
          mountPath: /app/config.yaml
          subPath: config.yaml
      volumes:
      - name: config
        configMap:
          name: homelab-mcp-config
```

## Adding New Services

1. Create a new directory under `homelab_mcp/services/`
2. Implement `ServiceBase` class with:
   - `_create_client()` - HTTP client setup
   - `register_tools()` - MCP tool registration
   - `health_check()` - Service health check
3. Add configuration model to `core/config.py`
4. Register in `server.py`

## MCP Client Configuration

Add to your MCP client (e.g., Windsurf):

```json
{
  "mcpServers": {
    "homelab": {
      "serverType": "streamable-http",
      "url": "http://192.168.1.100:6971/mcp"
    }
  }
}
```

## License

MIT
