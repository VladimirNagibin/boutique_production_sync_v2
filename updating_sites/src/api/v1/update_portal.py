from http import HTTPStatus
from typing import Any

from fastapi import APIRouter, Depends, Response

from services.portals import UpdatingPortalServis, get_portal_service
from schemas.v1.entity import EtlTable, ExportTable, UpdTable, UpdPortal

upd_portal = APIRouter()


@upd_portal.get("/etl", summary="reload portal", description="Reload portals.")
def reload_port(
    response: Response,
    page: int | None = None,
    upd_service: UpdatingPortalServis = Depends(get_portal_service),
) -> EtlTable:
    result: dict[str, Any] = upd_service.etl(page)
    if result.get("error"):
        response.status_code = HTTPStatus.BAD_REQUEST
    return EtlTable(**result)


@upd_portal.get("/export", summary="export tables", description="Export tables.")
def export_port(
    response: Response,
    portal: str = "ismy",
    upd_service: UpdatingPortalServis = Depends(get_portal_service),
) -> list[ExportTable]:
    results: list[dict[str, Any]] = upd_service.export_table(portal)
    err = [result["error"] for result in results if result.get("error")]
    if err:
        response.status_code = HTTPStatus.BAD_REQUEST
    return [ExportTable(**result) for result in results]


@upd_portal.get("/{portal}", summary="updating portal", description="Updating portals.")
def upt_port(
    portal: str,
    response: Response,
    upd_service: UpdatingPortalServis = Depends(get_portal_service),
) -> UpdPortal:
    result: dict[str, Any] = upd_service.update_portal(portal)
    upd_tables = [UpdTable(**res) for res in result["update_tables"]]
    upd_portal = result["update_portal"]
    if (upd_portal != "success") or (not result["update_tables_result"]):
        response.status_code = HTTPStatus.BAD_REQUEST
    return UpdPortal(upd_tables=upd_tables, upd_portal=upd_portal)
