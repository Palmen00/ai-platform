from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.schemas.auth import AuthStatusResponse, LoginRequest, LoginResponse
from app.schemas.user import UserCreateRequest, UserListResponse, UserResponse, UserUpdateRequest
from app.services.auth import (
    auth_service,
    get_actor_log_fields,
    get_current_session,
    require_admin_from_either_header,
)
from app.services.user_insights import UserInsightsService
from app.services.logging_service import log_event

router = APIRouter(prefix="/auth", tags=["auth"])
user_insights_service = UserInsightsService()


@router.get("/status", response_model=AuthStatusResponse)
def get_auth_status(session=Depends(get_current_session)) -> AuthStatusResponse:
    return AuthStatusResponse(
        auth_enabled=auth_service.auth_enabled,
        auth_configured=auth_service.auth_configured,
        authenticated=session is not None,
        safe_mode_enabled=auth_service.safe_mode_enabled,
        username=session.username if session else None,
        role=session.role if session else None,
        session_expires_at=session.expires_at.isoformat() if session else None,
    )


GENERIC_LOGIN_ERROR = "Could not sign in with those credentials."


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> LoginResponse:
    if not auth_service.auth_active:
        raise HTTPException(
            status_code=409,
            detail="Admin authentication is not enabled for this environment.",
        )

    client_ip = request.client.host if request.client else None
    if auth_service.is_login_rate_limited(client_ip):
        log_event(
            "auth.login",
            "Login blocked by rate limit.",
            status="error",
            category="audit",
            attempted_username=payload.username.strip(),
            client_ip=client_ip or "unknown",
        )
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Please wait and try again.",
        )

    result = auth_service.authenticate_user(payload.username, payload.password)
    if result.status != "ok" or result.user is None:
        auth_service.record_login_attempt(client_ip)
        log_event(
            "auth.login",
            "Login blocked by lockout." if result.status == "locked" else "Login failed.",
            status="warning" if result.status == "invalid" else "error",
            category="audit",
            attempted_username=payload.username.strip(),
            remaining_attempts=result.remaining_attempts,
            locked_until=result.locked_until.isoformat() if result.locked_until else None,
            client_ip=client_ip or "unknown",
        )
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    user = result.user
    token, expires_at = auth_service.issue_session_token(user)
    auth_service.set_admin_session_cookie(
        response,
        token=token,
        expires_at=expires_at,
    )
    auth_service.user_service.record_login(user.id)
    log_event(
        "auth.login",
        "User logged in.",
        category="audit",
        actor_user_id=user.id,
        actor_username=user.username,
        actor_role=user.role,
        client_ip=client_ip or "unknown",
    )
    return LoginResponse(
        expires_at=expires_at.isoformat(),
        auth_enabled=auth_service.auth_enabled,
        auth_configured=auth_service.auth_configured,
        authenticated=True,
        safe_mode_enabled=auth_service.safe_mode_enabled,
        username=user.username,
        role=user.role,
    )


@router.post("/logout")
def logout(
    response: Response,
    session=Depends(get_current_session),
) -> dict[str, str]:
    log_event(
        "auth.logout",
        "User logged out.",
        category="audit",
        **get_actor_log_fields(session),
    )
    auth_service.clear_admin_session_cookie(response)
    return {"status": "ok"}


@router.get("/users", response_model=UserListResponse)
def list_users(_: object = Depends(require_admin_from_either_header)) -> UserListResponse:
    return UserListResponse(users=user_insights_service.list_user_summaries_with_stats())


@router.post("/users", response_model=UserResponse)
def create_user(
    payload: UserCreateRequest,
    session=Depends(require_admin_from_either_header),
) -> UserResponse:
    try:
        user = auth_service.user_service.create_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    log_event(
        "user.create",
        "Local user created.",
        category="audit",
        **get_actor_log_fields(session),
        target_user_id=user.id,
        target_username=user.username,
        target_role=user.role,
        target_enabled=user.enabled,
    )
    return UserResponse(user=auth_service.user_service.to_summary(user))


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    session=Depends(require_admin_from_either_header),
) -> UserResponse:
    try:
        user = auth_service.user_service.update_user(user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    log_event(
        "user.update",
        "Local user updated.",
        category="audit",
        **get_actor_log_fields(session),
        target_user_id=user.id,
        target_username=user.username,
        target_role=user.role,
        target_enabled=user.enabled,
        password_changed=bool(payload.password and payload.password.strip()),
    )
    return UserResponse(user=auth_service.user_service.to_summary(user))
