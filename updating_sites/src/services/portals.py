import subprocess
import zipfile
from collections.abc import Iterator, Sequence
from typing import Any

import pandas as pd
from sqlalchemy import MetaData, Row, Table, create_engine, text
from sqlalchemy.engine.base import Engine
from sshtunnel import SSHTunnelForwarder

from common.log_context import bind_class, log_run
from core.logger import get_logger
from core.settings import settings
from services.helper import (
    get_files_tables,
    get_request_for_upd,
    get_tables_for_export,
    get_tables_for_overload,
)


logger = get_logger(__name__)


class PortalServices:
    def __init__(self, server: SSHTunnelForwarder, portal: str) -> None:
        self.portal = portal
        self.engine = create_engine(
            settings.portals_settings[portal].mysql_db
            % (server.local_bind_port)
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
        except Exception as error:
            logger.error(
                "CSV import to table failed",
                extra={
                    "portal": self.portal,
                    "table": table,
                    "file": file,
                    "error": str(error),
                },
                exc_info=True,
            )
            return 0, str(error)
        logger.info(
            "CSV import to table completed",
            extra={
                "portal": self.portal,
                "table": table,
                "file": file,
                "rows": result,
            },
        )
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
        else:
            logger.warning(
                "No file-table mapping found",
                extra={"portal": self.portal},
            )
        return result, success

    def update_portal(self) -> bool:
        logger.info(
            "Portal SQL update started",
            extra={"portal": self.portal},
        )
        try:
            with self.engine.connect() as connection:
                request = get_request_for_upd(self.portal)
                with connection.begin():
                    for query in request.split(";"):
                        if query.strip():
                            connection.execute(text(query))
        except Exception as error:
            logger.error(
                "Portal SQL update failed",
                extra={"portal": self.portal, "error": str(error)},
                exc_info=True,
            )
            raise
        logger.info(
            "Portal SQL update completed",
            extra={"portal": self.portal},
        )
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

    def get_data(
        self, engine: Engine, table: str
    ) -> Iterator[Sequence[Row[Any]]]:
        with engine.connect() as connection:
            source_data = connection.execute(text(f"SELECT * FROM {table};"))  # noqa: S608
            while results := source_data.fetchmany(10000):
                yield results

    def overload_tables(self, page: int | None = None) -> dict[str, Any]:
        metadata = MetaData()
        result: dict[str, Any] = {"tables": [], "page": page, "upd": False}
        logger.info("ETL overload started", extra={"page": page})
        current_table: str | None = None
        try:
            with self.engine_recipient.connect() as connection:
                for table_name in get_tables_for_overload(page):
                    current_table = table_name
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
        except Exception as error:
            result["error"] = str(error)
            logger.error(
                "ETL overload failed",
                extra={
                    "page": page,
                    "table": current_table,
                    "error": str(error),
                },
                exc_info=True,
            )
        else:
            logger.info(
                "ETL overload completed",
                extra={
                    "page": page,
                    "table_count": len(result["tables"]),
                    "updated": result["upd"],
                },
            )
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
        logger.info(
            "Database export started",
            extra={
                "portal": self.portal,
                "part": part,
                "database": database,
            },
        )
        result = subprocess.run(  # noqa: S602
            f"mysqldump -h %s -P %s -u %s -p%s %s {tables} > %s.sql"
            % (host, port, db_user, db_pass, database, file),
            shell=True,
        )
        log_method = logger.info if result.returncode == 0 else logger.error
        log_method(
            "Database export completed",
            extra={
                "portal": self.portal,
                "part": part,
                "database": database,
                "return_code": result.returncode,
            },
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
                logger.info(
                    "Export archive created",
                    extra={
                        "portal": self.portal,
                        "source_file": file,
                        "archive": zip_file_name_path,
                    },
                )
                return zip_file_name_path
        except Exception as error:
            logger.error(
                "Export archive creation failed",
                extra={
                    "portal": self.portal,
                    "source_file": file,
                    "error": str(error),
                },
                exc_info=True,
            )
            raise


class UpdatingPortalServis:
    def update_portal(self, portal: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        with bind_class(self), log_run("portal_update"):
            logger.info("Portal update started", extra={"portal": portal})
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
                    update_tables, result_tables = (
                        portal_services.update_tables()
                    )
                    result["update_tables"] = update_tables
                    result["update_tables_result"] = result_tables
                    if result_tables:
                        try:
                            portal_services.update_portal()
                            result["update_portal"] = "success"
                        except Exception as e:  # noqa: BLE001
                            result["update_portal"] = str(e)
                    else:
                        result["update_portal"] = "not started"
            logger.info(
                "Portal update completed",
                extra={
                    "portal": portal,
                    "tables_updated": result.get(
                        "update_tables_result", False
                    ),
                    "portal_status": result.get("update_portal"),
                },
            )
            return result

    def etl(self, page: int | None) -> dict[str, Any]:  # type: ignore[return]
        with bind_class(self), log_run("portal_etl"):
            logger.info("ETL synchronization started", extra={"page": page})
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
                except Exception:  # noqa: BLE001
                    result["file"] = file
                    logger.warning(
                        "Export archive unavailable; SQL file retained",
                        extra={
                            "portal": export_services.portal,
                            "part": part,
                            "file": file,
                        },
                    )
            else:
                result["error"] = "Error exporting tables"
        except Exception as error:
            result["error"] = str(error)
            logger.error(
                "Export part failed",
                extra={
                    "portal": export_services.portal,
                    "part": part,
                    "error": str(error),
                },
                exc_info=True,
            )
        return result

    def export_table(self, portal: str) -> list[Any]:
        result: list[Any] = []
        with bind_class(self), log_run("portal_export"):
            logger.info("Portal export started", extra={"portal": portal})
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
            logger.info(
                "Portal export completed",
                extra={
                    "portal": portal,
                    "part_count": len(result),
                    "error_count": sum(
                        1 for item in result if item.get("error")
                    ),
                },
            )
            return result


def get_portal_service() -> UpdatingPortalServis:
    return UpdatingPortalServis()
