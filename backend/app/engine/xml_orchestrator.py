import os
from pathlib import Path
import logging
from app.models.core import SipGateway, Agent
from app.esl.connection import esl_manager

logger = logging.getLogger(__name__)

# Usually freeswitch/conf is mounted, but if we run locally we need to find it
FS_CONF_DIR = Path("/etc/freeswitch") if os.path.exists("/.dockerenv") else Path("../freeswitch/conf")
PROFILES_DIR = FS_CONF_DIR / "sip_profiles" / "external"
DIRECTORY_DIR = FS_CONF_DIR / "directory" / "default"

def _ensure_dir():
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    DIRECTORY_DIR.mkdir(parents=True, exist_ok=True)

async def generate_gateway_xml(gateway: SipGateway):
    """
    Generates a static XML file for the FreeSWITCH external sip profile
    and reloads the XML so it takes effect immediately.
    """
    try:
        _ensure_dir()
        file_path = PROFILES_DIR / f"{gateway.id}.xml"
        
        # Build XML
        xml_content = f"""<include>
  <gateway name="{gateway.name}">
    <param name="realm" value="{gateway.sip_server}"/>
"""
        if gateway.sip_username:
            xml_content += f'    <param name="username" value="{gateway.sip_username}"/>\n'
        if gateway.sip_password:
            xml_content += f'    <param name="password" value="{gateway.sip_password}"/>\n'
            
        # Optional params
        xml_content += '    <param name="register" value="true"/>\n'
        xml_content += '    <param name="retry-seconds" value="30"/>\n'
        xml_content += '    <param name="ping" value="25"/>\n'
        
        xml_content += """  </gateway>
</include>
"""
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
            
        logger.info(f"Generated SIP Gateway XML: {file_path}")
        
        # Trigger reload in FS
        await esl_manager.api("reloadxml")
        await esl_manager.bgapi("sofia profile external rescan")
        logger.info("Triggered sofia profile external rescan")
            
    except Exception as e:
        logger.error(f"Failed to generate gateway XML: {e}")

async def delete_gateway_xml(gateway_id: str):
    """Deletes the XML and rescans"""
    try:
        file_path = PROFILES_DIR / f"{gateway_id}.xml"
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted SIP Gateway XML: {file_path}")
            await esl_manager.api("reloadxml")
            await esl_manager.bgapi("sofia profile external rescan")
                
    except Exception as e:
        logger.error(f"Failed to delete gateway XML: {e}")

async def generate_agent_xml(agent: Agent):
    """
    Generate a FreeSWITCH directory entry for an agent so their
    SIP softphone can register to our FreeSWITCH instance.
    
    Uses the agent's sip_extension and sip_password from the database.
    """
    try:
        _ensure_dir()
        ext = agent.sip_extension or agent.phone_or_sip
        password = agent.sip_password or "changeme123"
        file_path = DIRECTORY_DIR / f"{ext}.xml"
        
        xml_content = f"""<include>
  <user id="{ext}">
    <params>
      <param name="password" value="{password}"/>
      <param name="vm-password" value="{ext}"/>
    </params>
    <variables>
      <variable name="toll_allow" value="domestic,international,local"/>
      <variable name="accountcode" value="{ext}"/>
      <variable name="user_context" value="default"/>
      <variable name="effective_caller_id_name" value="{agent.name}"/>
      <variable name="effective_caller_id_number" value="{ext}"/>
      <variable name="outbound_caller_id_name" value="$${{outbound_caller_name}}"/>
      <variable name="outbound_caller_id_number" value="$${{outbound_caller_id}}"/>
      <variable name="callgroup" value="agents"/>
      <variable name="agent_id" value="{agent.id}"/>
    </variables>
  </user>
</include>
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
            
        logger.info(f"Generated Agent XML: {file_path}")
        
        # Reload FS config
        await esl_manager.api("reloadxml")
        
        # Provision agent into mod_callcenter
        await esl_manager.bgapi(f"callcenter_config agent add {ext} Callback")
        await esl_manager.bgapi(f"callcenter_config agent set contact {ext} user/{ext}")
        await esl_manager.bgapi(f"callcenter_config agent set status {ext} 'Available'")
        await esl_manager.bgapi(f"callcenter_config agent set state {ext} Waiting")
        await esl_manager.bgapi(f"callcenter_config tier add internal_sales_queue {ext} 1 1")
        logger.info(f"Provisioned Agent {ext} into mod_callcenter")
            
    except Exception as e:
        logger.error(f"Failed to generate agent XML: {e}")

async def delete_agent_xml(agent: Agent):
    try:
        ext = agent.sip_extension or agent.phone_or_sip
        file_path = DIRECTORY_DIR / f"{ext}.xml"
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted Agent XML: {file_path}")
            await esl_manager.api("reloadxml")
            # Remove from callcenter
            await esl_manager.bgapi(f"callcenter_config agent del {ext}")
    except Exception as e:
        logger.error(f"Failed to delete agent XML: {e}")
