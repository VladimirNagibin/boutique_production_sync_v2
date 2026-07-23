import base64
import os
from functools import lru_cache
from http import HTTPStatus
from typing import Any

import dropbox  # type: ignore[import-not-found]
import requests
from dropbox import DropboxOAuth2FlowNoRedirect
from fastapi import Depends

from common.logger import logger
from core.settings import settings
from services.storage import State, get_storage
from services.token_cipher import TokenCipher, get_token_cipher


class DropboxService:
    """Сервис для работы с Dropbox: авторизация, загрузка, удаление файлов."""

    def __init__(self, state: State, token_cipher: TokenCipher) -> None:
        self.state = state
        self.token_cipher = token_cipher

    # ----- Публичные методы -----

    def authorize(self) -> None:
        """
        Авторизация в Dropbox через OAuth2 (получение access/refresh токенов).
        Требует ручного ввода кода подтверждения.
        """
        auth_flow = DropboxOAuth2FlowNoRedirect(
            settings.dropbox_app_key,
            settings.dropbox_app_secret,
            token_access_type="offline",
        )

        authorize_url = auth_flow.start()
        logger.info(
            "Dropbox authorization URL",
            extra={"url": authorize_url},
        )
        logger.info("Click 'Allow', then copy the authorization code.")
        auth_code = input("Enter the authorization code here: ").strip()

        try:
            oauth_result = auth_flow.finish(auth_code)
        except Exception as e:
            logger.error("Dropbox authorization failed", extra={"error": str(e)})
            raise
            # exit(1)

        self._set_token("access_token", oauth_result.access_token)
        self._set_token("refresh_token", oauth_result.refresh_token)
        logger.info("Dropbox tokens saved successfully")

    def check_auth_token(self) -> bool:
        """Проверяет валидность текущего access_token."""
        access_token = self._get_token("access_token")
        if not access_token:
            return False

        try:
            with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
                dbx.users_get_current_account()
                return True
        except dropbox.exceptions.AuthError as e:
            logger.warning(
                "Access token invalid",
                extra={"error": str(e)},
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error during token check",
                extra={"error": str(e)},
            )
            return False

    def get_auth_token_by_refresh(self) -> int:
        """
        Обновляет access_token с помощью refresh_token.

        Returns:
            HTTP статус: 200 OK, иначе ошибка.
        """
        refresh_token = self._get_token("refresh_token")
        if not refresh_token:
            logger.error("Refresh token is missing")
            return HTTPStatus.BAD_REQUEST

        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.dropbox_app_key,
            "client_secret": settings.dropbox_app_secret,
        }
        try:
            response = requests.post(settings.dropbox_token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
            self._set_token("access_token", token_data["access_token"])
            logger.info("Access token refreshed successfully")
            return HTTPStatus.OK
        except requests.RequestException as e:
            logger.error(
                "Failed to refresh token",
                extra={"error": str(e)},
                exc_info=True,
            )
            return HTTPStatus.BAD_REQUEST
        except Exception as e:
            logger.error(
                "Unexpected error during token refresh",
                extra={"error": str(e)},
                exc_info=True,
            )
            return HTTPStatus.INTERNAL_SERVER_ERROR

    def put_file(self, local_file_path: str, dropbox_file_path: str) -> bool:
        """
        Загружает файл в Dropbox.

        Args:
            local_file_path: Локальный путь к файлу.
            dropbox_file_path: Путь в Dropbox (включая имя файла).

        Returns:
            True, если загрузка успешна, иначе False.
        """
        access_token = self._get_token("access_token")
        if not access_token:
            logger.error("Access token missing, cannot upload")
            return False

        try:
            with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
                return self._upload_file(dbx, local_file_path, dropbox_file_path)
        except Exception as e:
            logger.error(
                "Unexpected error during upload",
                extra={"local_path": local_file_path, "error": str(e)},
                exc_info=True,
            )
            return False

    def del_file(self, dropbox_file_path: str) -> bool:
        """
        Удаляет файл в Dropbox.

        Args:
            dropbox_file_path: Путь к файлу в Dropbox.

        Returns:
            True, если удаление успешно, иначе False.
        """
        access_token = self._get_token("access_token")
        if not access_token:
            logger.error("Access token missing, cannot delete")
            return False

        try:
            with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
                return self._delete_dropbox_file(dbx, dropbox_file_path)
        except Exception as e:
            logger.error(
                "Unexpected error during delete",
                extra={"dropbox_path": dropbox_file_path, "error": str(e)},
                exc_info=True,
            )
            return False

    def upd_portal_dropbox(self) -> list[dict[str, Any]]:
        """
        Основной метод: загружает активные файлы для каждого портала в Dropbox,
        удаляет старые версии и обновляет состояние.

        Returns:
            Список словарей с информацией о каждой операции (успех/ошибка).
        """
        result: list[dict[str, Any]] = []

        # 1. Проверяем/обновляем токен
        if not self.check_auth_token():
            status = self.get_auth_token_by_refresh()
            if status != HTTPStatus.OK:
                logger.error("Cannot refresh token, aborting upload")
                return result

            if not self.check_auth_token():
                logger.error("Token still invalid after refresh")
                return result

        access_token = self._get_token("access_token")
        if not access_token:
            logger.error("Access token is missing")
            return result

        # 2. Основной цикл по порталам
        with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
            for portal, dropbox_base_path in settings.portals_dropbox:
                for ind in range(1, 4):
                    entry = self._process_portal_file(
                        dbx, portal, ind, dropbox_base_path
                    )
                    if entry:
                        result.append(entry)

        logger.info(
            "Dropbox update completed",
            extra={"processed": len(result)},
        )
        return result

    # ----- Приватные методы -----

    def _get_token(self, token_name: str) -> str | None:
        """Извлекает и расшифровывает токен из хранилища."""
        encrypted = self.state.get_state(token_name)
        if not encrypted:
            return None
        try:
            decoded = base64.b64decode(encrypted)
            return self.token_cipher.decrypt_sync(decoded)
        except Exception as e:
            logger.error(
                "Failed to decrypt token",
                extra={"token_name": token_name, "error": str(e)},
            )
            return None

    def _set_token(self, token_name: str, value: str) -> bool:
        """Шифрует и сохраняет токен в хранилище."""
        try:
            encrypted = self.token_cipher.encrypt_sync(value)
            encoded = base64.b64encode(encrypted).decode("utf-8")
            return self.state.set_state(token_name, encoded)
        except Exception as e:
            logger.error(
                "Failed to encrypt/save token",
                extra={"token_name": token_name, "error": str(e)},
            )
            return False

    def _upload_file(
        self,
        dbx: dropbox.Dropbox,
        local_path: str,
        dropbox_path: str,
    ) -> bool:
        """Загружает файл и проверяет успешность."""
        try:
            with open(local_path, "rb") as f:
                metadata = dbx.files_upload(
                    f.read(),
                    dropbox_path,
                    mode=dropbox.files.WriteMode.overwrite,
                )
            # Проверяем, что загрузился корректно
            local_size = os.path.getsize(local_path)
            if metadata.size == local_size:
                logger.info(
                    "File uploaded successfully",
                    extra={
                        "local_path": local_path,
                        "dropbox_path": dropbox_path,
                        "size": metadata.size,
                    },
                )
                return True
            else:
                logger.warning(
                    "File size mismatch after upload",
                    extra={
                        "local_size": local_size,
                        "remote_size": metadata.size,
                    },
                )
                return False
        except FileNotFoundError:
            logger.error("Local file not found", extra={"path": local_path})
            return False
        except PermissionError:
            logger.error("Permission denied reading file", extra={"path": local_path})
            return False
        except dropbox.exceptions.ApiError as e:
            logger.error(
                "Dropbox API error during upload",
                extra={"path": dropbox_path, "error": str(e)},
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected upload error",
                extra={"path": local_path, "error": str(e)},
                exc_info=True,
            )
            return False

    def _delete_dropbox_file(self, dbx: dropbox.Dropbox, dropbox_path: str) -> bool:
        """Удаляет файл в Dropbox."""
        try:
            dbx.files_delete_v2(dropbox_path)
            logger.info(
                "File deleted from Dropbox",
                extra={"path": dropbox_path},
            )
            return True
        except dropbox.exceptions.ApiError as e:
            if e.error.is_path_lookup_error():
                logger.warning(
                    "File already deleted or not found",
                    extra={"path": dropbox_path},
                )
                return True  # Считаем успехом, если файла нет
            logger.error(
                "Dropbox API error during delete",
                extra={"path": dropbox_path, "error": str(e)},
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error during delete",
                extra={"path": dropbox_path, "error": str(e)},
                exc_info=True,
            )
            return False

    def _delete_local_file(self, local_path: str) -> bool:
        """Удаляет локальный файл."""
        try:
            os.remove(local_path)
            logger.info(
                "Local file deleted",
                extra={"path": local_path},
            )
            return True
        except FileNotFoundError:
            logger.warning(
                "Local file already deleted",
                extra={"path": local_path},
            )
            return True
        except PermissionError:
            logger.error(
                "Permission denied deleting local file",
                extra={"path": local_path},
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error deleting local file",
                extra={"path": local_path, "error": str(e)},
                exc_info=True,
            )
            return False

    def _process_portal_file(
        self,
        dbx: dropbox.Dropbox,
        portal: str,
        ind: int,
        dropbox_base_path: str,
    ) -> dict[str, Any] | None:
        """
        Обрабатывает один файл для заданного портала и индекса.

        Returns:
            Словарь с результатом операции, либо None, если файл не активен.
        """
        local_file_path = self.state.get_state(f"{portal}_fa{ind}_active")
        if not local_file_path:
            return None

        local_filename = os.path.basename(local_file_path)
        dropbox_dir = dropbox_base_path.rstrip("/") + "/"
        dropbox_file_path = f"{dropbox_dir}{local_filename}"

        entry: dict[str, Any] = {
            "portal": portal,
            "index": ind,
            "filename": local_filename,
            "dropbox_path": dropbox_file_path,
        }

        # 1. Загружаем новый файл
        upload_ok = self._upload_file(dbx, local_file_path, dropbox_file_path)
        entry["uploaded"] = upload_ok

        if not upload_ok:
            entry["error"] = "Upload failed"
            return entry

        # 2. Удаляем старый файл, если он был сохранён
        old_dropbox_path = self.state.get_state(f"{portal}_fa{ind}_dropbox")
        if old_dropbox_path:
            old_filename = os.path.basename(old_dropbox_path)
            old_entry = {
                "old_filename": old_filename,
                "old_dropbox_path": old_dropbox_path,
            }

            # Удаляем из Dropbox
            if self._delete_dropbox_file(dbx, old_dropbox_path):
                old_entry["del_dropbox"] = True
                # Удаляем локальную копию старого файла
                old_local_path = os.path.join("data/prices", old_filename)
                if self._delete_local_file(old_local_path):
                    old_entry["del_local"] = True
                else:
                    old_entry["del_local"] = False
                    old_entry["error"] = "Failed to delete local old file"
            else:
                old_entry["del_dropbox"] = False
                old_entry["error"] = "Failed to delete old file from Dropbox"

            entry["old_file"] = old_entry

        # 3. Сохраняем новый путь в состояние
        self.state.set_state(f"{portal}_fa{ind}_dropbox", dropbox_file_path)

        return entry


# ----- Dependency Injection -----
@lru_cache()
def get_dropbox(
    state: State = Depends(get_storage),
    token_cipher: TokenCipher = Depends(get_token_cipher),
) -> DropboxService:
    """Фабрика для создания экземпляра DropboxService."""
    return DropboxService(state, token_cipher)
