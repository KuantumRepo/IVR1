"""
ESL Connection Manager - powered by Genesis (asyncio-native FreeSWITCH ESL library).

Genesis has two distinct modes:
  - Consumer: A persistent background listener for subscribing to FS events
  - Inbound:  A one-shot async context manager for sending commands (bgapi, api)

This module wraps both to provide a unified interface for the rest of the app.
"""
import asyncio
import logging
from genesis import Consumer, Inbound

from app.core.config import settings

logger = logging.getLogger(__name__)


class ESLManager:
    """
    Singleton-style manager that:
      - Runs a Genesis Consumer in the background to receive FreeSWITCH events
      - Provides a send() method that opens a short-lived Inbound connection to
        dispatch commands (bgapi originate, uuid_kill, etc.)
    """
    def __init__(self):
        self.host = settings.FS_ESL_HOST
        self.port = settings.FS_ESL_PORT
        self.password = settings.FS_ESL_PASSWORD

        # The persistent Consumer (event listener)
        self._consumer = Consumer(self.host, self.port, self.password)
        self._consumer_task: asyncio.Task | None = None
        self.connected = False

        # Public reference so handlers can register decorators
        self.consumer = self._consumer

    async def start(self):
        """
        Launch the persistent Consumer as a background asyncio task.
        Called once from app startup (lifespan).
        """
        try:
            self._consumer_task = asyncio.create_task(self._run_consumer())
            logger.info("ESL Consumer task started — listening for FreeSWITCH events")
        except Exception as e:
            logger.error(f"Failed to start ESL Consumer: {e}")

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

    async def send_command(self, cmd: str) -> str | None:
        """
        Open a short-lived Inbound connection and send a single command.
        Used for: bgapi originate, uuid_kill, uuid_transfer, reloadxml, etc.
        Returns the response text or None on failure.
        """
        try:
            async with Inbound(self.host, self.port, self.password) as client:
                response = await client.send(cmd)
                return str(response)
        except Exception as e:
            logger.error(f"ESL Inbound command failed [{cmd}]: {e}")
            return None

    async def bgapi(self, cmd: str) -> str | None:
        """Shorthand for background API calls."""
        return await self.send_command(f"bgapi {cmd}")

    async def api(self, cmd: str) -> str | None:
        """Shorthand for foreground API calls."""
        return await self.send_command(f"api {cmd}")

    async def reload_xml(self):
        await self.api("reloadxml")

    async def push_gateway_xml(self, xml_content: str, filename: str):
        filepath = f"/etc/freeswitch/sip_profiles/external/{filename}"
        try:
            with open(filepath, "w") as f:
                f.write(xml_content)
            await self.reload_xml()
            await self.bgapi("sofia profile external rescan")
            return True
        except Exception as e:
            logger.error(f"Failed to push gateway XML: {e}")
            return False


esl_manager = ESLManager()
