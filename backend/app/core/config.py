from pydantic_settings import BaseSettings, SettingsConfigDict

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
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra="ignore")

settings = Settings()
