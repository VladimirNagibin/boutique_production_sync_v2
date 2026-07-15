import os
from logging import config as logging_config

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.logger import LOGGING


load_dotenv()
logging_config.dictConfig(LOGGING)


class SettingsPortal(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.upd_sites", env_prefix="portal_", env_file_encoding="utf-8"
    )
    user_db: str = "user_db"
    password_db: str = "password_db"
    name_db: str = "name_db"

    @property
    def mysql_db(self) -> str:
        return (
            f"mysql+pymysql://{self.user_db}:{self.password_db}@"
            f"{settings.ssh_tunnel_local_host}:%d/{self.name_db}"
        )


class SettingsOrnam(SettingsPortal):
    model_config = SettingsConfigDict(
        env_file=".env.upd_sites", env_prefix="ornam_", env_file_encoding="utf-8"
    )


class SettingsButic(SettingsPortal):
    model_config = SettingsConfigDict(
        env_file=".env.upd_sites", env_prefix="butic_", env_file_encoding="utf-8"
    )


class SettingsIsmy(SettingsPortal):
    model_config = SettingsConfigDict(
        env_file=".env.upd_sites", env_prefix="ismy_", env_file_encoding="utf-8"
    )


class SettingsRecipient(SettingsPortal):
    model_config = SettingsConfigDict(
        env_file=".env.upd_sites", env_prefix="recipient_", env_file_encoding="utf-8"
    )
    host: str = "host"
    login: str = "login"
    password: str = "password"


class SettingsSender(SettingsPortal):
    model_config = SettingsConfigDict(
        env_file=".env.upd_sites", env_prefix="sender_", env_file_encoding="utf-8"
    )
    host: str = "host"
    login: str = "login"
    password: str = "password"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.upd_sites", env_file_encoding="utf-8"
    )

    PROJECT_NAME: str = "project"
    APP_RELOAD: bool = False

    host: str = "host"
    login: str = "login"
    password: str = "password"

    ssh_tunnel_local_host: str = "127.0.0.1"
    ssh_tunnel_local_port: int = 3306
    portals_settings: dict[str, SettingsPortal] = {
        "ornam": SettingsOrnam(),
        "butic": SettingsButic(),
        "ismy": SettingsIsmy(),
    }

    sender: SettingsSender = SettingsSender()
    recipient: SettingsRecipient = SettingsRecipient()

    base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    dropbox_app_key: str = "dropbox_app_key"
    dropbox_app_secret: str = "dropbox_app_secret"
    dropbox_token_url: str = "dropbox_token_url"

    portals_dropbox: list[tuple[str, str]] = [
        ("sm", "/! СМ !/Прайсы нужно скачать!!!/"),
        ("inet", "/! ИНЕТ !/Прайсы нужно скачать!!!/"),
        (
            "ismy",
            "/!!! Для скачивания всей папки в архив нажмите Download !!!/",
        ),
    ]


settings = Settings()
