import os
import re
import json
import datetime
import hashlib
import jwt
from fastapi import APIRouter, Request, Response, HTTPException, status, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
import asyncio
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
from supabase import create_client, Client

from .dependencies import get_current_user, get_current_admin, JWT_SECRET, get_token_from_request
from api_utils import gemini_core, shadow_librarian
from api_utils.gemini_core import get_random_ai_client, OpenRouterWrapper, FREE_MODEL_NAME, clean_json, medical_safety_settings

router = APIRouter()

supabase_url = os.environ.get("SUPABASE_URL", "https://dominio-faltante.supabase.co")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "llave-faltante-ey")
supabase_admin: Client = create_client(supabase_url, supabase_key)

# Request Schema for /invoke-gemini
class InvokeGeminiRequest(BaseModel):
    action: str
    payload: Dict[str, Any]

# Request Schema for /analyze-patient
class AnalyzePatientRequest(BaseModel):
    paciente_dni: str

# Request Schema for /ingest-audio
class IngestAudioRequest(BaseModel):
    paciente_dni: str
    nombre_medico: Optional[str] = "Desconocido"
    transcripcion_audio: str
    contexto_adicional: Optional[str] = ""

# Request Schema for /b2b-endpoint
class B2BRequest(BaseModel):
    patientData: str
    mode: Optional[str] = "clinical"
    pastContext: Optional[str] = ""
    attachedFiles: Optional[List[Dict[str, Any]]] = []
    region: Optional[str] = "Latinoamérica"
    city: Optional[str] = "Global"
    suspectedPathology: Optional[str] = ""

@router.post("/invoke-gemini")
async def invoke_gemini(
    req_data: InvokeGeminiRequest, 
    request: Request, 
    response: Response,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    async def event_generator():
        try:
            task = asyncio.create_task(_invoke_gemini_internal(req_data, request, response, background_tasks, user))
            while not task.done():
                yield " "
                await asyncio.sleep(2)
            res = task.result()
            yield json.dumps(res, ensure_ascii=False)
        except HTTPException as he:
            yield json.dumps({"success": False, "error": "HTTPException", "detail": he.detail}, ensure_ascii=False)
        except Exception as e:
            yield json.dumps({"success": False, "error": "Exception", "detail": str(e)}, ensure_ascii=False)

    return StreamingResponse(event_generator(), media_type="application/json")

async def _invoke_gemini_internal(
    req_data: InvokeGeminiRequest, 
    request: Request, 
    response: Response,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    action = req_data.action
    payload = req_data.payload
    access_code = user.get("accessCode", "ANONYMOUS")

    if not action:
        raise HTTPException(status_code=400, detail="Falta la acción (action).")

    try:
        if os.environ.get("NODE_ENV") != "production":
            print(f"[Railway Backend] Invocando acción protegida: {action}")

        # === ZERO TRUST ARCHITECTURE ===
        safe_config = {}
        block_global = False
        block_chat_discoveries = False
        block_assimilation_tray = False
        block_medical_library = False

        try:
            config_res = supabase_admin.from_("admin_system_config").select("*").eq("id", "global_config").execute()
            if config_res.data and len(config_res.data) > 0:
                data = config_res.data[0]
                if data.get("kill_switch") is True:
                    raise HTTPException(status_code=403, detail="SISTEMA BLOQUEADO: El Administrador ha activado el Kill Switch global.")
                
                if action == "transcribeAudio" and data.get("dictation_enabled") is False:
                    raise HTTPException(status_code=403, detail="SISTEMA BLOQUEADO: El Administrador ha desactivado el Asistente de Dictado Médico.")

                block_global = data.get("block_global") is True
                block_chat_discoveries = data.get("block_chat_discoveries") is True
                block_assimilation_tray = data.get("block_assimilation_tray") is True
                block_medical_library = data.get("block_medical_library") is True

                safe_config = {
                    "apiKeys": data.get("api_keys") or [],
                    "activeModel": data.get("active_model"),
                    "dictationModel": data.get("dictation_model"),
                    "apiProvider": data.get("api_provider")
                }
                print(f"[Vercel Serverless] Configuración cargada -> Chat: {data.get('active_model')} | Dictado: {data.get('dictation_model') or 'gemini-2.5-flash'}")
        except HTTPException as he:
            raise he
        except Exception as e:
            print(f"[Vercel Serverless] No se pudo cargar config de Supabase: {e}. Se usarán defaults.")

        # === CAPA DE SEGURIDAD DE INYECCIÓN DE BASE DE DATOS ===
        if action == 'approveStagingKnowledge' and (block_global or block_assimilation_tray):
            reason = "a nivel Global (Interruptor Maestro)" if block_global else "desde la Bandeja de Asimilación"
            raise HTTPException(status_code=403, detail=f"INYECCIÓN BLOQUEADA: El canal de inyección principal está desactivado por el Administrador {reason}.")

        if action == 'library-process' and (block_global or block_medical_library):
            reason = "a nivel Global (Interruptor Maestro)" if block_global else "manual a la Biblioteca Médica"
            raise HTTPException(status_code=403, detail=f"INYECCIÓN BLOQUEADA: El canal de inyección principal está desactivado por el Administrador {reason}.")

        if action == 'approveMemory' and (block_global or block_chat_discoveries):
            reason = "a nivel Global (Interruptor Maestro)" if block_global else "desde el Chat de debates con el Médico Adscrito"
            raise HTTPException(status_code=403, detail=f"INYECCIÓN BLOQUEADA: El canal de inyección principal está desactivado por el Administrador {reason}.")

        gemini_core.set_dynamic_config(safe_config)

        # --- HIVE-MIND RETRIEVAL (RAG GLOBAL) ---
        if action in ['continueDebate', 'runTribunal', 'expandHypothesis']:
            search_topic = payload.get("topic") or (payload.get("session") and payload.get("session", {}).get("topic")) or payload.get("userMessage")
            
            # FASE 1: PRE-PERCEPCIÓN VISUAL (Evitar ceguera vectorial)
            visual_phenotype = ""
            if search_topic and "analiza" in search_topic.lower() and payload.get("attachedFiles") and len(payload.get("attachedFiles")) > 0:
                try:
                    print(f"[Hive-Mind] Topic genérico detectado. Extrayendo Firma Visual previa...")
                    visual_phenotype = await gemini_core.extract_visual_phenotype(payload["attachedFiles"])
                    if visual_phenotype:
                        search_topic = visual_phenotype
                        print(f"[Hive-Mind] Firma Visual extraída: {search_topic[:50]}...")
                except Exception as e:
                    print(f"[Hive-Mind] Fallo en la extracción de Firma Visual. Usando texto base: {e}")

            if search_topic:
                try:
                    print(f"[Hive-Mind] Buscando memorias globales afines a la Firma Visual...")
                    mems_res = supabase_admin.from_("memoria_evolutiva_global")\
                        .select("descubrimiento, hipotesis_inicial, trampa_clinica, evidencia_correccion, aforismo_medico, embedding")\
                        .order("creado_en", desc=True)\
                        .limit(200)\
                        .execute()
                    
                    global_memories = mems_res.data or []
                    if global_memories:
                        query_vect = await gemini_core.generate_embedding(search_topic)
                        
                        scored_memories = []
                        for m in global_memories:
                            db_vec = []
                            try:
                                db_vec = json.loads(m.get("embedding")) if isinstance(m.get("embedding"), str) else m.get("embedding")
                            except Exception:
                                pass
                            
                            scored_memories.append({
                                "text": f"[Descubrimiento]: {m.get('descubrimiento')}\n[Trampa Clínica Evitada]: {m.get('trampa_clinica') or 'N/A'}\n[Aforismo Médico / Regla]: {m.get('aforismo_medico') or 'N/A'}",
                                "score": gemini_core.cosine_similarity(query_vect, db_vec)
                            })
                        
                        scored_memories.sort(key=lambda x: x["score"], reverse=True)
                        best_matches = [m for m in scored_memories if m["score"] > 0.85][:3]
                        
                        if best_matches:
                            print(f"[Hive-Mind] Recuperadas {len(best_matches)} memorias semánticas. Pasando por Filtro Maestro...")
                            best_matches = await gemini_core.filter_hive_mind_memory(payload.get("topic") or "", visual_phenotype, best_matches)

                        if best_matches:
                            print(f"[Hive-Mind] ¡Éxito! Aprobadas {len(best_matches)} memorias relevantes.")
                            hive_knowledge = f"\n\n=== MEMORIA COLECTIVA GLOBAL (HIVE-MIND) ===\nATENCIÓN RED TEAM: Se ha recuperado la siguiente Memoria Evolutiva de casos morfológicamente similares. Tu trabajo NO es copiar estos diagnósticos, sino EVALUARLOS CRÍTICAMENTE.\n\nINSTRUCCIÓN DE FILTRADO:\n1. Revisa la 'Trampa Clínica' de estos casos y asegúrate de no estar cayendo en el mismo sesgo al analizar la imagen actual.\n2. Usa los 'Aforismos Médicos' como guía, pero si la imagen actual muestra una evolución o patrón distinto (ej. evidencia de curación, marcadores ausentes), descarta la memoria evolutiva inmediatamente.\n\nMEMORIAS RECUPERADAS:\n"
                            hive_knowledge += "\n\n".join([f"--- MEMORIA {i+1} (Similitud: {m['score']*100:.1f}%) ---\n{m['text']}" for i, m in enumerate(best_matches)])
                            
                            if "globalKnowledge" in payload:
                                payload["globalKnowledge"] = (payload["globalKnowledge"] or "") + hive_knowledge
                            elif "pastContext" in payload:
                                payload["pastContext"] = (payload["pastContext"] or "") + hive_knowledge
                            else:
                                payload["globalKnowledge"] = hive_knowledge
                except Exception as e:
                    print(f"[Hive-Mind] Omisión de recuperación (nodo no disponible): {e}")

        # ====== AGENTE BIBLIOTECARIO (RAG PRE-ANÁLISIS) ======
        if action in ['runClinicalAnalysis', 'runEpidemiologyAnalysis', 'runImmunologyAnalysis', 'runDeltaAnalysis', 'runTribunal']:
            try:
                search_topic = payload.get("topic") or payload.get("text") or ""
                
                if payload.get("attachedFiles") and len(payload["attachedFiles"]) > 0:
                    print("[Bibliotecario] Analizando imagen previa para contexto enriquecido...")
                    visual_findings = await gemini_core.extract_visual_phenotype(payload["attachedFiles"], search_topic)
                    if visual_findings:
                        search_topic = f"{search_topic}. Hallazgos Visuales Pre-Análisis: {visual_findings}"

                if len(search_topic.strip()) > 10:
                    print(f"[Bibliotecario] Buscando literatura afín para: {search_topic[:50]}...")
                    query_vect = await gemini_core.generate_embedding(search_topic)
                    
                    # Llamar al RPC en Supabase
                    rpc_res = supabase_admin.rpc('match_medical_documents', {
                        'query_embedding': query_vect,
                        'match_threshold': 0.50,
                        'match_count': 4,
                        'filter_category': payload.get("searchCategory") or 'Todas'
                    }).execute()
                    
                    library_matches = rpc_res.data or []
                    if library_matches:
                        print(f"[Bibliotecario] Encontrados {len(library_matches)} documentos relevantes.")
                        library_context = "\n\n=== MEMORIA HISTÓRICA RECUPERADA (AUDITORÍA RAG) ===\nEl Agente Bibliotecario ha recuperado los siguientes expedientes clínicos del pasado que coinciden matemáticamente con el caso actual.\n\n"
                        
                        for index, match in enumerate(library_matches):
                            match_percent = match.get("similarity", 0) * 100
                            library_context += f"[CASO HISTÓRICO {index + 1}]\nTítulo: {match.get('title')}\nCategoría: {match.get('category')} | Patología: {match.get('pathology')}\nSimilitud Vectorial: {match_percent:.1f}%\nContenido: {match.get('content_text')}\n\n"
                        
                        library_context += """INSTRUCCIÓN CRÍTICA DE EXPLICABILIDAD (XAI): Dado que se ha recuperado memoria histórica, DEBES generar OBLIGATORIAMENTE un nuevo bloque en tu JSON llamado 'historicalAuditor' (si el esquema lo permite, o incluirlo al inicio de tu razonamiento). En este bloque, debes hacer una comparación cruzada:
1. anchorMatch: Indica qué caso histórico usaste como ancla principal y su porcentaje de similitud.
2. congruence: Explica explícitamente POR QUÉ se parecen clínica y morfológicamente.
3. divergence: (VACUNA ANTI-SESGO) Explica explícitamente las DIFERENCIAS entre el paciente histórico y el actual (ej. edad, inmunidad, signos ausentes) y justifica por qué el caso histórico PODRÍA NO SER el diagnóstico final del paciente actual. NUNCA asumas que son la misma enfermedad solo por el porcentaje matemático.
====================================\n"""
                        
                        payload["pastContext"] = (payload.get("pastContext") or "") + library_context
            except Exception as e:
                print(f"[Bibliotecario] Búsqueda omitida o fallida: {e}")

        result = None
        dummy_on_step_update = lambda x: None

        # SWITCH SWITCHBOARD
        if action == "getStagingKnowledge":
            staging_res = supabase_admin.from_("knowledge_staging")\
                .select("*")\
                .eq("status", "pending_review")\
                .order("created_at", desc=True)\
                .execute()
            result = staging_res.data or []

        elif action == "approveStagingKnowledge":
            item_id = payload.get("id")
            if not item_id:
                raise HTTPException(status_code=400, detail="Falta el ID del artículo a aprobar.")
            
            item_res = supabase_admin.from_("knowledge_staging").select("*").eq("id", item_id).execute()
            if item_res.data:
                item_data = item_res.data[0]
                title = item_data.get("title") or f"Estudio sobre {item_data.get('topic')}"
                
                # Insert to medical_knowledge_base
                supabase_admin.from_("medical_knowledge_base").insert({
                    "title": title,
                    "description": f"Asimilado de {item_data.get('source') or 'Europe PMC'}",
                    "category": item_data.get("macro_category") or "Medicina Interna",
                    "pathology": item_data.get("micro_pathology") or item_data.get("topic"),
                    "content_text": item_data.get("content") or "Sin contenido.",
                    "file_type": "text_only",
                    "embedding": item_data.get("embedding")
                }).execute()
                
                # Update status
                supabase_admin.from_("knowledge_staging").update({"status": "approved"}).eq("id", item_id).execute()
            result = {"success": True}

        elif action == "rejectStagingKnowledge":
            item_id = payload.get("id")
            if not item_id:
                raise HTTPException(status_code=400, detail="Falta el ID del artículo a rechazar.")
            supabase_admin.from_("knowledge_staging").delete().eq("id", item_id).execute()
            result = {"success": True}

        elif action == "auditRedundancy":
            item_id = payload.get("id")
            if not item_id:
                raise HTTPException(status_code=400, detail="Falta el ID del artículo a auditar.")
            
            new_art_res = supabase_admin.from_("knowledge_staging").select("*").eq("id", item_id).execute()
            if not new_art_res.data:
                raise HTTPException(status_code=404, detail="No se encontró el artículo en cuarentena.")
            new_art = new_art_res.data[0]

            query_db = supabase_admin.from_("medical_knowledge_base").select("title, pathology, content_text").limit(3)
            if new_art.get("macro_category"):
                query_db = query_db.eq("category", new_art["macro_category"])
            search_keyword = new_art.get("micro_pathology") or new_art.get("topic") or ""
            if search_keyword:
                query_db = query_db.ilike("pathology", f"%{search_keyword}%")
            
            existing_arts_res = query_db.execute()
            existing_arts = existing_arts_res.data or []
            
            result = await gemini_core.audit_redundancy_agent(new_art, existing_arts)

        elif action == "generateEmbedding":
            result = await gemini_core.generate_embedding(payload.get("text"))

        elif action == "findRelevantSessions":
            relevant, random_session = await gemini_core.find_relevant_sessions(
                payload.get("currentTopic"), 
                payload.get("sessions"), 
                payload.get("topK", 3), 
                payload.get("currentMode")
            )
            result = {
                "relevant": relevant,
                "random": random_session
            }

        elif action == "runTribunal":
            result = await gemini_core.run_tribunal(
                payload.get("topic"), 
                dummy_on_step_update, 
                payload.get("pastContext"), 
                payload.get("attachedFiles"), 
                payload.get("region"), 
                payload.get("city")
            )

        elif action == "runClinicalAnalysis":
            draft_report = await gemini_core.run_clinical_analysis(
                payload.get("topic"), 
                dummy_on_step_update, 
                payload.get("pastContext"), 
                payload.get("attachedFiles"), 
                payload.get("region"), 
                payload.get("city"), 
                payload.get("isDebateMode"), 
                payload.get("searchCategory"), 
                payload.get("suspectedPathology")
            )
            
            true_diagnosis = ""
            if draft_report.get("systemicIntegration") and draft_report["systemicIntegration"].get("unifiedDiagnosis"):
                true_diagnosis = draft_report["systemicIntegration"]["unifiedDiagnosis"]
            elif draft_report.get("differentialDiagnoses") and len(draft_report["differentialDiagnoses"]) > 0:
                true_diagnosis = draft_report["differentialDiagnoses"][0].get("condition")

            # Fire Shadow Librarian background task
            background_tasks.add_task(
                shadow_librarian.run_shadow_librarian,
                {
                    "suspectedPathology": payload.get("suspectedPathology") or true_diagnosis,
                    "patientContext": payload.get("pastContext") or payload.get("topic"),
                    "originalTopic": payload.get("topic"),
                    "attachedFiles": payload.get("attachedFiles")
                }
            )

            # Hive-Mind Verification Plan
            try:
                search_string = f"{true_diagnosis} {payload.get('topic') or ''}".strip()
                query_vect = await gemini_core.generate_embedding(search_string)
                
                mems_res = supabase_admin.from_("memoria_evolutiva_global")\
                    .select("descubrimiento, trampa_clinica, aforismo_medico, embedding")\
                    .order("creado_en", desc=True)\
                    .limit(100)\
                    .execute()
                
                mems = mems_res.data or []
                if mems:
                    scored_mems = []
                    for m in mems:
                        db_vec = []
                        try:
                            db_vec = json.loads(m.get("embedding")) if isinstance(m.get("embedding"), str) else m.get("embedding")
                        except Exception:
                            pass
                        
                        scored_mems.append({
                            "text": f"**Trampa Clínica Histórica:** {m.get('trampa_clinica') or 'N/A'}\n\n**Regla de Oro/Aforismo:** {m.get('aforismo_medico') or m.get('descubrimiento')}",
                            "score": gemini_core.cosine_similarity(query_vect, db_vec)
                        })
                    
                    scored_mems.sort(key=lambda x: x["score"], reverse=True)
                    best_matches = [m for m in scored_mems if m["score"] > 0.86][:2]
                    
                    if best_matches:
                        visual_phenotype = ""
                        if draft_report.get("radiologicalSigns"):
                            signs = draft_report.get("radiologicalSigns")
                            if isinstance(signs, list):
                                visual_phenotype = ", ".join([s.get("sign") for s in signs if s.get("present") and s.get("sign")])
                                
                        print(f"[Auditor Maestro] Evaluando {len(best_matches)} memorias contra el diagnóstico: {true_diagnosis}...")
                        best_matches = await gemini_core.filter_hive_mind_memory(search_string, visual_phenotype, best_matches)
                        
                    if best_matches:
                        memory_text = "\n\n---\n\n".join([m["text"] for m in best_matches])
                        auditor_stamp = f"\n\n🛡️ **AUDITORÍA MAESTRA (HIVE-MIND) APROBADA**:\nHe cruzado este diagnóstico final con nuestra base de datos neuronal y he encontrado una correlación perfecta. Lección aplicable a este paciente:\n\n{memory_text}"
                        
                        if draft_report.get("boardSummary"):
                            draft_report["boardSummary"] += auditor_stamp
                        else:
                            draft_report["boardSummary"] = auditor_stamp
            except Exception as e:
                print(f"[Auditor Maestro] Omisión de búsqueda de memoria final: {e}")

            result = draft_report

        elif action == "amendClinicalReport":
            result = await gemini_core.amend_clinical_report(payload.get("oldReport"), payload.get("cognitiveAutopsy"))

        elif action == "runEpidemiologyAnalysis":
            result = await gemini_core.run_epidemiology_analysis(
                payload.get("topic"), 
                dummy_on_step_update, 
                payload.get("pastContext"), 
                payload.get("attachedFiles"), 
                payload.get("region"), 
                payload.get("city")
            )

        elif action == "runImmunologyAnalysis":
            result = await gemini_core.run_immunology_analysis(
                payload.get("topic"), 
                dummy_on_step_update, 
                payload.get("pastContext"), 
                payload.get("attachedFiles"), 
                payload.get("region"), 
                payload.get("city")
            )

        elif action == "runDeltaAnalysis":
            result = await gemini_core.run_delta_analysis(payload.get("patient"), payload.get("reports"), dummy_on_step_update)

        elif action == "library-process":
            # Check admin token
            admin_token = get_token_from_request(request, "biologic_admin_token")
            if not admin_token:
                raise HTTPException(status_code=401, detail="Acceso denegado: Token de Administrador faltante.")
            try:
                decoded = jwt.decode(admin_token, JWT_SECRET, algorithms=["HS256"])
                if decoded.get("role") != "admin":
                    raise Exception()
            except Exception:
                raise HTTPException(status_code=401, detail="Acceso denegado: Token de Administrador inválido o expirado.")

            title = payload.get("title")
            description = payload.get("description")
            category = payload.get("category")
            pathology = payload.get("pathology")
            file_url = payload.get("fileUrl")
            file_type = payload.get("fileType")
            raw_text = payload.get("rawText")

            if not title or not category or not pathology:
                raise HTTPException(status_code=400, detail="Faltan campos obligatorios")
                
            content_to_embed = f"[Título del Caso]: {title}. [Categoría]: {category}. [Patología Central]: {pathology}. [Descripción/Historia Clínica]: {raw_text or description or ''}"
            
            final_content_to_embed = content_to_embed
            uploaded_urls = []

            if payload.get("attachedFiles") and len(payload.get("attachedFiles")) > 0:
                print(f"[Bibliotecario] Procesando {len(payload['attachedFiles'])} archivos adjuntos...")
                
                visual_phenotype = await gemini_core.extract_visual_phenotype(payload["attachedFiles"], final_content_to_embed)
                if visual_phenotype:
                    print(f"[Bibliotecario] Fenotipo Visual extraído: {visual_phenotype}")
                    final_content_to_embed += f"\n\n[HALLAZGOS VISUALES / LABORATORIO (OCR)]\n{visual_phenotype}"

                for f in payload["attachedFiles"]:
                    import base64
                    buffer = base64.b64decode(f["data"])
                    
                    clean_file_name = re.sub(r'[^a-zA-Z0-9.-]', '_', f["name"])
                    
                    import unicodedata
                    clean_category = unicodedata.normalize('NFKD', category).encode('ASCII', 'ignore').decode('ASCII')
                    clean_category = re.sub(r'[^a-z0-9]', '', clean_category.lower())
                    
                    import time
                    file_path = f"{clean_category}/{int(time.time() * 1000)}_{clean_file_name}"
                    
                    try:
                        supabase_admin.storage.from_("medical_files").upload(
                            path=file_path,
                            file=buffer,
                            file_options={"content_type": f.get("type") or "application/pdf", "upsert": "true"}
                        )
                    except Exception as upload_err:
                        print(f"Error subiendo archivo {f['name']}: {upload_err}")
                        raise HTTPException(status_code=500, detail=f"No se pudo subir el archivo {f['name']} al servidor.")

                    url_res = supabase_admin.storage.from_("medical_files").get_public_url(file_path)
                    if isinstance(url_res, str):
                        public_url = url_res
                    elif hasattr(url_res, "public_url"):
                        public_url = url_res.public_url
                    else:
                        public_url = str(url_res)
                    uploaded_urls.append(public_url)

            if file_url:
                uploaded_urls.append(file_url)

            final_file_urls_str = ",".join(uploaded_urls) if uploaded_urls else None
            
            embedding_values = await gemini_core.generate_embedding(final_content_to_embed)
            
            supabase_admin.from_("medical_knowledge_base").insert({
                "title": title,
                "description": description,
                "category": category,
                "pathology": pathology,
                "file_url": final_file_urls_str,
                "file_type": 'multiple_files' if (payload.get("attachedFiles") and len(payload.get("attachedFiles")) > 0) else ('external_link' if file_url else 'text_only'),
                "content_text": final_content_to_embed,
                "embedding": embedding_values
            }).execute()
            
            result = {"success": True, "message": "Documento indexado y vectorizado correctamente."}

        elif action == "continueDebate":
            result = await gemini_core.continue_debate(
                payload.get("session"), 
                payload.get("userMessage"), 
                payload.get("globalKnowledge"), 
                payload.get("region"), 
                payload.get("city")
            )

        elif action == "expandHypothesis":
            result = await gemini_core.expand_hypothesis(
                payload.get("hypothesis"), 
                payload.get("action"), 
                payload.get("globalKnowledge"), 
                payload.get("session"), 
                payload.get("region"), 
                payload.get("city")
            )

        elif action == "approveMemory":
            text_to_embed = payload.get("cognitiveAutopsy", {}).get("aforismo_medico") if payload.get("isAutopsy") else payload.get("newDiscovery", {}).get("hallazgo")
            embedding_vector = await gemini_core.generate_embedding(text_to_embed)
            caso_origen = payload.get("topic")
            
            payload_db = {
                "caso_origen": caso_origen,
                "embedding": f"[{','.join(map(str, embedding_vector))}]",
                "puntuacion_humana": payload.get("rating", 5),
                "nota_humana": payload.get("note", '')
            }

            if payload.get("isAutopsy"):
                payload_db["etiqueta_diagnostica"] = payload.get("cognitiveAutopsy", {}).get("etiqueta_diagnostica")
                payload_db["descubrimiento"] = "AUTOPSIA COGNITIVA: " + payload.get("cognitiveAutopsy", {}).get("verdad_revelada")
                payload_db["hipotesis_inicial"] = payload.get("cognitiveAutopsy", {}).get("hipotesis_inicial")
                payload_db["trampa_clinica"] = payload.get("cognitiveAutopsy", {}).get("trampa_clinica")
                payload_db["evidencia_correccion"] = payload.get("cognitiveAutopsy", {}).get("evidencia_correccion")
                payload_db["aforismo_medico"] = payload.get("cognitiveAutopsy", {}).get("aforismo_medico")
            else:
                payload_db["etiqueta_diagnostica"] = payload.get("newDiscovery", {}).get("etiqueta_diagnostica")
                payload_db["descubrimiento"] = payload.get("newDiscovery", {}).get("hallazgo")

            existing_mem = supabase_admin.from_("memoria_evolutiva_global")\
                .select("id")\
                .eq("caso_origen", caso_origen)\
                .eq("descubrimiento", payload_db["descubrimiento"])\
                .limit(1)\
                .execute()

            was_duplicate = False
            if existing_mem.data and len(existing_mem.data) > 0:
                was_duplicate = True
                print("[Hive-Mind] Memoria omitida. Ya existía en la base de datos.")
            else:
                supabase_admin.from_("memoria_evolutiva_global").insert(payload_db).execute()
                
            result = {"success": True, "wasDuplicate": was_duplicate}

        elif action == "transcribeAudio":
            result = await gemini_core.transcribe_audio(payload.get("audioData"), payload.get("mimeType"))

        elif action == "formatClinicalText":
            result = await gemini_core.format_clinical_text(payload.get("rawText"))

        else:
            raise HTTPException(status_code=400, detail=f"La acción '{action}' no existe o no está protegida.")

        # --- CÁLCULO ESTRICTO DE COSTOS EN BACKEND ---
        try:
            input_words = len(json.dumps(payload).split())
            output_words = len(json.dumps(result).split()) if result else 0
            
            input_tokens = int(input_words * 1.33)
            output_tokens = int(output_words * 1.33)

            estimated_cost = (input_tokens * 0.00000015) + (output_tokens * 0.00000060)
            
            supabase_admin.from_('api_usage_logs').insert({
                "action": action,
                "model": safe_config.get("dictationModel") or "gemini-2.5-flash" if action == "transcribeAudio" else safe_config.get("activeModel") or "gemini-3.1-pro-preview",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "estimated_cost_usd": estimated_cost,
                "access_code": access_code
            }).execute()
        except Exception as e:
            print(f"[Billing] Error al registrar consumo en Supabase: {e}")

        return {"success": True, "data": result}
    except HTTPException as http_ex:
        raise http_ex
    except Exception as error:
        print(f"[Error Vercel] Acción {action} falló: {error}")
        raise HTTPException(status_code=500, detail=str(error) or "Fallo interno en el servidor seguro.")


@router.post("/analyze-patient")
async def analyze_patient(req_data: AnalyzePatientRequest, user: dict = Depends(get_current_user)):
    paciente_dni = req_data.paciente_dni
    if not paciente_dni:
        raise HTTPException(status_code=400, detail="Parámetro crítico faltante: paciente_dni")

    try:
        print(f"[Gran Tribunal] Iniciando barrido forense para el DNI: {paciente_dni}")

        # 1. RECOLECCIÓN ASÍNCRONA
        records_res = supabase_admin.from_("Registros_Clinicos")\
            .select("*")\
            .eq("paciente_dni", paciente_dni)\
            .order("fecha_registro", desc=False)\
            .execute()
        
        records = records_res.data or []
        if not records:
            return {"success": False, "message": "No existen registros médicos, audios ingestados ni laboratorios para este paciente todavía."}

        # 2. EMPAQUETADO
        historial_unificado = ""
        for index, r in enumerate(records):
            fecha = r.get("fecha_registro")
            origen = r.get("origen")
            tipo = r.get("tipo")
            contenido_json = r.get("contenido_json")
            historial_unificado += f"\n\n--- REGISTRO #{index + 1} | ORIGEN: {origen} | TIPO: {tipo} | FECHA: {fecha} ---"
            historial_unificado += f"\nCONTENIDO JSON ESTRUCTURADO:\n{json.dumps(contenido_json, indent=2, ensure_ascii=False)}"

        # 3. EL GRAN PROMPT CLINICO
        system_prompt = f"""
Eres la MATRIZ DE DEBATE CLÍNICO de más alto nivel (El Tribunal).
Tu objetivo es leer un historial fragmentado proveniente de múltiples orígenes asíncronos (ej. una entrevista de un médico de triaje, fotos de un radiólogo, pdfs de un laboratorio) que han sido unificados hoy para este paciente.

INSTRUCCIONES CLÍNICAS:
1. REGLA DE CONGRUENCIA FÍSICA Y EVOLUTIVA: Analiza cómo encaja la transcripción del audio del doctor general de hace días, con la radiografía subida horas después. ¿Hay un patrón de deterioro?
2. BÚSQUEDA DE FACTORES CONFUSORES: Cruza la 'adherencia a tratamientos' descrita en los audios con los resultados matemáticos de los laboratorios. Si hay una contradicción, márcala como Bandera Roja.
3. CONTEXTO SOCIO-AMBIENTAL (REGLA DEL ECOSISTEMA): Integra drásticamente los factores ambientales capturados por el Escriba Cognitivo (viajes, estrés, mascotas) con las hipótesis del médico. 
4. VETO AL CIERRE PREMATURO: Si el médico de triaje sugirió un diagnóstico en su "rastro cognitivo" en los audios, tú debes jugar al abogado del diablo. Intenta refutar agresivamente la hipótesis inicial del médico basándote en lagunas de información.
5. SÍNTESIS RESOLUTIVA: Provee un diagnóstico diferencial priorizado y un plan de acción estricto de pasos siguientes.

=== HISTORIAL UNIFICADO DEL PACIENTE (DNI: {paciente_dni}) ===
{historial_unificado}
"""

        # 4. INVOCACIÓN DE LA LLAMA INTELIGENTE CON ROTACIÓN DE KEYS
        ai = get_random_ai_client()
        
        schema_dict = {
            "type": "OBJECT",
            "properties": {
                "analisis_evolutivo": {"type": "STRING", "description": "Cómo ha cambiado el contexto asíncrono cruzando todos los registros."},
                "refutaciones_al_medico": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Fallos o sesgos detectados en el razonamiento original capturado."},
                "diagnosticos_diferenciales": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "patologia": {"type": "STRING"},
                            "probabilidad": {"type": "STRING", "enum": ["ALTA", "MEDIA", "BAJA"]},
                            "justificacion_cruzada": {"type": "STRING", "description": "Justificación cruzando el audio + lab/imagenes."}
                        },
                        "required": ["patologia", "probabilidad", "justificacion_cruzada"]
                    }
                },
                "plan_de_accion": {"type": "ARRAY", "items": {"type": "STRING"}},
                "banderas_rojas_activas": {"type": "ARRAY", "items": {"type": "STRING"}}
            },
            "required": ["analisis_evolutivo", "diagnosticos_diferenciales", "plan_de_accion"]
        }

        if isinstance(ai, OpenRouterWrapper):
            response = await ai.models.generate_content(
                model=FREE_MODEL_NAME,
                contents=system_prompt,
                config={"temperature": 0.2}
            )
        else:
            response = ai.models.generate_content(
                model=FREE_MODEL_NAME,
                contents=system_prompt,
                config=types.GenerateContentConfig(
                    safety_settings=medical_safety_settings,
                    response_mime_type="application/json",
                    response_schema=schema_dict,
                    temperature=0.2
                )
            )

        final_analysis = json.loads(clean_json(response.text or "{}"))

        return {
            "success": True,
            "paciente_dni": paciente_dni,
            "cantidad_registros_evaluados": len(records),
            "veredicto_tribunal": final_analysis
        }
    except Exception as e:
        print(f"Fallo crítico en el Tribunal Serverless: {e}")
        raise HTTPException(status_code=500, detail=f"Error catastrófico en el Tribunal: {e}")


@router.post("/ingest-audio")
async def ingest_audio(req_data: IngestAudioRequest, user: dict = Depends(get_current_user)):
    paciente_dni = req_data.paciente_dni
    nombre_medico = req_data.nombre_medico or "Desconocido"
    transcripcion_audio = req_data.transcripcion_audio
    contexto_adicional = req_data.contexto_adicional

    if not paciente_dni or not transcripcion_audio:
        raise HTTPException(status_code=400, detail="Faltan parámetros obligatorios: paciente_dni y transcripcion_audio son imperativos.")

    try:
        print(f"[Escriba Clínico] Ingestando audio para DNI: {paciente_dni}")

        prompt_text = f"""
Eres el "Escriba Clínico Cognitivo", una IA entrenada para analizar transcripciones crudas de consultas médico-paciente.
Tu objetivo NO es solo extraer síntomas de manual, sino diseccionar el ecosistema completo del paciente y el razonamiento del médico.

INSTRUCCIONES CRÍTICAS:
1. FILTRO DE RUIDO Y SEÑAL: Ignora saludos y charlas sociales vacías. Sin embargo, sé hiper-vigilante a comentarios casuales del paciente sobre su entorno (mascotas, viajes espaciales de hace meses, cambios de trabajo, dieta, exposición a químicos, problemas familiares).
2. LA CRONOLOGÍA (EL EJE DEL TIEMPO): Un síntoma sin tiempo no sirve. Extrae la línea temporal exacta del deterioro. ¿Qué pasó primero? ¿Qué se sumó después?
3. EL RASTRO COGNITIVO DEL DOCTOR: Analiza las preguntas que hizo el médico. Infiere qué diagnóstico differential estaba barajando el médico en su mente basándote en lo que preguntó. 
4. PERCEPCIÓN DE BANDERAS ROJAS OCULTAS: Detecta contradicciones entre lo que el paciente dice y lo que el médico asume, o detalles que el médico ignoró (ej. el paciente mencionó sangre en la orina y el médico cambió de tema).
5. ANÁLISIS DE BRECHAS (FALTANTES): ¿Qué información OBLIGATORIA según las guías clínicas no se preguntó? (Ej. Si es una mujer en edad fértil con dolor abdominal, ¿se preguntó por la fecha de última regla?).

=== TRANSCRIPCIÓN A ANALIZAR ===
Paciente DNI: {paciente_dni}
Médico a cargo: {nombre_medico}
Texto de la consulta: "{transcripcion_audio}"
{f"Contexto extra aportado: {contexto_adicional}" if contexto_adicional else ""}
"""

        ai = get_random_ai_client()
        
        schema_dict = {
            "type": "OBJECT",
            "properties": {
                "demografia_inferida": {"type": "STRING"},
                "cronologia_enfermedad": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "momento": {"type": "STRING"},
                            "evento": {"type": "STRING"}
                        },
                        "required": ["momento", "evento"]
                    }
                },
                "sintomas_signos_explicitos": {"type": "ARRAY", "items": {"type": "STRING"}},
                "claves_contextuales_y_ambientales": {"type": "ARRAY", "items": {"type": "STRING"}},
                "adherencia_tratamientos_previos": {"type": "ARRAY", "items": {"type": "STRING"}},
                "rastro_cognitivo_medico": {"type": "STRING"},
                "alertas_y_contradicciones": {"type": "ARRAY", "items": {"type": "STRING"}},
                "brechas_de_informacion": {"type": "ARRAY", "items": {"type": "STRING"}}
            },
            "required": [
                "demografia_inferida", 
                "cronologia_enfermedad", 
                "sintomas_signos_explicitos",
                "rastro_cognitivo_medico",
                "brechas_de_informacion"
            ]
        }

        if isinstance(ai, OpenRouterWrapper):
            response = await ai.models.generate_content(
                model=FREE_MODEL_NAME,
                contents=prompt_text,
                config={"temperature": 0.2}
            )
        else:
            response = ai.models.generate_content(
                model=FREE_MODEL_NAME,
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    safety_settings=medical_safety_settings,
                    response_mime_type="application/json",
                    response_schema=schema_dict,
                    temperature=0.2
                )
            )

        analysis_data = json.loads(clean_json(response.text or "{}"))

        # Save to database
        try:
            supabase_admin.from_("Registros_Clinicos").insert({
                "paciente_dni": paciente_dni,
                "tipo": "TRANSCRIPCION_AUDIO_ANALIZADA",
                "contenido_json": analysis_data,
                "origen": nombre_medico,
                "usuario_id": user.get("userId")
            }).execute()
        except Exception as db_ex:
            print(f"Excepción en la conexión Supabase al guardar audio ingestido: {db_ex}")

        return {
            "success": True,
            "message": "Audio procesado y asimilado con éxito para el paciente.",
            "paciente_dni": paciente_dni,
            "data": analysis_data
        }
    except Exception as e:
        print(f"Error en Ingesta de Audio: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor Vercel: {e}")


@router.post("/b2b-endpoint")
async def b2b_endpoint(
    req_data: B2BRequest, 
    request: Request,
    background_tasks: BackgroundTasks
):
    start_time = datetime.datetime.utcnow()
    
    # 1. Extraer API Key del Header (Formato: Bearer sk_biologic_...)
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized: Missing or invalid Bearer token.")
        
    raw_key = auth_header.split(" ")[1]
    hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    try:
        # 2. Validar en Supabase
        key_res = supabase_admin.from_("b2b_api_keys")\
            .select("*")\
            .eq("hashed_key", hashed_key)\
            .execute()
            
        if not key_res.data:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid API Key.")
            
        key_record = key_res.data[0]

        if key_record.get("status") != "Activa":
            raise HTTPException(status_code=403, detail=f"Forbidden: API Key is {key_record.get('status')}.")

        if key_record.get("credits_used", 0) >= key_record.get("credits_total", 0):
            raise HTTPException(status_code=402, detail="Payment Required: Credit limit reached.")

        patient_data = req_data.patientData
        mode = req_data.mode or "clinical"
        past_context = req_data.pastContext or ""
        attached_files = req_data.attachedFiles or []
        region = req_data.region or "Latinoamérica"
        city = req_data.city or "Global"
        suspected_pathology = req_data.suspectedPathology or ""

        if not patient_data:
            raise HTTPException(status_code=400, detail="Bad Request: 'patientData' is required and must be a string.")

        processed_files = []
        for f in attached_files:
            if not f.get("name") or not (f.get("type") or f.get("mimeType")) or not f.get("data"):
                raise HTTPException(status_code=400, detail="Bad Request: Each file in 'attachedFiles' must have 'name', 'type' (or 'mimeType'), and 'data' (base64 string).")
            processed_files.append({
                "name": f.get("name"),
                "mimeType": f.get("type") or f.get("mimeType"),
                "data": f.get("data")
            })

        # Cargar configuración global
        safe_config = {}
        try:
            config_res = supabase_admin.from_("admin_system_config").select("*").eq("id", "global_config").execute()
            if config_res.data:
                config_data = config_res.data[0]
                if config_data.get("kill_switch") is True:
                    raise HTTPException(status_code=503, detail="Service Unavailable: Global Kill Switch is active.")
                safe_config = {
                    "apiKeys": config_data.get("api_keys") or [],
                    "activeModel": config_data.get("active_model"),
                    "dictationModel": config_data.get("dictation_model"),
                    "apiProvider": config_data.get("api_provider")
                }
        except HTTPException as he:
            raise he
        except Exception:
            pass

        gemini_core.set_dynamic_config(safe_config)

        # 3. Ejecutar Análisis
        dummy_on_step_update = lambda x: None
        if mode == "clinical":
            result = await gemini_core.run_clinical_analysis(
                patient_data,
                dummy_on_step_update,
                past_context,
                processed_files,
                region,
                city,
                True, # isDebateMode = True for B2B
                None, # searchCategory
                suspected_pathology
            )

            # Shadow Librarian Background Task
            true_diagnosis = ""
            if result.get("systemicIntegration") and result["systemicIntegration"].get("unifiedDiagnosis"):
                true_diagnosis = result["systemicIntegration"]["unifiedDiagnosis"]
            elif result.get("differentialDiagnoses") and len(result["differentialDiagnoses"]) > 0:
                true_diagnosis = result["differentialDiagnoses"][0].get("condition")

            background_tasks.add_task(
                shadow_librarian.run_shadow_librarian,
                {
                    "suspectedPathology": suspected_pathology or true_diagnosis,
                    "patientContext": past_context or patient_data,
                    "attachedFiles": processed_files
                }
            )
        else:
            raise HTTPException(status_code=400, detail="Bad Request: Only 'clinical' mode is supported in the current B2B API.")

        execution_time_ms = int((datetime.datetime.utcnow() - start_time).total_seconds() * 1000)

        # 4. Cobrar 1 crédito y registrar consumo
        new_credits_used = key_record.get("credits_used", 0) + 1
        supabase_admin.from_("b2b_api_keys").update({
            "credits_used": new_credits_used,
            "last_used_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", key_record.get("id")).execute()

        client_ip = request.headers.get("x-forwarded-for") or request.client.host or "unknown"

        supabase_admin.from_("b2b_usage_logs").insert({
            "key_id": key_record.get("id"),
            "request_ip": client_ip,
            "topic": patient_data[:100],
            "response_time_ms": execution_time_ms,
            "status_code": 200
        }).execute()

        return {
            "status": "success",
            "executionTimeMs": execution_time_ms,
            "remainingCredits": key_record.get("credits_total", 0) - new_credits_used,
            "data": result
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"[B2B API Error] {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error during processing.")
