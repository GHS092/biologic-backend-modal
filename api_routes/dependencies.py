import os
import jwt
from fastapi import Request, HTTPException, status
from supabase import create_client, Client

JWT_SECRET = os.environ.get("JWT_SECRET", "biologic_secret_key_123")

supabase_url = os.environ.get("SUPABASE_URL", "https://dominio-faltante.supabase.co")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "llave-faltante-ey")
supabase_admin: Client = create_client(supabase_url, supabase_key)

def get_token_from_request(request: Request, cookie_name: str) -> str:
    # 1. Try to get from Authorization Header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        if token and token != "null" and token != "undefined":
            return token
    
    # 2. Try to get from Cookie
    return request.cookies.get(cookie_name)

async def get_current_user(request: Request) -> dict:
    token = get_token_from_request(request, "biologic_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Acceso denegado. Se requiere autenticación."
        )
    
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        
        # Verify if license/access code is revoked
        code = decoded.get("accessCode")
        if code:
            try:
                res = supabase_admin.from_("access_codes").select("status").eq("code", code).execute()
                if res.data and len(res.data) > 0:
                    if res.data[0].get("status") == "revoked":
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Tu licencia ha sido revocada por el administrador."
                        )
            except Exception as db_err:
                print(f"[Auth Dependency] Warning verifying code: {db_err}")
                
        return decoded
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado."
        )

async def get_current_admin(request: Request) -> dict:
    token = get_token_from_request(request, "biologic_admin_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No autorizado. Token de Administrador faltante."
        )
    
    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if decoded.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acceso denegado. Se requiere rol de Administrador."
            )
        return decoded
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de administrador inválido o expirado."
        )
