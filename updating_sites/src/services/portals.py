import subprocess
import zipfile
from collections.abc import Iterator, Sequence
from typing import Any

import pandas as pd
from sshtunnel import SSHTunnelForwarder  # type: ignore[import-not-found]
from sqlalchemy import Row, create_engine, text, Table, MetaData
from sqlalchemy.engine.base import Engine

from core.settings import settings
from services.helper import (
    get_request_for_upd,
    get_files_tables,
    get_tables_for_export,
    get_tables_for_overload,
)


class PortalServices:
    def __init__(self, server: SSHTunnelForwarder, portal: str) -> None:
        self.portal = portal
        self.engine = create_engine(
            settings.portals_settings[portal].mysql_db % (server.local_bind_port)
        )

    def update_table(self, file: str, table: str) -> tuple[Any, str]:
        try:
            df = pd.read_csv(file, sep=";")
            result = df.to_sql(
                table,
                con=self.engine,
                if_exists="replace",
                index=False,
                chunksize=10000,
            )
        except Exception as e:
            return 0, str(e)
        return result, ""

    def update_tables(self) -> tuple[list[Any], bool]:
        result: list[Any] = []
        success = True
        file_table = get_files_tables(self.portal)
        if file_table:
            for file, table in file_table:
                rows, err = self.update_table(file, table)
                res: dict[str, str] = {"table": table, "rows": rows}
                if err:
                    res["error"] = err
                    success = False
                result.append(res)
        return result, success

    def update_portal(self) -> bool:
        try:
            with self.engine.connect() as connection:
                request = get_request_for_upd(self.portal)
                with connection.begin():
                    for query in request.split(";"):
                        if query.strip():
                            connection.execute(text(query))
        except Exception as e:
            raise e
        return True


class EtlServices:
    def __init__(
        self,
        server_sender: SSHTunnelForwarder,
        server_recipient: SSHTunnelForwarder,
    ) -> None:
        self.engine_recipient = create_engine(
            settings.recipient.mysql_db % (server_recipient.local_bind_port)
        )
        self.engine_sender = create_engine(
            settings.sender.mysql_db % (server_sender.local_bind_port)
        )

    def get_data(self, engine: Engine, table: str) -> Iterator[Sequence[Row[Any]]]:
        with engine.connect() as connection:
            source_data = connection.execute(text(f"SELECT * FROM {table};"))
            while results := source_data.fetchmany(10000):
                yield results

    def overload_tables(self, page: int | None = None) -> dict[str, Any]:
        metadata = MetaData()
        result: dict[str, Any] = {"tables": [], "page": page, "upd": False}
        try:
            with self.engine_recipient.connect() as connection:
                for table_name in get_tables_for_overload(page):
                    result["tables"].append(table_name)
                    table_recipient = Table(
                        table_name,
                        metadata,
                        autoload_with=self.engine_recipient,
                    )
                    if page == 0 or page is None:
                        connection.execute(text(f"TRUNCATE {table_name};"))
                    number_page = 0
                    for batch in self.get_data(self.engine_sender, table_name):
                        if page is None or page == number_page:
                            result["upd"] = True
                            val = [record._asdict() for record in batch]
                            insert_stmt = table_recipient.insert().values(val)
                            connection.execute(insert_stmt)
                            connection.commit()
                        number_page += 1
        except Exception as e:
            result["error"] = str(e)
        return result


class ExportService:
    def __init__(self, server: SSHTunnelForwarder, portal: str) -> None:
        self.portal = portal
        self.port: int = server.local_bind_port

    def update_table(self, part: int) -> tuple[int, str]:
        host = settings.ssh_tunnel_local_host
        port = self.port
        db_user = settings.portals_settings[self.portal].user_db
        db_pass = settings.portals_settings[self.portal].password_db
        database = settings.portals_settings[self.portal].name_db
        # filestamp = time.strftime('%Y-%m-%d-%I')
        file = f"data/upload/{database}_{part}"
        tables = " ".join(get_tables_for_export(part))
        result = subprocess.run(
            f"mysqldump -h %s -P %s -u %s -p%s %s {tables} > %s.sql"
            % (host, port, db_user, db_pass, database, file),
            shell=True,
        )
        return result.returncode, file

    def zip_file(self, file: str) -> str:
        zip_file_name_path = f"{file}.zip"
        zip_file_name = file.rsplit("/")[-1]
        try:
            with zipfile.ZipFile(
                zip_file_name_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as zipf:
                zipf.write(file, zip_file_name)
                return zip_file_name_path
        except Exception as e:
            raise e


class UpdatingPortalServis:
    def update_portal(self, portal: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        with SSHTunnelForwarder(
            ssh_address_or_host=settings.host,
            ssh_username=settings.login,
            ssh_password=settings.password,
            remote_bind_address=(
                settings.ssh_tunnel_local_host,
                settings.ssh_tunnel_local_port,
            ),
        ) as server:
            if server:
                server.start()
                portal_services = PortalServices(server, portal)
                update_tables, result_tables = portal_services.update_tables()
                result["update_tables"] = update_tables
                result["update_tables_result"] = result_tables
                if result_tables:
                    try:
                        portal_services.update_portal()
                        result["update_portal"] = "success"
                    except Exception as e:
                        result["update_portal"] = str(e)
                else:
                    result["update_portal"] = "not started"
        return result

    def etl(self, page: int | None) -> dict[str, Any]:  # type: ignore[return]
        with (
            SSHTunnelForwarder(
                ssh_address_or_host=settings.recipient.host,
                ssh_username=settings.recipient.login,
                ssh_password=settings.recipient.password,
                remote_bind_address=(
                    settings.ssh_tunnel_local_host,
                    settings.ssh_tunnel_local_port,
                ),
            ) as server_recipient,
            SSHTunnelForwarder(
                ssh_address_or_host=settings.sender.host,
                ssh_username=settings.sender.login,
                ssh_password=settings.sender.password,
                remote_bind_address=(
                    settings.ssh_tunnel_local_host,
                    settings.ssh_tunnel_local_port,
                ),
            ) as server_sender,
        ):
            if server_recipient and server_sender:
                server_recipient.start()
                server_sender.start()

                etl_services = EtlServices(server_sender, server_recipient)
                return etl_services.overload_tables(page)

    def export_table_part(
        self, export_services: ExportService, part: int
    ) -> dict[str, int | str]:
        result: dict[str, int | str] = {}
        result["part"] = part
        try:
            result["result"], file = export_services.update_table(part)
            file += ".sql"
            if result["result"] == 0:
                try:
                    zip_file = export_services.zip_file(file)
                    result["file"] = zip_file
                except Exception:
                    result["file"] = file
            else:
                result["error"] = "Error exporting tables"
        except Exception as e:
            result["error"] = str(e)
        return result

    def export_table(self, portal: str) -> list[Any]:
        result: list[Any] = []
        with SSHTunnelForwarder(
            ssh_address_or_host=settings.host,
            ssh_username=settings.login,
            ssh_password=settings.password,
            remote_bind_address=(
                settings.ssh_tunnel_local_host,
                settings.ssh_tunnel_local_port,
            ),
        ) as server:
            if server:
                server.start()
                export_services = ExportService(server, portal)
                result.append(self.export_table_part(export_services, 1))
                result.append(self.export_table_part(export_services, 2))
        return result


def get_portal_service() -> UpdatingPortalServis:
    return UpdatingPortalServis()
