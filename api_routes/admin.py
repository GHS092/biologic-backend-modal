import os
import random
import hashlib
import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from supabase import create_client, Client

from .dependencies import get_current_admin

router = APIRouter()

supabase_url = os.environ.get("SUPABASE_URL", "https://dominio-faltante.supabase.co")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "llave-faltante-ey")
supabase_admin: Client = create_client(supabase_url, supabase_key)

# Helpers
def generate_med_code() -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    code = "MED-"
    for _ in range(6):
        code += random.choice(chars)
    return code

def generate_b2b_key() -> str:
    # 16 bytes = 32 hex chars
    import secrets
    return f"sk_biologic_{secrets.token_hex(16)}"

def hash_b2b_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

# Schemas
class CreateAccessCodeRequest(BaseModel):
    customCode: Optional[str] = None

class RevokeAccessCodeRequest(BaseModel):
    code: str

class CreateB2BKeyRequest(BaseModel):
    clientName: str
    tier: str
    creditsTotal: int
    rpmLimit: int

class UpdateB2BKeyRequest(BaseModel):
    id: str
    status: str

class DeleteB2BKeyRequest(BaseModel):
    id: str

class SaveConfigRequest(BaseModel):
    api_keys: List[str]
    active_model: str
    kill_switch: bool
    api_provider: str
    dictation_enabled: bool
    dictation_model: str
    block_global: Optional[bool] = False
    block_chat_discoveries: Optional[bool] = False
    block_assimilation_tray: Optional[bool] = False
    block_medical_library: Optional[bool] = False

# --- Access Codes Routes ---
@router.get("/admin-access-codes")
async def get_access_codes(admin: dict = Depends(get_current_admin)):
    try:
        res = supabase_admin.from_("access_codes")\
            .select("*, user_profiles(email, username)")\
            .order("created_at", desc=True)\
            .execute()
        return {"success": True, "codes": res.data or []}
    except Exception as e:
        err_str = str(e)
        if "42P01" in err_str:
            return {"success": True, "codes": []}
        raise HTTPException(status_code=500, detail=err_str)

@router.post("/admin-access-codes")
async def create_access_code(req_data: CreateAccessCodeRequest, admin: dict = Depends(get_current_admin)):
    custom_code = req_data.customCode
    code_to_insert = ""

    if custom_code and custom_code.strip():
        code_to_insert = custom_code.strip().upper()
    else:
        code_to_insert = generate_med_code()

    try:
        res = supabase_admin.from_("access_codes").insert({
            "code": code_to_insert,
            "status": "available"
        }).execute()

        if not res.data:
            raise HTTPException(status_code=500, detail="Failed to save access code.")

        return {"success": True, "message": f"Código {code_to_insert} generado."}
    except Exception as e:
        err_str = str(e)
        if "23505" in err_str or "already exists" in err_str.lower():
            raise HTTPException(status_code=400, detail="Ese código ya existe. Por favor elige otro.")
        raise HTTPException(status_code=500, detail=err_str)

@router.delete("/admin-access-codes")
async def revoke_access_code(req_data: RevokeAccessCodeRequest, admin: dict = Depends(get_current_admin)):
    code = req_data.code
    if not code:
        raise HTTPException(status_code=400, detail="Falta el código.")

    try:
        supabase_admin.from_("access_codes").update({
            "status": "revoked"
        }).eq("code", code).execute()

        return {"success": True, "message": f"Código {code} revocado."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- B2B API Keys Routes ---
@router.get("/admin-b2b-keys")
async def get_b2b_keys(admin: dict = Depends(get_current_admin)):
    try:
        res = supabase_admin.from_("b2b_api_keys").select("*").order("created_at", desc=True).execute()
        return {"success": True, "keys": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/admin-b2b-keys")
async def create_b2b_key(req_data: CreateB2BKeyRequest, admin: dict = Depends(get_current_admin)):
    client_name = req_data.clientName
    tier = req_data.tier
    credits_total = req_data.creditsTotal
    rpm_limit = req_data.rpmLimit

    if not client_name:
        raise HTTPException(status_code=400, detail="El nombre del cliente es obligatorio.")

    raw_key = generate_b2b_key()
    hashed_key = hash_b2b_key(raw_key)

    try:
        res = supabase_admin.from_("b2b_api_keys").insert({
            "client_name": client_name,
            "hashed_key": hashed_key,
            "tier": tier,
            "credits_total": credits_total,
            "credits_used": 0,
            "rpm_limit": rpm_limit,
            "status": "Activa"
        }).execute()

        if not res.data:
            raise HTTPException(status_code=500, detail="No se pudo registrar la llave B2B.")

        return {
            "success": True,
            "keyData": res.data[0],
            "rawKey": raw_key
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/admin-b2b-keys")
async def update_b2b_key(req_data: UpdateB2BKeyRequest, admin: dict = Depends(get_current_admin)):
    key_id = req_data.id
    status_val = req_data.status

    if not key_id or not status_val:
        raise HTTPException(status_code=400, detail="Faltan parámetros.")

    try:
        res = supabase_admin.from_("b2b_api_keys").update({
            "status": status_val
        }).eq("id", key_id).execute()

        return {"success": True, "message": f"Estado actualizado a {status_val}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/admin-b2b-keys")
async def delete_b2b_key(req_data: DeleteB2BKeyRequest, admin: dict = Depends(get_current_admin)):
    key_id = req_data.id
    if not key_id:
        raise HTTPException(status_code=400, detail="Faltan parámetros.")

    try:
        supabase_admin.from_("b2b_api_keys").delete().eq("id", key_id).execute()
        return {"success": True, "message": "Llave eliminada permanentemente."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Global Config Routes ---
@router.get("/admin-config")
async def get_admin_config(admin: dict = Depends(get_current_admin)):
    try:
        res = supabase_admin.from_("admin_system_config").select("*").eq("id", "global_config").execute()
        if not res.data:
            # Default fallback
            return {
                "success": True,
                "config": {
                    "api_keys": [],
                    "active_model": "gemini-3.1-pro-preview",
                    "kill_switch": False,
                    "api_provider": "google",
                    "dictation_enabled": True,
                    "dictation_model": "gemini-2.5-flash",
                    "block_global": False,
                    "block_chat_discoveries": False,
                    "block_assimilation_tray": False,
                    "block_medical_library": False
                }
            }
        
        data = res.data[0]
        safe_config = {
            **data,
            "block_global": data.get("block_global") is True,
            "block_chat_discoveries": data.get("block_chat_discoveries") is True,
            "block_assimilation_tray": data.get("block_assimilation_tray") is True,
            "block_medical_library": data.get("block_medical_library") is True
        }
        return {"success": True, "config": safe_config}
    except Exception as e:
        err_str = str(e)
        if "PGRST116" in err_str or "global_config" in err_str:
            return {
                "success": True,
                "config": {
                    "api_keys": [],
                    "active_model": "gemini-3.1-pro-preview",
                    "kill_switch": False,
                    "api_provider": "google",
                    "dictation_enabled": True,
                    "dictation_model": "gemini-2.5-flash",
                    "block_global": False,
                    "block_chat_discoveries": False,
                    "block_assimilation_tray": False,
                    "block_medical_library": False
                }
            }
        raise HTTPException(status_code=500, detail=err_str)

@router.post("/admin-config")
async def save_admin_config(req_data: SaveConfigRequest, admin: dict = Depends(get_current_admin)):
    api_keys = req_data.api_keys
    active_model = req_data.active_model
    kill_switch = req_data.kill_switch
    api_provider = req_data.api_provider
    dictation_enabled = req_data.dictation_enabled
    dictation_model = req_data.dictation_model
    block_global = req_data.block_global
    block_chat_discoveries = req_data.block_chat_discoveries
    block_assimilation_tray = req_data.block_assimilation_tray
    block_medical_library = req_data.block_medical_library

    base_payload = {
        "id": "global_config",
        "api_keys": api_keys or [],
        "active_model": active_model or "gemini-3.1-pro-preview",
        "kill_switch": kill_switch is True,
        "api_provider": api_provider or "google",
        "dictation_enabled": dictation_enabled is True,
        "dictation_model": dictation_model or "gemini-2.5-flash",
        "updated_at": datetime.datetime.utcnow().isoformat()
    }

    full_payload = {
        **base_payload,
        "block_global": block_global is True,
        "block_chat_discoveries": block_chat_discoveries is True,
        "block_assimilation_tray": block_assimilation_tray is True,
        "block_medical_library": block_medical_library is True
    }

    try:
        # Try full save first
        res = supabase_admin.from_("admin_system_config").upsert(full_payload, on_conflict="id").execute()
        return {"success": True, "message": "Configuración global de seguridad salvaguardada en la Nube."}
    except Exception as e:
        print(f"[Admin Config] Full save failed, retrying base fields: {e}")
        try:
            # Retry with base fields
            supabase_admin.from_("admin_system_config").upsert(base_payload, on_conflict="id").execute()
            return {
                "success": True,
                "migrationNeeded": True,
                "message": "Configuración guardada parcialmente. ¡RECUERDA ejecutar el script SQL de migración (supabase_migration_security_block.sql) en Supabase para habilitar las nuevas capas de seguridad de base de datos!"
            }
        except Exception as retry_err:
            raise HTTPException(status_code=500, detail=str(retry_err))

# --- Telemetry Routes ---
@router.get("/admin-telemetry")
async def get_admin_telemetry(admin: dict = Depends(get_current_admin)):
    try:
        res = supabase_admin.from_("api_usage_logs").select("*").execute()
        return {"success": True, "logs": res.data or []}
    except Exception as e:
        err_str = str(e)
        if "42P01" in err_str:
            return {"success": True, "logs": []}
        raise HTTPException(status_code=500, detail=err_str)

@router.delete("/admin-telemetry")
async def clear_admin_telemetry(admin: dict = Depends(get_current_admin)):
    try:
        supabase_admin.from_("api_usage_logs").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
