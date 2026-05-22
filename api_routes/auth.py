import os
import bcrypt
import jwt
import datetime
from fastapi import APIRouter, Request, Response, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from supabase import create_client, Client

router = APIRouter()

JWT_SECRET = os.environ.get("JWT_SECRET", "biologic_secret_key_123")
ADMIN_PASSWORD = os.environ.get("ADMIN_MASTER_PASSWORD", "123456")

supabase_url = os.environ.get("SUPABASE_URL", "https://dominio-faltante.supabase.co")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "llave-faltante-ey")
supabase_admin: Client = create_client(supabase_url, supabase_key)

class AuthRequest(BaseModel):
    action: str
    email: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    accessCode: Optional[str] = None

class AdminAuthRequest(BaseModel):
    action: str
    password: Optional[str] = None

@router.post("/auth")
async def auth_switchboard(req_data: AuthRequest, request: Request, response: Response):
    action = req_data.action
    
    if not action:
        raise HTTPException(status_code=400, detail="Missing action")

    try:
        if action == "register":
            email = req_data.email
            username = req_data.username
            password = req_data.password
            access_code = req_data.accessCode

            if not email or not username or not password or not access_code:
                raise HTTPException(status_code=400, detail="Faltan campos (email, username, password, accessCode)")

            # 1. Verify access code
            code_res = supabase_admin.from_("access_codes").select("*").eq("code", access_code).execute()
            if not code_res.data:
                raise HTTPException(status_code=400, detail="El código de autorización es inválido.")
            
            code_data = code_res.data[0]
            if code_data.get("status") != "available":
                raise HTTPException(status_code=400, detail="Este código de autorización ya está en uso o ha sido revocado.")

            # 2. Hash password
            # bcrypt in python requires bytes
            salt = bcrypt.gensalt(10)
            password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

            # 3. Create user
            try:
                user_res = supabase_admin.from_("user_profiles").insert({
                    "email": email,
                    "username": username,
                    "password_hash": password_hash,
                    "access_code": access_code
                }).execute()
            except Exception as db_err:
                err_str = str(db_err)
                if "23505" in err_str or "already exists" in err_str.lower():
                    raise HTTPException(status_code=400, detail="El correo electrónico ya está registrado.")
                raise db_err

            if not user_res.data:
                raise HTTPException(status_code=500, detail="Error al crear el perfil de usuario.")
            
            user_data = user_res.data[0]

            # 4. Update access code status
            supabase_admin.from_("access_codes").update({
                "status": "used",
                "used_by_email": email,
                "used_at": datetime.datetime.utcnow().isoformat()
            }).eq("code", access_code).execute()

            # 5. Generate JWT
            payload = {
                "userId": user_data.get("id"),
                "email": email,
                "username": username,
                "accessCode": access_code,
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
            }
            token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

            # Set HttpOnly Cookie
            response.set_cookie(
                key="biologic_token",
                value=token,
                httponly=True,
                secure=True,  # For Vercel production
                samesite="lax",
                max_age=7 * 24 * 60 * 60  # 7 days in seconds
            )

            return {
                "success": True,
                "token": token,
                "user": {
                    "userId": user_data.get("id"),
                    "email": email,
                    "username": username,
                    "accessCode": access_code
                }
            }

        elif action == "login":
            email = req_data.email
            password = req_data.password

            if not email or not password:
                raise HTTPException(status_code=400, detail="Faltan credenciales.")

            # 1. Find user
            user_res = supabase_admin.from_("user_profiles").select("*, access_codes(status)").eq("email", email).execute()
            if not user_res.data:
                raise HTTPException(status_code=400, detail="Credenciales inválidas.")

            user = user_res.data[0]

            # 2. Check if code is revoked
            access_code_data = user.get("access_codes")
            access_code_status = None
            if isinstance(access_code_data, dict):
                access_code_status = access_code_data.get("status")
            elif isinstance(access_code_data, list) and len(access_code_data) > 0:
                access_code_status = access_code_data[0].get("status")

            if access_code_status == "revoked":
                raise HTTPException(status_code=403, detail="Tu licencia ha sido revocada por el administrador.")

            # 3. Check password
            password_hash = user.get("password_hash", "")
            is_match = bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
            if not is_match:
                raise HTTPException(status_code=400, detail="Credenciales inválidas.")

            # 4. Generate JWT
            payload = {
                "userId": user.get("id"),
                "email": user.get("email"),
                "username": user.get("username"),
                "accessCode": user.get("access_code"),
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
            }
            token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

            # Set HttpOnly Cookie
            response.set_cookie(
                key="biologic_token",
                value=token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=7 * 24 * 60 * 60
            )

            return {
                "success": True,
                "token": token,
                "user": {
                    "userId": user.get("id"),
                    "email": user.get("email"),
                    "username": user.get("username"),
                    "accessCode": user.get("access_code")
                }
            }

        elif action == "validate":
            # Support both header and cookies
            auth_header = request.headers.get("Authorization")
            token = None
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            if not token or token == "null" or token == "undefined":
                token = request.cookies.get("biologic_token")

            if not token:
                raise HTTPException(status_code=401, detail="No token")

            try:
                decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                
                # Verify if still not revoked
                code = decoded.get("accessCode")
                if code:
                    code_res = supabase_admin.from_("access_codes").select("status").eq("code", code).execute()
                    if code_res.data and code_res.data[0].get("status") == "revoked":
                        raise HTTPException(status_code=403, detail="Licencia revocada.")

                return {"success": True, "user": decoded}
            except jwt.PyJWTError:
                raise HTTPException(status_code=401, detail="Invalid token")

        elif action == "logout":
            response.delete_cookie(
                key="biologic_token",
                httponly=True,
                secure=True,
                samesite="lax"
            )
            return {"success": True}

        else:
            raise HTTPException(status_code=400, detail="Acción desconocida.")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin-auth")
async def admin_auth_switchboard(req_data: AdminAuthRequest, request: Request, response: Response):
    action = req_data.action

    try:
        if action == "login":
            password = req_data.password
            if not password:
                raise HTTPException(status_code=400, detail="Contraseña de administrador requerida.")

            if password != ADMIN_PASSWORD:
                raise HTTPException(status_code=401, detail="Credenciales de administrador inválidas.")

            # Generate Admin JWT
            payload = {
                "role": "admin",
                "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1)
            }
            token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

            # Set HttpOnly Cookie
            response.set_cookie(
                key="biologic_admin_token",
                value=token,
                httponly=True,
                secure=True,
                samesite="lax",
                max_age=60 * 60  # 1 hour
            )

            return {"success": True, "token": token}

        elif action == "logout":
            response.delete_cookie(
                key="biologic_admin_token",
                httponly=True,
                secure=True,
                samesite="lax"
            )
            return {"success": True}

        elif action == "validate":
            # Support both header and cookies
            auth_header = request.headers.get("Authorization")
            token = None
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
            if not token or token == "null" or token == "undefined":
                token = request.cookies.get("biologic_admin_token")

            if not token:
                raise HTTPException(status_code=401, detail="No autorizado.")

            try:
                decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
                if decoded.get("role") != "admin":
                    raise HTTPException(status_code=403, detail="No autorizado.")
                return {"success": True}
            except jwt.PyJWTError:
                raise HTTPException(status_code=401, detail="Token inválido o expirado.")

        else:
            raise HTTPException(status_code=400, detail="Acción desconocida.")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
