from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

COMMON_CONFIG: dict = dict(
    env_file=".env.example",
    env_file_encoding="utf-8",
    extra="ignore",
)


class LoggingSettings(BaseSettings):
    # logging settings
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        **COMMON_CONFIG, env_prefix="LOG_"
    )

    level: str = "INFO"
    use_colors: bool = True


class MinioSettings(BaseSettings):
    # minio settings
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        **COMMON_CONFIG, env_prefix="MINIO_"
    )

    root_user: str
    root_password: str
    endpoint: str

    bucket_bronze: str = "bronze"
    bucket_silver: str = "silver"
    bucket_gold: str = "gold"


class PrefectSettings(BaseSettings):
    # prefect settings
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        **COMMON_CONFIG, env_prefix="PREFECT_"
    )

    server_ui_api_url: str


class DashboardSettings(BaseSettings):
    # dashboard settings
    # NOTE: reads ONLY from .env (not .env.example) so that on Streamlit
    # Community Cloud the default data_source="static" is used.
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="DASHBOARD_",
    )

    data_source: str = "static"  # default to public dashboard
    title: str = "GitPulse Analytics"
    cache_ttl: int = 3600
    static_data_path: str = "dashboard/data"


class Settings(BaseSettings):
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    minio: MinioSettings = Field(default_factory=MinioSettings)
    prefect: PrefectSettings = Field(default_factory=PrefectSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)


settings = Settings()
