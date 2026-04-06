from fastapi import APIRouter, Depends, HTTPException, Response

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


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response) -> LoginResponse:
    if not auth_service.auth_active:
        raise HTTPException(
            status_code=409,
            detail="Admin authentication is not enabled for this environment.",
        )

    user = auth_service.authenticate_user(payload.username, payload.password)
    if user is None:
        log_event(
            "auth.login",
            "Login failed.",
            status="warning",
            category="audit",
            attempted_username=payload.username.strip(),
        )
        raise HTTPException(status_code=401, detail="Invalid credentials.")

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
