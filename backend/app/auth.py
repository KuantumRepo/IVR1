"""
Authentication Module — Username + Password + TOTP 2FA

Single-user auth system. Credentials live entirely in environment variables.
Nothing touches the database.

Environment Variables Required:
    AUTH_USERNAME          - Login username (default: admin)
    AUTH_PASSWORD_HASH     - bcrypt hash of the password
    TOTP_SECRET            - pyotp-compatible base32 secret
    EMERGENCY_BYPASS_CODE  - Fallback code if authenticator is unavailable
    JWT_SECRET             - Secret key for signing JWTs
    JWT_EXPIRE_HOURS       - Token validity in hours (default: 24)
    QR_SETUP_ENABLED       - Set to 'true' to enable the QR code endpoint
"""

import os
import io
import base64
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from jose import jwt, JWTError
import bcrypt
import pyotp
import qrcode

logger = logging.getLogger(__name__)

# ── Environment Configuration ────────────────────────────────────────────────
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
AUTH_PASSWORD_HASH = os.getenv("AUTH_PASSWORD_HASH", "")
TOTP_SECRET = os.getenv("TOTP_SECRET", "")
EMERGENCY_BYPASS_CODE = os.getenv("EMERGENCY_BYPASS_CODE", "")
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
QR_SETUP_ENABLED = os.getenv("QR_SETUP_ENABLED", "false").lower() == "true"

# ── Crypto Setup ─────────────────────────────────────────────────────────────
security_scheme = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception:
        return False

# ── Pydantic Schemas ─────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


# ── JWT Utilities ────────────────────────────────────────────────────────────

def create_access_token(subject: str) -> tuple[str, datetime]:
    """Create a signed JWT with expiry."""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    return token, expire


def verify_token(token: str) -> dict:
    """Verify and decode a JWT. Raises JWTError on failure."""
    return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])


# ── Dependency: Require Valid JWT ────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str:
    """
    FastAPI dependency that extracts and validates the JWT from the
    Authorization: Bearer header. Returns the username (subject).
    
    Used as a dependency on protected routes.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = verify_token(credentials.credentials)
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """
    Authenticate with username + password + TOTP code.
    
    TOTP code can be either:
    - A valid 6-digit TOTP code from an authenticator app
    - The emergency bypass code (for phone loss scenarios)
    
    On failure, always returns the same generic error regardless of
    which field was wrong — never reveals which credential failed.
    """
    # ── Validate username ─────────────────────────────────────────────────
    if body.username != AUTH_USERNAME:
        logger.warning(f"Login attempt with invalid username: {body.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ── Validate password ─────────────────────────────────────────────────
    if not AUTH_PASSWORD_HASH or not verify_password(body.password, AUTH_PASSWORD_HASH):
        logger.warning(f"Login attempt with invalid password for user: {body.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ── Validate TOTP or emergency bypass code ────────────────────────────
    totp_valid = False

    # Check emergency bypass code first
    if EMERGENCY_BYPASS_CODE and body.totp_code == EMERGENCY_BYPASS_CODE:
        totp_valid = True
        logger.warning("Login using EMERGENCY BYPASS CODE — consider rotating it")

    # Check TOTP
    if not totp_valid and TOTP_SECRET:
        totp = pyotp.TOTP(TOTP_SECRET)
        totp_valid = totp.verify(body.totp_code, valid_window=1)

    # If no TOTP secret is configured, skip TOTP validation entirely
    # (allows initial setup before TOTP is configured)
    if not totp_valid and TOTP_SECRET:
        logger.warning(f"Login attempt with invalid TOTP for user: {body.username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ── Success ───────────────────────────────────────────────────────────
    token, expire = create_access_token(subject=body.username)
    expires_in = int((expire - datetime.now(timezone.utc)).total_seconds())

    logger.info(f"Successful login for user: {body.username}")
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.get("/verify")
async def verify(user: str = Depends(get_current_user)):
    """Verify that a JWT token is valid. Returns 200 if valid, 401 if not."""
    return {"status": "authenticated", "user": user}


@router.get("/qr")
async def get_qr_code():
    """
    Generate and return the TOTP QR code for Google Authenticator setup.
    
    Returns a full HTML page with the scannable QR code and setup instructions.
    
    SECURITY: This endpoint is ONLY available when QR_SETUP_ENABLED=true.
    After scanning, set QR_SETUP_ENABLED=false and redeploy to permanently
    disable this endpoint.
    """
    from fastapi.responses import HTMLResponse

    if not QR_SETUP_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="QR setup is disabled. Set QR_SETUP_ENABLED=true to enable."
        )

    if not TOTP_SECRET:
        raise HTTPException(
            status_code=500,
            detail="TOTP_SECRET is not configured."
        )

    # Generate the otpauth URI
    totp = pyotp.TOTP(TOTP_SECRET)
    provisioning_uri = totp.provisioning_uri(
        name=AUTH_USERNAME,
        issuer_name="Broadcaster"
    )

    # Generate QR code as PNG in memory
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    b64_image = base64.b64encode(buffer.read()).decode("utf-8")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Broadcaster — TOTP Setup</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            min-height: 100vh;
            background: #000;
            color: #fff;
            font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }}
        .card {{
            max-width: 460px;
            width: 100%;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 20px;
            padding: 40px 32px;
            backdrop-filter: blur(40px);
            box-shadow: 0 25px 50px rgba(0,0,0,0.5);
        }}
        .icon {{
            width: 48px; height: 48px;
            background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.02));
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 14px;
            display: flex; align-items: center; justify-content: center;
            margin: 0 auto 24px;
        }}
        .icon svg {{ width: 24px; height: 24px; stroke: rgba(255,255,255,0.8); fill: none; stroke-width: 1.5; }}
        h1 {{ font-size: 20px; font-weight: 600; text-align: center; margin-bottom: 6px; letter-spacing: -0.01em; }}
        .subtitle {{ font-size: 11px; color: rgba(255,255,255,0.3); text-align: center; font-family: monospace; letter-spacing: 0.2em; text-transform: uppercase; margin-bottom: 32px; }}
        .qr-wrap {{
            background: #fff;
            border-radius: 16px;
            padding: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 auto 28px;
            width: fit-content;
        }}
        .qr-wrap img {{ display: block; width: 240px; height: 240px; image-rendering: pixelated; }}
        .manual-key {{
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 28px;
        }}
        .manual-key label {{ font-size: 10px; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 0.15em; font-weight: 500; display: block; margin-bottom: 8px; }}
        .manual-key code {{
            font-family: 'SF Mono', 'Fira Code', monospace;
            font-size: 15px;
            letter-spacing: 0.12em;
            color: #10b981;
            word-break: break-all;
            user-select: all;
            cursor: text;
        }}
        .steps {{ list-style: none; counter-reset: step; }}
        .steps li {{
            counter-increment: step;
            font-size: 13px;
            color: rgba(255,255,255,0.5);
            padding: 8px 0;
            padding-left: 32px;
            position: relative;
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }}
        .steps li:last-child {{ border-bottom: none; }}
        .steps li::before {{
            content: counter(step);
            position: absolute;
            left: 0;
            width: 20px; height: 20px;
            background: rgba(255,255,255,0.06);
            border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
            font-size: 11px;
            font-weight: 600;
            color: rgba(255,255,255,0.4);
        }}
        .steps li strong {{ color: rgba(255,255,255,0.8); font-weight: 500; }}
        .warning {{
            margin-top: 24px;
            background: rgba(239,68,68,0.08);
            border: 1px solid rgba(239,68,68,0.15);
            border-radius: 10px;
            padding: 12px 16px;
            font-size: 11px;
            color: rgba(239,68,68,0.8);
            text-align: center;
            line-height: 1.5;
        }}
        .footer {{ text-align: center; margin-top: 28px; font-size: 9px; color: rgba(255,255,255,0.1); font-family: monospace; letter-spacing: 0.2em; text-transform: uppercase; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">
            <svg viewBox="0 0 24 24" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
        </div>
        <h1>Authenticator Setup</h1>
        <p class="subtitle">Scan with Google Authenticator</p>
        
        <div class="qr-wrap">
            <img src="data:image/png;base64,{b64_image}" alt="TOTP QR Code" />
        </div>

        <div class="manual-key">
            <label>Manual Entry Key</label>
            <code>{TOTP_SECRET}</code>
        </div>

        <ol class="steps">
            <li>Open <strong>Google Authenticator</strong> on your phone</li>
            <li>Tap <strong>+</strong> then <strong>Scan a QR code</strong></li>
            <li>Point your camera at the QR code above</li>
            <li>After scanning, edit <strong>.env</strong> and set <strong>QR_SETUP_ENABLED=false</strong></li>
            <li>Run <strong>docker compose restart backend</strong></li>
        </ol>

        <div class="warning">
            ⚠ This page will be permanently disabled after you set QR_SETUP_ENABLED=false.<br/>
            Do not share this URL or leave it enabled in production.
        </div>

        <p class="footer">Broadcaster • Authorized Setup Only</p>
    </div>
</body>
</html>"""

    return HTMLResponse(content=html)

