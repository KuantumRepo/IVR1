from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Broadcaster"
    DATABASE_URL: str
    REDIS_URL: str
    
    # FreeSWITCH ESL
    FS_ESL_HOST: str = "127.0.0.1"
    FS_ESL_PORT: int = 8021
    FS_ESL_PASSWORD: str = "ClueCon"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8', extra="ignore")

settings = Settings()
