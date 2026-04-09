"""
ESL Connection Manager — Persistent Pool Architecture
======================================================

Powered by Genesis (asyncio-native FreeSWITCH ESL library).

Architecture:
  - Consumer: A single persistent connection for subscribing to FS events.
  - ESLPool:  A pool of N persistent Inbound connections for sending commands.
              Each connection is protected by an asyncio.Lock to prevent
              response interleaving (Genesis's send() is not concurrency-safe).

Why not reuse the Consumer's connection for commands?
  The Consumer's Inbound connection is busy reading events via `events plain ALL`.
  Sending a command on it would interleave command replies with event data in the
  same reader loop, corrupting the response queue. Per FreeSWITCH best practices,
  event listening and command sending use separate connections.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from genesis import Consumer, Inbound

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Connection Pool ────────────────────────────────────────────────────────────

@dataclass
class _PoolSlot:
    """A single persistent connection + its serialization lock."""
    index: int
    host: str
    port: int
    password: str
    connection: Inbound | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _healthy: bool = False

    async def connect(self) -> bool:
        """Open (or reconnect) this slot's Inbound connection."""
        try:
            if self.connection and self.connection.is_connected:
                return True

            conn = Inbound(self.host, self.port, self.password)
            await conn.start()
            self.connection = conn
            self._healthy = True
            logger.info(f"ESL Pool slot {self.index}: connected")
            return True
        except Exception as e:
            self._healthy = False
            self.connection = None
            logger.error(f"ESL Pool slot {self.index}: connect failed — {e}")
            return False

    async def disconnect(self):
        """Gracefully close this slot."""
        if self.connection:
            try:
                await self.connection.stop()
            except Exception:
                pass
            self.connection = None
            self._healthy = False

    @property
    def healthy(self) -> bool:
        return self._healthy and self.connection is not None and self.connection.is_connected

    async def send(self, cmd: str):
        """Send a command under lock. Auto-reconnects on failure."""
        async with self.lock:
            # Ensure connected
            if not self.healthy:
                if not await self.connect():
                    return None

            try:
                response = await self.connection.send(cmd)
                return response
            except Exception as e:
                logger.warning(f"ESL Pool slot {self.index}: send failed ({e}), reconnecting...")
                self._healthy = False
                # One retry after reconnect
                if await self.connect():
                    try:
                        response = await self.connection.send(cmd)
                        return response
                    except Exception as e2:
                        logger.error(f"ESL Pool slot {self.index}: retry also failed — {e2}")
                        self._healthy = False
                return None


class ESLPool:
    """
    Pool of N persistent Inbound connections with round-robin dispatch.

    Each connection is serialized via asyncio.Lock. Under high concurrency,
    commands are distributed across slots and queue behind their slot's lock.
    This gives us N concurrent in-flight commands at any time.
    """

    def __init__(self, host: str, port: int, password: str, size: int = 3):
        self.size = size
        self._slots = [
            _PoolSlot(index=i, host=host, port=port, password=password)
            for i in range(size)
        ]
        self._next = 0  # Round-robin counter

    async def start(self):
        """Open all pool connections. Called once at app startup."""
        results = await asyncio.gather(
            *(slot.connect() for slot in self._slots),
            return_exceptions=True,
        )
        connected = sum(1 for r in results if r is True)
        logger.info(f"ESL Pool: {connected}/{self.size} connections established")

    async def stop(self):
        """Close all pool connections. Called at app shutdown."""
        await asyncio.gather(*(slot.disconnect() for slot in self._slots))
        logger.info("ESL Pool: all connections closed")

    def _next_slot(self) -> _PoolSlot:
        """Round-robin slot selection."""
        slot = self._slots[self._next % self.size]
        self._next += 1
        return slot

    async def send(self, cmd: str) -> str | None:
        """
        Send a command via the next available pool slot.
        Returns the parsed response body/text or None on failure.
        """
        slot = self._next_slot()
        response = await slot.send(cmd)

        if response is None:
            return None

        # Parse response: ESLEvent dict with optional .body attribute
        if hasattr(response, "body") and response.body:
            return str(response.body).strip()

        reply = response.get("Reply-Text", "")
        if reply:
            return reply.strip()

        return str(response).strip()


# ── ESL Manager (public interface) ─────────────────────────────────────────────

class ESLManager:
    """
    Unified ESL interface for the application.

    - Consumer: persistent event listener (CHANNEL_ANSWER, EXECUTE_COMPLETE, etc.)
    - Pool: persistent command sender (sendmsg, api, bgapi)

    All handler code calls esl_manager.execute() / .api() / .bgapi() — the pool
    handles connection lifecycle transparently.
    """

    def __init__(self):
        self.host = settings.FS_ESL_HOST
        self.port = settings.FS_ESL_PORT
        self.password = settings.FS_ESL_PASSWORD
        self.pool_size = settings.FS_ESL_POOL_SIZE

        # Persistent event listener
        self._consumer = Consumer(self.host, self.port, self.password)
        self._consumer_task: asyncio.Task | None = None

        # Persistent command pool
        self._pool = ESLPool(self.host, self.port, self.password, self.pool_size)

        # Public reference for handler decorators
        self.consumer = self._consumer
        self.connected = False

    async def start(self):
        """
        Launch Consumer + Pool. Called once from app startup (lifespan).
        """
        # Start the command pool
        await self._pool.start()

        # Start the event consumer as a background task
        try:
            self._consumer_task = asyncio.create_task(self._run_consumer())
            logger.info("ESL Consumer task started — listening for FreeSWITCH events")
        except Exception as e:
            logger.error(f"Failed to start ESL Consumer: {e}")

    async def stop(self):
        """Graceful shutdown of pool + consumer."""
        await self._pool.stop()
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass

    async def _run_consumer(self):
        """Inner loop — Genesis Consumer.start() blocks until disconnected."""
        while True:
            try:
                logger.info(f"Connecting ESL Consumer to FreeSWITCH at {self.host}:{self.port}...")
                await self._consumer.start()
                self.connected = True
            except Exception as e:
                self.connected = False
                logger.error(f"ESL Consumer disconnected: {e}. Retrying in 5s...")
                await asyncio.sleep(5)

    # ── Command interface (unchanged signatures) ──────────────────────────

    async def send_command(self, cmd: str) -> str | None:
        """Send a raw ESL command via the persistent pool."""
        return await self._pool.send(cmd)

    async def bgapi(self, cmd: str) -> str | None:
        """Shorthand for background API calls."""
        return await self.send_command(f"bgapi {cmd}")

    async def api(self, cmd: str) -> str | None:
        """Shorthand for foreground API calls."""
        return await self.send_command(f"api {cmd}")

    async def execute(self, uuid: str, app: str, arg: str = "") -> str | None:
        """
        Execute an application on a channel using ESL sendmsg protocol.
        This is the industry-standard way to run apps on FreeSWITCH channels.
        """
        cmd = f"sendmsg {uuid}\ncall-command: execute\nexecute-app-name: {app}"
        if arg:
            cmd += f"\nexecute-app-arg: {arg}"
        return await self.send_command(cmd)

    async def reload_xml(self):
        await self.api("reloadxml")

    async def push_gateway_xml(self, xml_content: str, filename: str):
        import os
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        workspace_dir = os.path.dirname(backend_dir)
        filepath = os.path.join(workspace_dir, "freeswitch", "conf", "sip_profiles", "external", filename)

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w") as f:
                f.write(xml_content)
            await self.reload_xml()
            await self.bgapi("sofia profile external rescan")
            return True
        except Exception as e:
            logger.error(f"Failed to push gateway XML to {filepath}: {e}")
            return False


esl_manager = ESLManager()
