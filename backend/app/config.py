from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    llm_api_base: str = "https://api.openai.com/v1"
    llm_model_name: str = "gpt-4o"
    llm_api_key: str = ""
    llm_timeout: int = 300
    llm_max_retries: int = 2
    # Set to false for models that reject the temperature parameter (e.g. gpt-5, o1, o3)
    llm_temperature_supported: bool = True

    # Jira
    jira_base_url: str = ""
    jira_user: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""
    jira_timeout: int = 30

    # Paths
    prompts_dir: Path = Path("prompts")
    config_dir: Path = Path("config")
    local_data_dir: Path = Path("local_data")
    templates_dir: Path = Path("frontend/templates")
    static_dir: Path = Path("frontend/static")

    def __repr__(self) -> str:
        return (
            f"Settings(llm_api_base={self.llm_api_base!r}, "
            f"llm_model_name={self.llm_model_name!r}, "
            f"jira_base_url={self.jira_base_url!r}, "
            f"jira_user={self.jira_user!r})"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
