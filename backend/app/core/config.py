import os
from pydantic_settings import BaseSettings, SettingsConfigDict

_core_dir = os.path.dirname(os.path.abspath(__file__))
_app_dir = os.path.dirname(_core_dir)
_backend_dir = os.path.dirname(_app_dir)
_workspace_dir = os.path.dirname(_backend_dir)

class Settings(BaseSettings):
    PROJECT_NAME: str = "Broadcaster"
    DATABASE_URL: str
    REDIS_URL: str
    
    # FreeSWITCH ESL (backend → FS management connection)
    FS_ESL_HOST: str = "127.0.0.1"
    FS_ESL_PORT: int = 8021
    FS_ESL_PASSWORD: str = "ClueCon"
    FS_ESL_POOL_SIZE: int = 3
    
    # FreeSWITCH SIP (agent softphones → FS registration)
    # In dev: same as ESL host (127.0.0.1)
    # In prod: public IP or domain the agent's softphone can reach
    FS_SIP_DOMAIN: str = "127.0.0.1"
    FS_SIP_PORT: int = 5060
    
    # Whisper AMD sidecar (Layer 2 — AI-based answering machine detection)
    # Local dev: whisper-amd container exposes port 8080 on localhost
    # Docker prod: compose DNS resolves 'whisper-amd' service name
    WHISPER_AMD_HOST: str = "localhost"
    WHISPER_AMD_PORT: int = 8080
    WHISPER_AMD_WS_URL: str = "ws://localhost:8080/ws/amd"
    
    # Shared audio directory — where FS recordings and TTS files live
    # Local dev: relative path to the bind-mounted data/audio directory
    # Docker prod: /audio (absolute path inside the container)
    AUDIO_DIR: str = "./data/audio"
    
    # FreeSWITCH conf directory (where sip profiles are written)
    FS_CONF_DIR: str = os.path.join(_workspace_dir, "freeswitch", "conf")
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra="ignore")

settings = Settings()
