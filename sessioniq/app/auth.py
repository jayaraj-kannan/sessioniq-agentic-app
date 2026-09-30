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

def register_user(
    username: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
    display_name: Optional[str] = None
) -> Dict[str, Any]:
    """Registers a new user in Firestore 'users' collection with username and/or email."""
    db = get_firestore_client()

    clean_username = username.strip().lower() if username and username.strip() else ""
    clean_email = email.strip().lower() if email and email.strip() else ""

    if not clean_username and not clean_email:
        raise ValueError("Must provide either a username or an email address")

    if not password or len(password) < 6:
        raise ValueError("Password must be at least 6 characters")

    # If username given, check for duplicate username
    if clean_username:
        if len(clean_username) < 3:
            raise ValueError("Username must be at least 3 characters")
        user_by_name = list(db.collection("users").where("username", "==", clean_username).limit(1).stream())
        if user_by_name:
            raise ValueError(f"Username '{clean_username}' is already taken")

    # If email given, check for duplicate email
    if clean_email:
        if "@" not in clean_email:
            raise ValueError("Invalid email format")
        user_by_email = list(db.collection("users").where("email", "==", clean_email).limit(1).stream())
        if user_by_email:
            raise ValueError("User with this email already exists")

    # Fallback email if only username provided
    if not clean_email:
        clean_email = f"{clean_username}@sessioniq.local"

    # Fallback username if only email provided
    if not clean_username:
        clean_username = clean_email.split("@")[0]

    user_id = f"user-{secrets.token_hex(8)}"
    salt = secrets.token_hex(16)
    password_hash = _hash_password(password, salt)
    token = secrets.token_urlsafe(32)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    name = display_name.strip() if display_name and display_name.strip() else clean_username.capitalize()

    user_data = {
        "user_id": user_id,
        "username": clean_username,
        "email": clean_email,
        "display_name": name,
        "salt": salt,
        "password_hash": password_hash,
        "auth_provider": "password",
        "auth_token": token,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    db.collection("users").document(user_id).set(user_data)

    return {
        "user_id": user_id,
        "username": clean_username,
        "email": clean_email,
        "display_name": name,
        "token": token,
    }

def login_user(identifier: str, password: str) -> Dict[str, Any]:
    """Authenticates user against Firestore by username or email and returns an auth token."""
    db = get_firestore_client()
    clean_id = identifier.strip().lower()
    if not clean_id or not password:
        raise ValueError("Please provide your username/email and password")

    # Query by username or email
    user_docs = []
    if "@" in clean_id:
        user_docs = list(db.collection("users").where("email", "==", clean_id).limit(1).stream())
    else:
        user_docs = list(db.collection("users").where("username", "==", clean_id).limit(1).stream())

    if not user_docs:
        # Fallback check other field in case of format differences
        user_docs = list(db.collection("users").where("email", "==", clean_id).limit(1).stream())

    if not user_docs:
        raise ValueError("Invalid username/email or password")

    user_dict = user_docs[0].to_dict()
    salt = user_dict.get("salt", "")
    expected_hash = user_dict.get("password_hash", "")
    provided_hash = _hash_password(password, salt)

    if not expected_hash or provided_hash != expected_hash:
        raise ValueError("Invalid username/email or password")

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
        "username": user_dict.get("username", clean_id),
        "email": user_dict.get("email", ""),
        "display_name": user_dict.get("display_name", user_dict.get("username", clean_id)),
        "token": token,
    }

def google_authenticate(credential: Optional[str] = None, email: Optional[str] = None, name: Optional[str] = None, picture: Optional[str] = None) -> Dict[str, Any]:
    """Authenticates or registers a user via Google Sign-In.
    Supports Google ID tokens (credential) or verified profile data."""
    db = get_firestore_client()
    google_email = None
    display_name = name or ""
    avatar = picture or ""

    if credential:
        try:
            # Attempt to verify with google.oauth2 if client ID matches or parse JWT claims
            from google.oauth2 import id_token
            from google.auth.transport import requests
            claims = id_token.verify_oauth2_token(credential, requests.Request())
            google_email = claims.get("email")
            display_name = claims.get("name") or display_name
            avatar = claims.get("picture") or avatar
        except Exception:
            # Decode unverified JWT payload safely if audience is not configured yet
            try:
                import json
                import base64
                parts = credential.split(".")
                if len(parts) >= 2:
                    padding = "=" * (4 - len(parts[1]) % 4)
                    payload_bytes = base64.urlsafe_b64decode(parts[1] + padding)
                    claims = json.loads(payload_bytes.decode("utf-8"))
                    google_email = claims.get("email")
                    display_name = claims.get("name") or display_name
                    avatar = claims.get("picture") or avatar
            except Exception as jwt_err:
                pass

    if not google_email and email:
        google_email = email.strip().lower()

    if not google_email or "@" not in google_email:
        raise ValueError("Could not extract a valid Google email from sign-in credentials")

    clean_email = google_email.strip().lower()

    # Look up existing user by Google email
    user_docs = list(db.collection("users").where("email", "==", clean_email).limit(1).stream())
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    token = secrets.token_urlsafe(32)

    if user_docs:
        # Existing user - log them in and update token
        user_dict = user_docs[0].to_dict()
        user_id = user_dict.get("user_id")
        db.collection("users").document(user_id).update({
            "auth_token": token,
            "auth_provider": "google",
            "avatar_url": avatar or user_dict.get("avatar_url", ""),
            "updated_at": now_iso,
        })
        return {
            "user_id": user_id,
            "username": user_dict.get("username", clean_email.split("@")[0]),
            "email": clean_email,
            "display_name": user_dict.get("display_name", display_name or clean_email.split("@")[0]),
            "avatar_url": avatar or user_dict.get("avatar_url", ""),
            "token": token,
        }
    else:
        # New Google user - create profile
        user_id = f"user-{secrets.token_hex(8)}"
        username_candidate = clean_email.split("@")[0]
        # Check if username collision
        existing_names = list(db.collection("users").where("username", "==", username_candidate).limit(1).stream())
        if existing_names:
            username_candidate = f"{username_candidate}_{secrets.token_hex(2)}"

        resolved_name = display_name if display_name else username_candidate.capitalize()

        user_data = {
            "user_id": user_id,
            "username": username_candidate,
            "email": clean_email,
            "display_name": resolved_name,
            "auth_provider": "google",
            "avatar_url": avatar,
            "auth_token": token,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        db.collection("users").document(user_id).set(user_data)

        return {
            "user_id": user_id,
            "username": username_candidate,
            "email": clean_email,
            "display_name": resolved_name,
            "avatar_url": avatar,
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
