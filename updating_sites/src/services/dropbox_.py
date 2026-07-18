import base64
import os
from functools import lru_cache
from http import HTTPStatus
from typing import Any

import dropbox  # type: ignore[import-not-found]
import requests
from dropbox import DropboxOAuth2FlowNoRedirect
from fastapi import Depends

from services.storage import get_storage, State
from services.token_cipher import TokenCipher, get_token_cipher
from core.settings import settings


class DropboxService:
    def __init__(self, state: State, token_cipher: TokenCipher) -> None:
        self.state = state
        self.token_cipher = token_cipher

    def authorize(self) -> None:
        auth_flow = DropboxOAuth2FlowNoRedirect(
            settings.dropbox_app_key,
            settings.dropbox_app_secret,
            token_access_type="offline",
        )

        authorize_url = auth_flow.start()
        print("1. Go to: " + authorize_url)
        print('2. Click "Allow" (you might have to log in first).')
        print("3. Copy the authorization code.")
        auth_code = input("Enter the authorization code here: ").strip()

        try:
            oauth_result = auth_flow.finish(auth_code)
        except Exception as e:
            print("Error: %s" % (e,))
            exit(1)

        self._set_token("access_token", oauth_result.access_token)
        self._set_token("refresh_token", oauth_result.refresh_token)

    def check_auth_token(self) -> bool:
        access_token = self._get_token("access_token")
        if not access_token:
            return False
        with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
            try:
                dbx.users_get_current_account()
                return True
            except Exception:
                return False

    def get_auth_token_by_refresh(self) -> int:
        refresh_token = self._get_token("refresh_token")
        if not refresh_token:
            return HTTPStatus.BAD_REQUEST
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.dropbox_app_key,
            "client_secret": settings.dropbox_app_secret,
        }
        try:
            response = requests.post(settings.dropbox_token_url, data=data)
        except Exception:
            return HTTPStatus.BAD_REQUEST
        status_code = response.status_code
        if status_code == HTTPStatus.OK:
            token_data = response.json()
            self._set_token("access_token", token_data["access_token"])
        #  else:
        #    print("Ошибка:", response.status_code, response.text)
        return status_code

    def put_file(self, local_file_path: str, dropbox_file_path: str) -> bool:
        access_token = self._get_token("access_token")
        if not access_token:
            return False
        with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
            try:
                with open(local_file_path, "rb") as f:
                    dbx.files_upload(
                        f.read(),
                        dropbox_file_path,
                        mode=dropbox.files.WriteMode.overwrite,
                    )
                    print(
                        f"Файл {local_file_path} успешно загружен в Dropbox "
                        f"по пути {dropbox_file_path}"
                    )
            except dropbox.exceptions.ApiError as e:
                print(f"Ошибка при загрузке файла: {e}")
                return False
            except FileNotFoundError:
                print(f"Файл {local_file_path} не найден.")
                return False
            except PermissionError:
                print(f"Нет прав на чтение файла {local_file_path}.")
                return False
            except Exception as e:
                print(f"Произошла ошибка: {e}")
                return False
        return True

    def del_file(self, dropbox_file_path: str) -> bool:
        access_token = self._get_token("access_token")
        if not access_token:
            return False
        with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
            try:
                dbx.files_delete_v2(dropbox_file_path)
            except dropbox.exceptions.ApiError as e:
                print(f"Ошибка при удалении файла: {e}")
                return False
            except Exception as e:
                print(f"Произошла ошибка: {e}")
                return False
        return True

    def upd_portal_dropbox(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not self.check_auth_token():
            self.get_auth_token_by_refresh()
        if not self.check_auth_token():
            return result
        access_token = self._get_token("access_token")
        with dropbox.Dropbox(oauth2_access_token=access_token) as dbx:
            for portal, dropbox_path in settings.portals_dropbox:
                for ind in range(1, 4):
                    file_info: dict[str, Any] = {}
                    local_file_path = self.state.get_state(f"{portal}_fa{ind}_active")
                    if not local_file_path:
                        continue
                    local_file = local_file_path.rsplit("/")[-1]
                    file_info["filename"] = local_file
                    dropbox_file_path = f"{dropbox_path}{local_file}"
                    try:
                        with open(local_file_path, "rb") as f:
                            metadata = dbx.files_upload(
                                f.read(),
                                dropbox_file_path,
                                mode=dropbox.files.WriteMode.overwrite,
                            )
                            if metadata.name == os.path.basename(local_file_path):
                                # Можно дополнительно сравнить размер
                                local_size = os.path.getsize(local_file_path)
                                if metadata.size == local_size:
                                    print(
                                        "Upload verified: file exists and size matches"
                                    )
                                else:
                                    print("Warning: size mismatch")
                            else:
                                print("Upload verification failed: name mismatch")
                        file_info["load"] = True
                        dropbox_file_path_old = self.state.get_state(
                            f"{portal}_fa{ind}_dropbox"
                        )
                        if not dropbox_file_path_old:
                            self.state.set_state(
                                f"{portal}_fa{ind}_dropbox", dropbox_file_path
                            )
                            continue
                        file_old = dropbox_file_path_old.rsplit("/")[-1]
                        file_info_old: dict[str, Any] = {}
                        file_info_old["filename"] = file_old
                        try:
                            # dbx.files_delete_v2(dropbox_file_path_old)
                            file_info_old["del_dropbox"] = True
                        except dropbox.exceptions.ApiError as e:
                            file_info_old["del_dropbox"] = False
                            file_info_old["error"] = f"Ошибка при удалении файла: {e}"
                        if file_info_old["del_dropbox"]:
                            try:
                                # os.remove(f"data/prices/{file_old}")
                                file_info_old["del_lockal"] = True
                            except FileNotFoundError:
                                file_info_old["del_lockal"] = False
                                file_info_old["error"] = f"Файл {file_old} не найден."
                            except PermissionError:
                                file_info_old["del_lockal"] = False
                                file_info_old["error"] = (
                                    f"Нет прав на удаление файла {file_old}."
                                )
                            except Exception as e:
                                file_info_old["del_lockal"] = False
                                file_info_old["error"] = f"Произошла ошибка: {e}"
                            result.append(file_info_old)
                            if file_info_old["del_lockal"]:
                                self.state.set_state(
                                    f"{portal}_fa{ind}_dropbox",
                                    dropbox_file_path,
                                )
                    except dropbox.exceptions.ApiError as e:
                        file_info["load"] = False
                        file_info["error"] = f"Ошибка при загрузке файла: {e}"
                    finally:
                        result.append(file_info)
        return result

    def _get_token(self, token_name: str) -> str | None:
        token_cipher = self.state.get_state(token_name)
        if not token_cipher:
            return None
        decoded_data = base64.b64decode(token_cipher)
        return self.token_cipher.decrypt_sync(decoded_data)

    def _set_token(self, token_name: str, value: str) -> bool:
        binary_data = self.token_cipher.encrypt_sync(value)
        encoded_data = base64.b64encode(binary_data).decode("utf-8")
        return self.state.set_state(token_name, encoded_data)


@lru_cache()
def get_dropbox(
    state: State = Depends(get_storage),
    token_cipher: TokenCipher = Depends(get_token_cipher),
) -> DropboxService:
    return DropboxService(state, token_cipher)
