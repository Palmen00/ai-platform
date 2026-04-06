from fastapi import APIRouter, Depends, HTTPException

from app.schemas.auth import AuthStatusResponse, LoginRequest, LoginResponse
from app.services.auth import auth_service, get_admin_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/status", response_model=AuthStatusResponse)
def get_auth_status(token: str | None = Depends(get_admin_token)) -> AuthStatusResponse:
    session = auth_service.validate_admin_token(token)
    return AuthStatusResponse(
        auth_enabled=auth_service.auth_enabled,
        auth_configured=auth_service.auth_configured,
        authenticated=session is not None,
        safe_mode_enabled=auth_service.safe_mode_enabled,
        session_expires_at=session.expires_at.isoformat() if session else None,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if not auth_service.auth_active:
        raise HTTPException(
            status_code=409,
            detail="Admin authentication is not enabled for this environment.",
        )

    if not auth_service.verify_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid admin password.")

    token, expires_at = auth_service.issue_admin_token()
    return LoginResponse(
        token=token,
        expires_at=expires_at.isoformat(),
        auth_enabled=auth_service.auth_enabled,
        auth_configured=auth_service.auth_configured,
        authenticated=True,
        safe_mode_enabled=auth_service.safe_mode_enabled,
    )


@router.post("/logout")
def logout() -> dict[str, str]:
    return {"status": "ok"}
