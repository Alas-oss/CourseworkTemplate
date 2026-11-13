import os
from functools import lru_cache

import firebase_admin
from fastapi import Header, HTTPException
from firebase_admin import auth, credentials

CREDENTIALS_PATH = os.getenv(
    "FIREBASE_CREDENTIALS",
    "/app/firebase_credentials.json"
)


class FirebaseNotConfigured(RuntimeError):
    """Raised when the Firebase credentials are missing or unusable."""


@lru_cache(maxsize=1)
def initialise_firebase():
    if not os.path.exists(CREDENTIALS_PATH):
        raise FirebaseNotConfigured(
            "Credentials file not found: " + CREDENTIALS_PATH
        )

    certificate = credentials.Certificate(CREDENTIALS_PATH)
    return firebase_admin.initialize_app(certificate)


def verify_firebase_token(id_token: str) -> dict:
    
    try:
        initialise_firebase()
    except FirebaseNotConfigured:
        raise
    except Exception as error:
        raise FirebaseNotConfigured(str(error))

    return auth.verify_id_token(id_token, clock_skew_seconds=10)


def get_current_user(
    authorization: str | None = Header(default=None, alias="Authorization")
) -> dict:
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"}
        )

    try:
        claims = verify_firebase_token(token.strip())
    except FirebaseNotConfigured:
        raise HTTPException(
            status_code=503,
            detail="Authentication service is not configured"
        )
    except auth.CertificateFetchError:
        raise HTTPException(
            status_code=503,
            detail="Could not reach the Firebase key service"
        )
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return {
        "uid": claims.get("uid") or claims.get("sub"),
        "email": claims.get("email")
    }