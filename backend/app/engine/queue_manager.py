"""
Campaign Queue Manager — Dynamic mod_callcenter queue lifecycle.

Creates/destroys FreeSWitch callcenter queues per campaign so each campaign
routes transfers to its own agent pool. Uses the standard mod_callcenter
approach: write queue XML → callcenter_config queue load → manage tiers via ESL.

Thread safety: mod_callcenter's command handlers are thread-safe for tier add/del
and queue load operations. The key rule is: create the queue and add tiers
BEFORE any call tries to transfer to it (done at campaign start).
"""
import os
import logging
from pathlib import Path
from uuid import UUID
from typing import List

from app.esl.connection import esl_manager
from app.core.config import settings

logger = logging.getLogger(__name__)

# Queue XML files live alongside callcenter.conf.xml
QUEUE_DIR = Path(settings.FS_CONF_DIR) / "autoload_configs" / "campaign_queues"


def _queue_name(campaign_id: UUID | str) -> str:
    """Canonical mod_callcenter queue name for a campaign."""
    return f"campaign_{str(campaign_id)}"


def _queue_xml_path(campaign_id: UUID | str) -> Path:
    """Path to the queue XML file on disk."""
    return QUEUE_DIR / f"{_queue_name(campaign_id)}.xml"


def _generate_queue_xml(campaign_id: UUID | str) -> str:
    """Generate a mod_callcenter queue XML definition for a campaign.
    
    Uses the same proven settings as internal_sales_queue but with a
    campaign-specific name. The queue is loaded into FS via
    callcenter_config queue load.
    """
    name = _queue_name(campaign_id)
    return f"""<include>
  <queue name="{name}">
    <param name="strategy" value="longest-idle-agent"/>
    <param name="moh-sound" value="${{hold_music}}"/>
    <param name="time-base-score" value="system"/>
    <param name="max-wait-time" value="120"/>
    <param name="max-wait-time-with-no-agent" value="30"/>
    <param name="max-wait-time-with-no-agent-time-reached" value="5"/>
    <param name="tier-rules-apply" value="false"/>
    <param name="tier-rule-wait-second" value="300"/>
    <param name="tier-rule-wait-multiply-level" value="true"/>
    <param name="tier-rule-no-agent-no-wait" value="false"/>
    <param name="discard-abandoned-after" value="60"/>
    <param name="abandoned-resume-allowed" value="false"/>
  </queue>
</include>
"""


async def create_campaign_queue(campaign_id: UUID | str, agent_extensions: List[str]) -> bool:
    """Create a mod_callcenter queue for a campaign and add agent tiers.
    
    Called when a campaign starts. The queue is created by:
    1. Writing a queue XML file to disk
    2. Reloading XML so FS sees the new file
    3. Loading the queue into mod_callcenter's memory
    4. Adding each assigned agent as a tier
    
    Args:
        campaign_id: Campaign UUID
        agent_extensions: List of SIP extensions (e.g. ["3001", "3002"])
    
    Returns:
        True if queue was created successfully
    """
    queue_name = _queue_name(campaign_id)
    
    try:
        # 1. Write queue XML
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        xml_path = _queue_xml_path(campaign_id)
        xml_content = _generate_queue_xml(campaign_id)
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        logger.info(f"Wrote queue XML: {xml_path}")
        
        # 2. Reload XML so FS picks up the new file
        await esl_manager.api("reloadxml")
        
        # 3. Load the queue into mod_callcenter's memory
        result = await esl_manager.api(f"callcenter_config queue load {queue_name}")
        logger.info(f"Queue load result: {result}")
        
        # 4. Add agent tiers — only for agents whose softphone is registered
        added = 0
        for i, ext in enumerate(agent_extensions):
            try:
                # Verify agent is registered before adding to tier
                reg_check = await esl_manager.api(f"sofia_contact user/{ext}")
                is_registered = reg_check and "error" not in str(reg_check).lower()
                
                await esl_manager.bgapi(
                    f"callcenter_config tier add {queue_name} {ext} 1 {i + 1}"
                )
                
                # Set agent status based on registration
                if is_registered:
                    await esl_manager.bgapi(
                        f"callcenter_config agent set status {ext} Available"
                    )
                    added += 1
                    logger.info(f"Tier added: {ext} → {queue_name} (registered)")
                else:
                    await esl_manager.bgapi(
                        f"callcenter_config agent set status {ext} 'Logged Out'"
                    )
                    logger.info(f"Tier added: {ext} → {queue_name} (offline)")
            except Exception as e:
                logger.error(f"Failed to add tier {ext} → {queue_name}: {e}")
        
        logger.info(
            f"Campaign queue '{queue_name}' created with "
            f"{added}/{len(agent_extensions)} registered agents"
        )
        return True
        
    except Exception as e:
        logger.error(f"Failed to create campaign queue {queue_name}: {e}")
        return False


async def destroy_campaign_queue(campaign_id: UUID | str) -> bool:
    """Destroy a campaign's mod_callcenter queue.
    
    Called when a campaign stops/aborts/completes. Removes all tiers,
    unloads the queue from memory, and deletes the XML file.
    """
    queue_name = _queue_name(campaign_id)
    
    try:
        # 1. List and remove all tiers for this queue
        tier_result = await esl_manager.api("callcenter_config tier list")
        if tier_result:
            for line in str(tier_result).strip().split("\n"):
                if queue_name in line:
                    parts = line.split("|")
                    if len(parts) >= 2:
                        agent_name = parts[1]
                        await esl_manager.bgapi(
                            f"callcenter_config tier del {queue_name} {agent_name}"
                        )
        
        # 2. Unload the queue from mod_callcenter memory
        await esl_manager.bgapi(f"callcenter_config queue unload {queue_name}")
        
        # 3. Delete the XML file
        xml_path = _queue_xml_path(campaign_id)
        if xml_path.exists():
            xml_path.unlink()
        
        logger.info(f"Campaign queue '{queue_name}' destroyed")
        return True
        
    except Exception as e:
        logger.error(f"Failed to destroy campaign queue {queue_name}: {e}")
        return False


async def add_agent_to_campaign(campaign_id: UUID | str, extension: str) -> bool:
    """Add an agent to a running campaign's queue (mid-campaign join).
    
    Called when an admin adds a new agent to an active campaign via the UI.
    """
    queue_name = _queue_name(campaign_id)
    try:
        # Get current tier count for position
        tier_result = await esl_manager.api("callcenter_config tier list")
        position = 1
        if tier_result:
            for line in str(tier_result).strip().split("\n"):
                if queue_name in line:
                    position += 1
        
        await esl_manager.bgapi(
            f"callcenter_config tier add {queue_name} {extension} 1 {position}"
        )
        
        # Check registration and set status
        reg_check = await esl_manager.api(f"sofia_contact user/{extension}")
        is_registered = reg_check and "error" not in str(reg_check).lower()
        if is_registered:
            await esl_manager.bgapi(
                f"callcenter_config agent set status {extension} Available"
            )
        
        logger.info(f"Agent {extension} added to campaign queue {queue_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to add agent {extension} to {queue_name}: {e}")
        return False


async def remove_agent_from_campaign(campaign_id: UUID | str, extension: str) -> bool:
    """Remove an agent from a running campaign's queue."""
    queue_name = _queue_name(campaign_id)
    try:
        await esl_manager.bgapi(
            f"callcenter_config tier del {queue_name} {extension}"
        )
        logger.info(f"Agent {extension} removed from campaign queue {queue_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to remove agent {extension} from {queue_name}: {e}")
        return False


def get_queue_name_for_campaign(campaign_id: UUID | str | None) -> str:
    """Get the queue name to transfer a call to.
    
    If campaign_id is provided, returns the campaign-specific queue.
    Otherwise falls back to the global internal_sales_queue.
    """
    if campaign_id:
        return _queue_name(campaign_id)
    return "internal_sales_queue"
