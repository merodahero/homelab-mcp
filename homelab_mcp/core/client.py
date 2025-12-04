"""HTTP client utilities for Homelab MCP services."""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HTTPClient:
    """Reusable HTTP client with common patterns for homelab services."""
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        verify_ssl: bool = False,
        headers: dict[str, str] | None = None,
    ):
        """Initialize HTTP client.
        
        Args:
            base_url: Base URL for the service
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
            headers: Default headers to include in requests
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout)
        self.verify_ssl = verify_ssl
        self.headers = headers or {}
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                verify=self.verify_ssl,
                headers=self.headers,
            )
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a GET request.
        
        Args:
            path: URL path (appended to base_url)
            params: Query parameters
            headers: Additional headers
        
        Returns:
            HTTP response
        """
        client = await self._get_client()
        response = await client.get(path, params=params, headers=headers)
        return response
    
    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a POST request.
        
        Args:
            path: URL path (appended to base_url)
            json: JSON body
            data: Form data
            headers: Additional headers
        
        Returns:
            HTTP response
        """
        client = await self._get_client()
        response = await client.post(path, json=json, data=data, headers=headers)
        return response
    
    async def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a PUT request."""
        client = await self._get_client()
        response = await client.put(path, json=json, headers=headers)
        return response
    
    async def delete(
        self,
        path: str,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a DELETE request."""
        client = await self._get_client()
        response = await client.delete(path, headers=headers)
        return response
    
    async def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request and return JSON response.
        
        Args:
            path: URL path
            params: Query parameters
        
        Returns:
            Parsed JSON response
        
        Raises:
            httpx.HTTPStatusError: If response status is not 2xx
        """
        response = await self.get(path, params=params)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
    
    async def post_json(
        self,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request and return JSON response."""
        response = await self.post(path, json=json)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result
