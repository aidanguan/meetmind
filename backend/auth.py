import os
import json
import httpx
from typing import Optional, Dict
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, jwk
from jose.utils import base64url_decode
from sqlalchemy.orm import Session
from datetime import datetime

from database import get_db
from models import User

# Configuration
AZURE_AD_CLIENT_ID = os.getenv("AZURE_AD_CLIENT_ID")
AZURE_AD_TENANT_ID = os.getenv("AZURE_AD_TENANT_ID")
# Use common endpoint or specific tenant endpoint. Specific tenant is safer for single-tenant apps.
JWKS_URL = f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/discovery/v2.0/keys" if AZURE_AD_TENANT_ID else None

# This scheme will parse the token from the Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

SKIP_AUTH = True

class AzureADAuth:
    def __init__(self):
        self.jwks = None
        self.last_fetch = 0
        self.cache_ttl = 3600  # 1 hour

    async def get_jwks(self):
        now = datetime.utcnow().timestamp()
        if self.jwks and (now - self.last_fetch < self.cache_ttl):
            return self.jwks
        
        if not JWKS_URL:
            # If config is missing, we can't validate.
            # In a real app we might want to fail startup, but here we raise at runtime.
            raise HTTPException(status_code=500, detail="Azure AD Tenant ID not configured")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(JWKS_URL)
                response.raise_for_status()
                self.jwks = response.json()
                self.last_fetch = now
                return self.jwks
            except Exception as e:
                print(f"Error fetching JWKS: {e}")
                raise HTTPException(status_code=500, detail="Could not fetch Azure AD keys")

    async def verify_token(self, token: str):
        jwks = await self.get_jwks()
        
        try:
            unverified_header = jwt.get_unverified_header(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token header")

        rsa_key = {}
        if 'kid' not in unverified_header:
             raise HTTPException(status_code=401, detail="Token header missing kid")

        for key in jwks['keys']:
            if key['kid'] == unverified_header['kid']:
                rsa_key = {
                    'kty': key['kty'],
                    'kid': key['kid'],
                    'use': key['use'],
                    'n': key['n'],
                    'e': key['e']
                }
                break
        
        if not rsa_key:
            raise HTTPException(status_code=401, detail="Unable to find appropriate key")

        try:
            # Azure AD tokens usually have 'aud' as the Client ID (for id_tokens) or API URI (for access_tokens).
            # We assume the client is sending an ID token or an Access Token for this API.
            # If validating access token for API, 'aud' should match the App ID URI or Client ID.
            # We'll use AZURE_AD_CLIENT_ID as the expected audience for simplicity.
            
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=AZURE_AD_CLIENT_ID,
                options={"verify_at_hash": False} 
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.JWTClaimsError:
            raise HTTPException(status_code=401, detail="Incorrect claims, please check the audience and issuer")
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Unable to parse authentication token: {str(e)}")

auth_handler = AzureADAuth()

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if SKIP_AUTH:
        # Return a debug user
        debug_oid = "debug-user-oid"
        user = db.query(User).filter(User.azure_oid == debug_oid).first()
        if not user:
             user = User(
                azure_oid=debug_oid,
                email="debug@example.com",
                full_name="Debug User",
                last_login_at=datetime.utcnow()
            )
             db.add(user)
             db.commit()
             db.refresh(user)
        return user

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if not AZURE_AD_CLIENT_ID or not AZURE_AD_TENANT_ID:
        # For development/demo purposes if env vars are missing, we might want to bypass or warn.
        # But strictly speaking we should fail.
        # Let's print a warning and fail.
        print("Warning: AZURE_AD_CLIENT_ID or AZURE_AD_TENANT_ID is missing.")
        raise HTTPException(status_code=500, detail="Azure AD configuration missing on server")

    payload = await auth_handler.verify_token(token)
    
    # Extract user info
    oid = payload.get("oid")
    # 'preferred_username' is common for email in V2 tokens, 'upn' in V1.
    email = payload.get("preferred_username") or payload.get("upn") or payload.get("email")
    name = payload.get("name")

    if not oid:
        raise HTTPException(status_code=401, detail="Token missing OID claim")

    user = db.query(User).filter(User.azure_oid == oid).first()
    
    if not user:
        # JIT Provisioning
        user = User(
            azure_oid=oid,
            email=email,
            full_name=name,
            last_login_at=datetime.utcnow()
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update last login
        user.last_login_at = datetime.utcnow()
        # Update details if changed? Maybe not every time.
        if email and user.email != email:
            user.email = email
        if name and user.full_name != name:
            user.full_name = name
            
        db.commit()
    
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user
