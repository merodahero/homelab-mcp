"""Tests for health check module."""

import pytest

from homelab_mcp.core.health import (
    HealthChecker,
    HealthStatus,
    OverallHealth,
    ServiceHealth,
)


class TestHealthStatus:
    """Tests for HealthStatus enum."""

    def test_status_values(self):
        """Test health status enum values."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


class TestServiceHealth:
    """Tests for ServiceHealth model."""

    def test_healthy_service(self):
        """Test healthy service health."""
        health = ServiceHealth(
            name="test_service",
            status=HealthStatus.HEALTHY,
            message="All good",
        )
        assert health.name == "test_service"
        assert health.status == HealthStatus.HEALTHY
        assert health.message == "All good"
        assert health.details == {}

    def test_unhealthy_service_with_details(self):
        """Test unhealthy service with details."""
        health = ServiceHealth(
            name="failing_service",
            status=HealthStatus.UNHEALTHY,
            message="Connection failed",
            details={"error": "timeout", "retries": 3},
        )
        assert health.status == HealthStatus.UNHEALTHY
        assert health.details["error"] == "timeout"

    def test_to_dict(self):
        """Test converting service health to dict."""
        health = ServiceHealth(
            name="test",
            status=HealthStatus.HEALTHY,
            message="OK",
        )
        d = health.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "healthy"
        assert d["message"] == "OK"
        assert "last_check" in d
        assert "latency_ms" in d


class TestOverallHealth:
    """Tests for OverallHealth model."""

    def test_all_healthy(self):
        """Test overall health when all services healthy."""
        services = [
            ServiceHealth(name="s1", status=HealthStatus.HEALTHY, message="OK"),
            ServiceHealth(name="s2", status=HealthStatus.HEALTHY, message="OK"),
        ]
        overall = OverallHealth(status=HealthStatus.HEALTHY, services=services)
        assert overall.status == HealthStatus.HEALTHY

    def test_to_dict(self):
        """Test converting overall health to dict."""
        services = [
            ServiceHealth(name="s1", status=HealthStatus.HEALTHY, message="OK"),
        ]
        overall = OverallHealth(status=HealthStatus.HEALTHY, services=services)
        d = overall.to_dict()
        assert d["status"] == "healthy"
        assert len(d["services"]) == 1
        assert d["services"][0]["name"] == "s1"


class TestHealthChecker:
    """Tests for HealthChecker class."""

    @pytest.fixture
    def checker(self):
        """Create a fresh health checker for each test."""
        return HealthChecker()

    async def test_register_and_check_healthy(self, checker):
        """Test registering and checking a healthy service."""
        async def healthy_check():
            return ServiceHealth(
                name="test",
                status=HealthStatus.HEALTHY,
                message="OK",
            )
        
        checker.register("test", healthy_check)
        result = await checker.check_service("test")
        assert result.status == HealthStatus.HEALTHY

    async def test_check_unregistered_service(self, checker):
        """Test checking an unregistered service."""
        result = await checker.check_service("nonexistent")
        assert result.status == HealthStatus.UNKNOWN
        assert "no health check registered" in result.message.lower()

    async def test_check_all_services(self, checker):
        """Test checking all registered services."""
        async def healthy_check():
            return ServiceHealth(name="s1", status=HealthStatus.HEALTHY, message="OK")
        
        async def unhealthy_check():
            return ServiceHealth(name="s2", status=HealthStatus.UNHEALTHY, message="Failed")
        
        checker.register("s1", healthy_check)
        checker.register("s2", unhealthy_check)
        
        overall = await checker.check_all()
        assert overall.status == HealthStatus.UNHEALTHY  # One unhealthy = overall unhealthy
        assert len(overall.services) == 2

    async def test_check_all_empty(self, checker):
        """Test check_all with no registered services."""
        overall = await checker.check_all()
        assert overall.status == HealthStatus.HEALTHY
        assert len(overall.services) == 0

    async def test_exception_in_health_check(self, checker):
        """Test that exceptions in health checks are handled."""
        async def failing_check():
            raise RuntimeError("Check failed!")
        
        checker.register("failing", failing_check)
        result = await checker.check_service("failing")
        assert result.status == HealthStatus.UNHEALTHY
        assert "Check failed!" in result.message
