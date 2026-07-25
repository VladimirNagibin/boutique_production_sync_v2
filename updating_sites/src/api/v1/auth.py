from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates

from common.logger import logger
from core.settings import settings
from repositories.tinydb_repo import TinyDBRepository, get_tinydb_repo
from schemas.v1.response_schemas import TokenResponse
from services.auth import UserAuthService, get_auth_service

auth_router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
templates = Jinja2Templates(directory=f"{settings.base_dir}/templates")


@auth_router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request) -> HTMLResponse:
    """Страница регистрации (установки пароля)."""
    return templates.TemplateResponse("register.html", {"request": request})  # type: ignore[arg-type]


# Регистрация
@auth_router.post("/register")
async def register(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    repo: TinyDBRepository = Depends(get_tinydb_repo),
) -> RedirectResponse:
    """Обработка формы регистрации."""
    try:
        if await repo.create_user(username=email, password=password):
            return RedirectResponse(
                url="/api/v1/auth/register?success=1", status_code=303
            )
        return RedirectResponse(
            url="/api/v1/auth/register?error=User already exists",
            status_code=303,
        )

    except HTTPException as e:
        # Возвращаем ошибку обратно на форму
        return RedirectResponse(
            url=f"/api/v1/auth/register?error={e.detail}", status_code=303
        )
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}", exc_info=True)
        return RedirectResponse(
            url="/api/v1/auth/register?error=unexpected_error", status_code=303
        )


@auth_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Страница регистрации (установки пароля)."""
    return templates.TemplateResponse("login.html", {"request": request})  # type: ignore[arg-type]


# Логин (получение токена)
@auth_router.post("/token")
async def login(
    response: Response,
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    repo: TinyDBRepository = Depends(get_tinydb_repo),
    auth_service: UserAuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """
    Обработка входа.
    Получает токены от сервиса и устанавливает их в HttpOnly куки.
    """
    try:
        role = await repo.get_role_user(form_data.username, form_data.password)
        if role is None:
            return RedirectResponse(
                url="/api/v1/auth/login?error=Incorrect email or password.",
                status_code=303,
            )

        # 1. Вызываем ваш сервис, который проверяет пароль и генерирует токены
        token_response: TokenResponse = await auth_service.create_tokens(
            form_data.username, role
        )

        # 2. Создаем ответ-редирект (например, на главную страницу)
        response = RedirectResponse(url="/api/v1/tiny/admin/db/", status_code=303)

        # 3. Устанавливаем куки на сервере
        # Access Token (короткий)
        response.set_cookie(
            key="access_token",
            value=token_response.access_token,
            httponly=True,  # Недоступен через JS
            max_age=token_response.expires_in,
            expires=token_response.expires_in,
            path="/",
            samesite="lax",  # Защита от CSRF
        )

        # Refresh Token (длинный)
        refresh_max_age = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        response.set_cookie(
            key="refresh_token",
            value=token_response.refresh_token,
            httponly=True,
            max_age=refresh_max_age,
            expires=refresh_max_age,
            path="/",
            samesite="lax",
        )

        return response

    except HTTPException as e:
        # При ошибке редиректим обратно на логин с параметром ошибки
        # e.detail обычно "Incorrect email or password"
        return RedirectResponse(
            url=f"/api/v1/auth/login?error={e.detail}", status_code=303
        )


@auth_router.post("/logout")
async def logout() -> Response:
    """Удаляет куки и редиректит на логин."""
    # response = RedirectResponse(url="/api/v1/auth/login", status_code=303)
    response = Response(status_code=200)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.headers["HX-Redirect"] = "/api/v1/auth/login/"
    return response
