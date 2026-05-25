import os
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from supabase import create_client, Client

from .dependencies import get_current_user

router = APIRouter()

supabase_url = os.environ.get("SUPABASE_URL", "https://dominio-faltante.supabase.co")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "llave-faltante-ey")
supabase_admin: Client = create_client(supabase_url, supabase_key)

# Request schemas
class CreatePatientRequest(BaseModel):
    paciente_dni: str
    nombre: str
    edad: Optional[Any] = None
    ciudad: Optional[str] = None

class DeletePatientRequest(BaseModel):
    paciente_dni: str

class SaveReportRequest(BaseModel):
    paciente_dni: str
    tipo: str
    contenido_json: Dict[str, Any]
    origen: Optional[str] = "INTERFAZ_CLINICA"

class DeleteReportRequest(BaseModel):
    report_id: str

class ShareSessionRequest(BaseModel):
    session: Dict[str, Any]
    durationMinutes: int

@router.post("/create-patient")
async def create_patient(req_data: CreatePatientRequest, user: dict = Depends(get_current_user)):
    paciente_dni = req_data.paciente_dni
    nombre = req_data.nombre
    edad = req_data.edad
    ciudad = req_data.ciudad

    if not paciente_dni or not nombre:
        raise HTTPException(status_code=400, detail="Faltan parámetros obligatorios.")

    try:
        fecha_format = None
        if edad is not None:
            # 1. Comprobar si es un formato de fecha ISO YYYY-MM-DD
            try:
                datetime.datetime.strptime(str(edad), "%Y-%m-%d")
                fecha_format = str(edad)
            except ValueError:
                # 2. Si no, tratar como número de años/edad relativa
                try:
                    edad_num = int(edad)
                    if edad_num > 1900:
                        fecha_format = f"{edad_num}-01-01"
                    elif edad_num < 130:
                        current_year = datetime.datetime.now().year
                        fecha_format = f"{current_year - edad_num}-01-01"
                except (ValueError, TypeError):
                    pass

        payload = {
            "dni": paciente_dni,
            "nombre_completo": nombre
        }

        if ciudad:
            payload["ciudad"] = ciudad

        if fecha_format:
            payload["fecha_nacimiento"] = fecha_format

        res = supabase_admin.from_("pacientes").upsert(payload, on_conflict="dni").execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="No se pudo registrar o actualizar el paciente en Supabase.")

        return {
            "success": True,
            "message": "Paciente creado exitosamente y sincronizado con Supabase."
        }
    except Exception as e:
        print(f"[Create Patient] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno en el servidor: {e}")

@router.post("/delete-patient")
@router.delete("/delete-patient")
async def delete_patient(req_data: DeletePatientRequest, user: dict = Depends(get_current_user)):
    paciente_dni = req_data.paciente_dni
    if not paciente_dni:
        raise HTTPException(status_code=400, detail="El DNI del paciente es obligatorio.")

    try:
        # 1. Delete all patient clinical records first (avoid FK constraint error)
        supabase_admin.from_("Registros_Clinicos").delete().eq("paciente_dni", paciente_dni).execute()

        # 2. Delete patient from patients table
        res = supabase_admin.from_("pacientes").delete().eq("dni", paciente_dni).execute()

        return {
            "success": True,
            "message": "Paciente y todos sus registros eliminados de la base de datos."
        }
    except Exception as e:
        print(f"[Delete Patient] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {e}")

@router.post("/save-report")
async def save_report(req_data: SaveReportRequest, user: dict = Depends(get_current_user)):
    paciente_dni = req_data.paciente_dni
    tipo = req_data.tipo
    contenido_json = req_data.contenido_json
    origen = req_data.origen or "INTERFAZ_CLINICA"

    if not paciente_dni or not tipo or not contenido_json:
        raise HTTPException(status_code=400, detail="Faltan parámetros obligatorios para guardar el registro clínico.")

    try:
        res = supabase_admin.from_("Registros_Clinicos").insert({
            "paciente_dni": paciente_dni,
            "tipo": tipo,
            "contenido_json": contenido_json,
            "origen": origen,
            "usuario_id": user.get("userId")
        }).execute()

        if not res.data:
            raise HTTPException(status_code=500, detail="No se pudo registrar el informe clínico en la base de datos.")

        return {
            "success": True,
            "message": "Reporte clínico sincronizado exitosamente con Supabase."
        }
    except Exception as e:
        print(f"[Save Report] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error del servidor: {e}")

@router.post("/delete-report")
@router.delete("/delete-report")
async def delete_report(req_data: DeleteReportRequest, user: dict = Depends(get_current_user)):
    report_id = req_data.report_id
    if not report_id:
        raise HTTPException(status_code=400, detail="El ID del reporte es obligatorio.")

    try:
        user_id = user.get("userId")
        # Borrar estrictamente si coincide el ID del reporte y el dueño es el usuario actual
        res = supabase_admin.from_("Registros_Clinicos").delete()\
            .eq("contenido_json->>id", report_id)\
            .eq("usuario_id", user_id)\
            .execute()

        return {
            "success": True,
            "message": "Reporte clínico eliminado de la base de datos."
        }
    except Exception as e:
        print(f"[Delete Report] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {e}")

@router.get("/sync-down")
async def sync_down(user: dict = Depends(get_current_user)):
    try:
        # Get all patients
        pacientes_res = supabase_admin.from_("pacientes").select("*").execute()
        pacientes = pacientes_res.data or []

        # Get all clinical records
        registros_res = supabase_admin.from_("Registros_Clinicos").select("*").execute()
        registros = registros_res.data or []

        formatted_registros = []
        for r in registros:
            json_data = r.get("contenido_json") or {}
            json_data["patientDni"] = r.get("paciente_dni")
            json_data["usuario_id"] = r.get("usuario_id")

            # Fallbacks
            if not json_data.get("date"):
                fecha_reg = r.get("fecha_registro")
                if fecha_reg:
                    # Parse standard UTC ISO format in python
                    try:
                        # Handle Z ending or replace with offset
                        cleaned_date = fecha_reg.replace("Z", "+00:00")
                        dt = datetime.datetime.fromisoformat(cleaned_date)
                        json_data["date"] = int(dt.timestamp() * 1000)
                    except ValueError:
                        json_data["date"] = int(datetime.datetime.utcnow().timestamp() * 1000)
                else:
                    json_data["date"] = int(datetime.datetime.utcnow().timestamp() * 1000)

            if not json_data.get("type"):
                json_data["type"] = "clinical" if r.get("tipo") == "TEXTO_CLINICO" else "investigator"

            if not json_data.get("id"):
                json_data["id"] = r.get("id")

            formatted_registros.append(json_data)

        return {
            "success": True,
            "pacientes": pacientes,
            "registros": formatted_registros
        }
    except Exception as e:
        print(f"[Sync Down] Error: {e}")
        raise HTTPException(status_code=500, detail="Error interno sincronizando datos de la nube.")

@router.post("/share-session")
async def share_session(req_data: ShareSessionRequest, user: dict = Depends(get_current_user)):
    session = req_data.session
    duration_minutes = req_data.durationMinutes

    if not session or not session.get("id") or not duration_minutes:
        raise HTTPException(status_code=400, detail="Faltan parámetros obligatorios.")

    try:
        expira_en = (datetime.datetime.utcnow() + datetime.timedelta(minutes=duration_minutes)).isoformat()

        payload = {
            "session_id": session.get("id"),
            "contenido_json": session,
            "expira_en": expira_en
        }

        res = supabase_admin.from_("Sesiones_Compartidas").upsert(payload, on_conflict="session_id").execute()
        if not res.data:
            raise HTTPException(status_code=500, detail="Error al guardar la sesión compartida.")

        return {
            "success": True,
            "message": "Sesión compartida exitosamente.",
            "expira_en": expira_en
        }
    except Exception as e:
        print(f"[Share Session] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-shared-sessions")
async def get_shared_sessions(user: dict = Depends(get_current_user)):
    try:
        now_str = datetime.datetime.utcnow().isoformat()
        
        # Get active ones
        res = supabase_admin.from_("Sesiones_Compartidas")\
            .select("session_id, contenido_json, expira_en, creado_en")\
            .gt("expira_en", now_str)\
            .order("creado_en", desc=True)\
            .execute()

        # Delete expired sessions in the background
        try:
            supabase_admin.from_("Sesiones_Compartidas").delete().lte("expira_en", now_str).execute()
        except Exception as del_err:
            print(f"[Get Shared Sessions] Warn deleting expired: {del_err}")

        return {
            "success": True,
            "data": res.data or []
        }
    except Exception as e:
        print(f"[Get Shared Sessions] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
