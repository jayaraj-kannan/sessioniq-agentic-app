import hashlib
import os
import secrets
import time
from typing import Optional, Dict, Any
from fastapi import Header, HTTPException
from google.cloud import firestore

from app.tools import _get_project_id

def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()

def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=_get_project_id())

def register_user(email: str, password: str, display_name: Optional[str] = None) -> Dict[str, Any]:
    """Registers a new user in Firestore 'users' collection."""
    db = get_firestore_client()
    clean_email = email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise ValueError("Invalid email format")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    # Check if user already exists
    user_docs = list(db.collection("users").where("email", "==", clean_email).limit(1).stream())
    if user_docs:
        raise ValueError("User with this email already exists")

    user_id = f"user-{secrets.token_hex(8)}"
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    token = secrets.token_urlsafe(32)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    name = display_name.strip() if display_name and display_name.strip() else clean_email.split("@")[0].capitalize()

    user_data = {
        "user_id": user_id,
        "email": clean_email,
        "display_name": name,
        "salt": salt,
        "password_hash": password_hash,
        "auth_token": token,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    db.collection("users").document(user_id).set(user_data)

    return {
        "user_id": user_id,
        "email": clean_email,
        "display_name": name,
        "token": token,
    }

def login_user(email: str, password: str) -> Dict[str, Any]:
    """Authenticates user against Firestore 'users' collection and returns an auth token."""
    db = get_firestore_client()
    clean_email = email.strip().lower()

    user_docs = list(db.collection("users").where("email", "==", clean_email).limit(1).stream())
    if not user_docs:
        raise ValueError("Invalid email or password")

    user_dict = user_docs[0].to_dict()
    salt = user_dict.get("salt", "")
    expected_hash = user_dict.get("password_hash", "")
    provided_hash = _hash_password(password, salt)

    if provided_hash != expected_hash:
        raise ValueError("Invalid email or password")

    # Refresh auth token
    token = secrets.token_urlsafe(32)
    user_id = user_dict.get("user_id")
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    db.collection("users").document(user_id).update({
        "auth_token": token,
        "updated_at": now_iso,
    })

    return {
        "user_id": user_id,
        "email": clean_email,
        "display_name": user_dict.get("display_name", clean_email.split("@")[0]),
        "token": token,
    }

def get_current_user_optional(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """Extracts user from Authorization header if present."""
    if not authorization:
        return None

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not token:
        return None

    db = get_firestore_client()
    user_docs = list(db.collection("users").where("auth_token", "==", token).limit(1).stream())
    if not user_docs:
        return None

    u = user_docs[0].to_dict()
    return {
        "user_id": u.get("user_id"),
        "email": u.get("email"),
        "display_name": u.get("display_name"),
    }

def get_current_user_required(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Requires a valid logged-in user in Firestore."""
    user = get_current_user_optional(authorization)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in to perform this action."
        )
    return user

def verify_session_ownership(session_id: str, user: Dict[str, Any], db: Optional[firestore.Client] = None) -> Dict[str, Any]:
    """Verifies that the provided user is the owner of the session."""
    if db is None:
        db = get_firestore_client()

    doc = db.collection("sessions").document(session_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Session not found")

    session_data = doc.to_dict()
    owner_id = session_data.get("owner_id")

    # If the session has an owner, check that it matches
    if owner_id and owner_id != user.get("user_id"):
        raise HTTPException(
            status_code=403,
            detail="Access forbidden: Only the session owner can upload materials, generate quizzes, or manage rooms for this session."
        )

    return session_data
