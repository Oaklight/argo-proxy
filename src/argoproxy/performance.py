"""
Performance optimization utilities for argo-proxy.
"""

import asyncio
import inspect
import multiprocessing
import os
from typing import Optional

import aiohttp
from tqdm import tqdm

from .utils.logging import log_debug, log_warning


class OptimizedHTTPSession:
    """Optimized HTTP session with connection pooling and performance tuning."""

    def __init__(
        self,
        *,
        total_connections: int = 100,
        connections_per_host: int = 30,
        keepalive_timeout: int = 30,
        connect_timeout: int = 10,
        read_timeout: int = 30,
        total_timeout: int = 60,
        dns_cache_ttl: int = 300,
        user_agent: str = "argo-proxy",
    ):
        """
        Initialize optimized HTTP session.

        Args:
            total_connections: Maximum total connections in pool
            connections_per_host: Maximum connections per host
            keepalive_timeout: Keep-alive timeout in seconds
            connect_timeout: Connection timeout in seconds
            read_timeout: Socket read timeout in seconds
            total_timeout: Total request timeout in seconds
            dns_cache_ttl: DNS cache TTL in seconds
            user_agent: User agent string
        """
        # Check aiohttp version for tcp_nodelay support
        connector_kwargs = {
            "limit": total_connections,
            "limit_per_host": connections_per_host,
            "ttl_dns_cache": dns_cache_ttl,
            "use_dns_cache": True,
            "keepalive_timeout": keepalive_timeout,
            "enable_cleanup_closed": True,
        }

        # Only add tcp_nodelay if supported (aiohttp >= 3.8.0)
        try:
            sig = inspect.signature(aiohttp.TCPConnector.__init__)
            if "tcp_nodelay" in sig.parameters:
                connector_kwargs["tcp_nodelay"] = True
                log_debug(
                    "TCP_NODELAY enabled for lower latency", context="performance"
                )
        except Exception:
            log_debug(
                "TCP_NODELAY not supported in this aiohttp version",
                context="performance",
            )

        self.connector = aiohttp.TCPConnector(**connector_kwargs)

        self.timeout = aiohttp.ClientTimeout(
            total=total_timeout,
            connect=connect_timeout,
            sock_read=read_timeout,
        )

        self.session: Optional[aiohttp.ClientSession] = None
        self.user_agent = user_agent

    async def create_session(self) -> aiohttp.ClientSession:
        """Create and return the HTTP session with progress indication."""
        if self.session is None or self.session.closed:
            # Show progress for connection pool creation only if it might take time
            if self.connector.limit > 100:  # Only show progress for large pools
                with tqdm(
                    total=100,
                    desc="🔗 Initializing HTTP connection pool",
                    bar_format="{desc}: {percentage:3.0f}%|{bar}|",
                    leave=False,
                    ncols=60,
                ) as pbar:
                    pbar.update(30)
                    await asyncio.sleep(0.05)

                    self.session = aiohttp.ClientSession(
                        connector=self.connector,
                        timeout=self.timeout,
                        headers={"User-Agent": self.user_agent},
                    )
                    pbar.update(70)
                    await asyncio.sleep(0.05)
            else:
                # For smaller pools, create without progress bar
                self.session = aiohttp.ClientSession(
                    connector=self.connector,
                    timeout=self.timeout,
                    headers={"User-Agent": self.user_agent},
                )

            log_debug(
                f"HTTP session created with {self.connector.limit} total connections, "
                f"{self.connector.limit_per_host} per host",
                context="performance",
            )
        return self.session

    async def close(self):
        """Close the HTTP session and connector."""
        if self.session and not self.session.closed:
            await self.session.close()
            log_debug("HTTP session closed", context="performance")

        if not self.connector.closed:
            await self.connector.close()
            log_debug("HTTP connector closed", context="performance")


async def optimize_event_loop():
    """Apply event loop optimizations for better performance."""
    try:
        # Get current event loop
        loop = asyncio.get_running_loop()

        # Set debug mode to False for production performance
        loop.set_debug(False)

        # Optimize task factory if available
        if hasattr(loop, "set_task_factory"):
            loop.set_task_factory(None)

        log_debug("Event loop optimizations applied", context="performance")

    except Exception as e:
        log_warning(
            f"Could not apply event loop optimizations: {e}", context="performance"
        )


def get_performance_config() -> dict:
    """Get performance configuration based on system capabilities."""

    # Get CPU count for scaling connection limits
    cpu_count = multiprocessing.cpu_count()

    # Scale connection limits based on CPU cores - increased for better concurrency
    base_connections = max(200, cpu_count * 20)
    base_per_host = max(50, cpu_count * 10)

    # Check for environment overrides
    total_connections = int(os.getenv("ARGO_PROXY_MAX_CONNECTIONS", base_connections))
    connections_per_host = int(
        os.getenv("ARGO_PROXY_MAX_CONNECTIONS_PER_HOST", base_per_host)
    )

    return {
        "total_connections": total_connections,
        "connections_per_host": connections_per_host,
        "keepalive_timeout": int(
            os.getenv("ARGO_PROXY_KEEPALIVE_TIMEOUT", "600")
        ),  # 10 minutes
        "connect_timeout": int(os.getenv("ARGO_PROXY_CONNECT_TIMEOUT", "10")),
        "read_timeout": int(os.getenv("ARGO_PROXY_READ_TIMEOUT", "600")),  # 10 minutes
        "total_timeout": int(
            os.getenv("ARGO_PROXY_TOTAL_TIMEOUT", "1800")
        ),  # 30 minutes
        "dns_cache_ttl": int(os.getenv("ARGO_PROXY_DNS_CACHE_TTL", "300")),
    }
