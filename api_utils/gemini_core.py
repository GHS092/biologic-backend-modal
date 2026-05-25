import os
import re
import json
import random
import asyncio
import httpx
from typing import List, Dict, Any, Optional, Tuple
from google import genai
from google.genai import types

# Helper to download and base64-encode files (especially videos from Supabase Storage) safely
async def resolve_attached_file_data(
    file: Dict[str, Any],
    on_step_update: Optional[Any] = None,
    idx: int = 0
) -> Optional[Dict[str, Any]]:
    import urllib.request
    import base64
    
    file_name = file.get("name", "").lower()
    video_url = file.get("videoUrl") or file.get("video_url")
    
    # Smart Mime-Type inference to avoid fallback to application/octet-stream
    mime_type = file.get("mimeType") or file.get("mime_type") or file.get("type") or ""
    if not mime_type or mime_type == "application/octet-stream":
        if file_name.endswith(".mp4") or file_name.endswith(".mov") or file_name.endswith(".avi") or file_name.endswith(".webm") or video_url:
            mime_type = "video/mp4"
        elif file_name.endswith(".png"):
            mime_type = "image/png"
        elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif file_name.endswith(".pdf"):
            mime_type = "application/pdf"
        else:
            mime_type = "application/octet-stream"

    if video_url:
        try:
            if on_step_update:
                on_step_update({
                    "id": f"dl-video-{idx}-{hash(video_url)}",
                    "type": "analysis",
                    "title": f"Cargando Cine-loop: {file.get('name', 'video')}",
                    "content": f"Transfiriendo barrido o cine-loop dinámico desde Supabase Storage a memoria serverless...",
                    "confidence": 0.95,
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                })
            print(f"[Backend File Resolver] Descargando video desde URL: {video_url} | Mime: {mime_type}")
            req = urllib.request.Request(video_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as response:
                video_bytes = response.read()
            base64_data = base64.b64encode(video_bytes).decode('utf-8')
            print(f"[Backend File Resolver] Video descargado con éxito: {len(video_bytes)} bytes | Mime asignado: {mime_type}")
            return {
                "inline_data": {
                    "data": base64_data,
                    "mime_type": mime_type
                }
            }
        except Exception as dl_err:
            print(f"[Backend Download Error] Fallo al descargar video {video_url}: {dl_err}")
            return None
    elif file.get("data"):
        raw_data = file["data"]
        print(f"[Backend File Resolver] Cargando archivo local: {file.get('name')} | Mime: {mime_type} | Size: {len(raw_data)} chars")
        return {
            "inline_data": {
                "data": raw_data,
                "mime_type": mime_type
            }
        }
    return None

from .video_reasoning import inject_video_scanning_protocol


# Configurations injected at runtime
current_admin_config: Dict[str, Any] = {}

def set_dynamic_config(config: Dict[str, Any]):
    global current_admin_config
    current_admin_config = config or {}

# OpenRouter Wrapper for Python
class OpenRouterWrapper:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.models = self.Models(self)

    class Models:
        def __init__(self, wrapper):
            self.wrapper = wrapper

        async def generate_content(self, model: str, contents: Any, config: Any = None) -> Any:
            messages = []
            
            # Extract content text
            if isinstance(contents, str):
                messages = [{"role": "user", "content": contents}]
            elif isinstance(contents, dict):
                parts = contents.get("parts", [])
                text_content = ""
                if isinstance(parts, list):
                    text_content = "\n".join([p.get("text", "") if isinstance(p, dict) else str(p) for p in parts])
                else:
                    text_content = str(parts)
                role = "assistant" if contents.get("role") == "model" else contents.get("role", "user")
                messages = [{"role": role, "content": text_content}]
            elif isinstance(contents, list):
                for c in contents:
                    if isinstance(c, dict):
                        role = "assistant" if c.get("role") == "model" else c.get("role", "user")
                        parts = c.get("parts", [])
                        text_content = ""
                        if isinstance(parts, list):
                            text_content = "\n".join([p.get("text", "") if isinstance(p, dict) else str(p) for p in parts if "text" in p])
                        else:
                            text_content = str(parts)
                        messages.append({"role": role, "content": text_content})
                    elif isinstance(c, str):
                        messages.append({"role": "user", "content": c})
            else:
                messages = [{"role": "user", "content": str(contents)}]

            or_model = model
            if "/" not in or_model:
                or_model = f"google/{or_model}"

            print(f"[OpenRouter] Proxying call to model: {or_model}")

            headers = {
                "Authorization": f"Bearer {self.wrapper.api_key}",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "BioLogic",
                "Content-Type": "application/json"
            }

            payload = {
                "model": or_model,
                "messages": messages
            }
            
            if config:
                if hasattr(config, "temperature") and config.temperature is not None:
                    payload["temperature"] = config.temperature
                elif isinstance(config, dict) and "temperature" in config:
                    payload["temperature"] = config["temperature"]

            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)

            if res.status_code != 200:
                raise Exception(f"OpenRouter Error: {res.status_code} {res.text}")

            data = res.json()
            content = data["choices"][0]["message"]["content"]

            class ResponseObj:
                def __init__(self, text):
                    self.text = text

            return ResponseObj(content)

def get_random_ai_client(force_google: bool = False) -> Any:
    global current_admin_config
    keys = []

    api_keys = current_admin_config.get("apiKeys") or current_admin_config.get("api_keys")
    if api_keys and len(api_keys) > 0:
        keys = api_keys
    else:
        keys_str = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
        if not keys_str:
            raise Exception("No hay API Keys registradas en la Bóveda Segura ni en las Variables de Vercel/Modal.")
        keys = [k.strip() for k in keys_str.split(",") if k.strip()]

    if not keys:
        raise Exception("No hay API Keys registradas en la Bóveda Segura ni en las Variables de Vercel/Modal.")

    random_key = random.choice(keys)
    api_provider = current_admin_config.get("apiProvider") or current_admin_config.get("api_provider")

    if not force_google and api_provider == "openrouter":
        return OpenRouterWrapper(random_key)

    # Note: official google-genai package uses genai.Client
    return genai.Client(api_key=random_key)

def get_active_model() -> str:
    global current_admin_config
    active = current_admin_config.get("activeModel") or current_admin_config.get("active_model")
    if active:
        return active
    return "gemini-2.5-flash"  # fallback

FREE_MODEL_NAME = "gemini-2.5-flash"

# Medical safety settings configured as types.SafetySetting list
medical_safety_settings = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_NONE,
    )
]

def clean_json(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    elif cleaned.startswith("```"):
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()

async def with_retry_and_timeout(
    promise_factory,
    ms: int,
    step_name: str,
    max_retries: int = 3,
    force_google: bool = False
) -> Any:
    last_error = None
    actual_seconds = max(ms / 1000.0, 120.0) # 120 seconds minimum

    for attempt in range(max_retries + 1):
        try:
            ai_client = get_random_ai_client(force_google)
            # Run the promise_factory under asyncio wait_for
            result = await asyncio.wait_for(promise_factory(ai_client), timeout=actual_seconds)
            return result
        except asyncio.TimeoutError:
            last_error = Exception(f"El agente '{step_name}' tardó demasiado en responder ({actual_seconds}s). El servidor de IA podría estar sobrecargado.")
            print(f"[{step_name}] Intento {attempt + 1} fallido por Timeout. Reintentando en 1s...")
            await asyncio.sleep(1.0)
        except Exception as error:
            last_error = error
            if attempt == max_retries:
                break
            print(f"[{step_name}] Intento {attempt + 1} fallido: {error}. Reintentando en 1s...")
            await asyncio.sleep(1.0)

    err_str = str(last_error)
    if any(kw in err_str for kw in ["503", "UNAVAILABLE", "high demand", "overloaded"]):
        raise Exception("El sistema médico BioLogic se encuentra procesando múltiples solicitudes clínicas de alta complejidad en este momento. Por favor, vuelve a intentarlo en unos segundos.")

    raise last_error

# Concurrently gather literature context
async def gather_literature_context(
    topic: str,
    on_step_update,
    mode_prefix: str,
    attached_files: Optional[List[Dict[str, Any]]] = None
) -> str:
    from .literature import search_europe_pmc, get_full_text_sections
    try:
        on_step_update({
            "id": f"{mode_prefix}-research-plan-{int(asyncio.get_event_loop().time() * 1000)}",
            "type": "analysis",
            "title": "Planificando Búsqueda",
            "content": f"Formulando consultas para Europe PMC sobre: \"{topic}\"...",
            "confidence": 0.9,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        })

        search_prompt = f"You are a medical researcher. The user's initial query is: \"{topic}\".\n"
        if attached_files and len(attached_files) > 0:
            search_prompt += "I have attached clinical images/documents. PLEASE ANALYZE THESE IMAGES FIRST to understand the exact clinical finding.\n"
        search_prompt += "Based on the user's query and the visual analysis of the images (if present), generate up to 3 highly specific search queries in English to find the most relevant recent medical literature to diagnose or treat this condition.\n"
        search_prompt += "Return ONLY a JSON array of strings. Example: [\"ring enhancing lesion isointense DWI\", \"cerebral mass normal ADC\"]"

        parts = [{"text": search_prompt}]
        if attached_files and len(attached_files) > 0:
            for file in attached_files:
                mime = file.get("mimeType", "") or file.get("type", "") or ""
                url = file.get("videoUrl") or file.get("video_url") or ""
                if mime.startswith("video/") or url:
                    continue # Skip heavy videos in Europe PMC query planner to avoid overhead/crash
                if file.get("data"):
                    parts.append({
                        "inline_data": {
                            "data": file["data"],
                            "mime_type": file["mimeType"]
                        }
                    })

        async def run_plan(ai):
            # In official SDK we use client.aio for async
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=parts,
                    config={"temperature": 0.2}
                )
            else:
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=parts,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json"
                    )
                )

        plan_response = await with_retry_and_timeout(run_plan, 15000, "Planificador de Búsqueda", 1)
        queries = json.loads(clean_json(plan_response.text or "[]"))

        if not isinstance(queries, list) or len(queries) == 0:
            return ""

        on_step_update({
            "id": f"{mode_prefix}-epmc-{int(asyncio.get_event_loop().time() * 1000)}",
            "type": "analysis",
            "title": "Extrayendo Textos Completos",
            "content": f"Consultando Europe PMC para: {', '.join(queries)}...",
            "confidence": 0.95,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        })

        # Process the first 2 queries
        unique_results = []
        seen_ids = set()
        for q in queries[:2]:
            res = await search_europe_pmc(q, 2)
            for r in res:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    unique_results.append(r)

        if unique_results:
            enriched_results = list(unique_results)
            # Try to fetch full text for the first article if OA
            if enriched_results[0] and enriched_results[0].get("isOpenAccess"):
                full_text = await get_full_text_sections(enriched_results[0]["id"])
                if full_text.get("results") or full_text.get("conclusion"):
                    enriched_results[0]["fullTextResults"] = full_text["results"]
                    enriched_results[0]["fullTextConclusion"] = full_text["conclusion"]

            return f"\n=== EVIDENCIA RECIENTE (EUROPE PMC FULL-TEXT) ===\nUtiliza esta evidencia para anclar tu respuesta. Cita usando [PMID/PMCID: <id>].\n{json.dumps(enriched_results[:4])}\n"
    except Exception as e:
        print(f"Error gathering Europe PMC context: {e}")
    return ""

async def extract_visual_phenotype(attached_files: List[Dict[str, Any]], context_topic: str = "") -> str:
    if not attached_files:
        return ""
    try:
        instruction = (
            "INSTRUCCIÓN CRÍTICA (PRE-PERCEPCIÓN): Eres un radiólogo/patólogo experto. Tu tarea es extraer la \"Firma Visual\" y médica de las imágenes adjuntas. \n\n"
            f"CONTEXTO DEL MÉDICO: \"{context_topic}\"\n\n"
            "REGLA DE AGNOSIA FORZADA: Tienes ESTRICTAMENTE PROHIBIDO usar nombres de enfermedades o patologías finales (ej. \"Hernia Diafragmática\", \"Neumonía\", \"Tumor\") en tu descripción. Debes comportarte como un espectrómetro fotográfico ciego. Describe puramente la GEOMETRÍA, DENSIDAD y TOPOGRAFÍA (ej. \"Múltiples densidades tubulares radiolúcidas en hemitórax izquierdo con desplazamiento mediastínico contralateral\" o \"Opacidad en forma de cuña que eleva los lóbulos del timo\").\n\n"
            "Basándote ESTRICTAMENTE en este contexto y bajo la regla de Agnosia Forzada, describe en máximo 3 oraciones los hallazgos morfológicos o valores de laboratorio más relevantes. Extrae puramente la evidencia física y métrica."
        )
        parts = [{"text": instruction}]
        for idx, file in enumerate(attached_files):
            resolved = await resolve_attached_file_data(file, idx=idx)
            if resolved:
                parts.append(resolved)

        async def run_phenotype(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=parts
                )
            else:
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=parts,
                    config=types.GenerateContentConfig(safety_settings=medical_safety_settings)
                )

        response = await with_retry_and_timeout(run_phenotype, 15000, "Pre-Percepción Visual", 1)
        return response.text.strip() if response.text else ""
    except Exception as e:
        print(f"Error extrayendo fenotipo visual: {e}")
        return ""

async def translate_to_english_medical_term(topic: str) -> str:
    if not topic:
        return ""
    try:
        prompt = f"Translate the following medical pathology or symptoms to English, maintaining strict medical terminology suitable for PubMed/EuropePMC searches. Return ONLY the English translation, no other text or explanation. If it's already in English, leave it as is.\n\nText: {topic}"
        async def run_translate(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
            else:
                return await ai.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(safety_settings=medical_safety_settings)
                )
        response = await with_retry_and_timeout(run_translate, 10000, "Traducción Médica", 1)
        return response.text.strip() if response.text else topic
    except Exception as e:
        print(f"[Traductor Médico] Error en la traducción: {e}")
        return topic

async def translate_and_tag_literature(abstract_text: str, suspected_pathology: str) -> str:
    if not abstract_text:
        return ""
    try:
        prompt = (
            "Eres un experto revisor médico y traductor.\n"
            "Tu tarea es doble:\n"
            "1. Traducir el siguiente Abstract médico al Español.\n"
            "2. Comparar el contenido del Abstract con la Sospecha Diagnóstica original del médico y añadir una ETIQUETA SEMÁNTICA al principio del texto traducido.\n\n"
            f"Sospecha Original del Médico: \"{suspected_pathology}\"\n\n"
            f"Abstract a traducir y evaluar:\n\"{abstract_text}\"\n\n"
            "REGLA DE ETIQUETADO (Elige UNA y colócala al inicio del texto, en mayúsculas y negritas):\n"
            "- **🟢 [CONCORDANCIA CLÍNICA]** : Si el artículo habla principalmente de la misma patología o confirma el mismo mecanismo fisiopatológico sospechado.\n"
            "- **🟡 [ALERTA DE COMPLICACIÓN]** : Si el artículo habla de la sospecha, pero se enfoca en una complicación grave, secuela letal o progresión severa.\n"
            "- **🔴 [RED DE SEGURIDAD / DIFERENCIAL ATÍPICO]** : Si el artículo presenta una patología DIFERENTE que puede simular los mismos síntomas (diagnóstico diferencial raro), o contradice la sospecha original.\n\n"
            "FORMATO DE SALIDA ESTRICTO:\n"
            "**[ETIQUETA ELEGIDA]**\n"
            "* 📌 **Similitud Crítica:** [1 única línea breve resumiendo qué variable fisiopatológica, demográfica o farmacológica ancla el artículo a la sospecha del médico].\n"
            "* ⚠️ **Divergencia / Brecha:** [1 única línea breve indicando la principal diferencia clínica (ej. fármacos distintos, edades atípicas, síntomas ausentes), o indicando \"Ninguna\" si el match es absoluto].\n\n"
            "[Texto traducido del abstract]\n\n"
            "No agregues explicaciones adicionales fuera de este formato estricto."
        )
        async def run_tag(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"temperature": 0.2}
                )
            else:
                return await ai.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        temperature=0.2
                    )
                )
        response = await with_retry_and_timeout(run_tag, 15000, "Traductor y Etiquetador Semántico", 1)
        return response.text.strip() if response.text else abstract_text
    except Exception as e:
        print(f"[Traductor Etiquetador] Error, cayendo a traducción simple: {e}")
        return await translate_to_spanish_medical(abstract_text)

async def classify_literature(title: str, abstract: str) -> Dict[str, str]:
    try:
        prompt = (
            "Eres un experto bibliotecario médico.\n"
            "Tu tarea es clasificar la siguiente literatura médica en UNA de las siguientes categorías Macro estrictas y extraer la Patología Micro.\n\n"
            "CATEGORÍAS MACRO PERMITIDAS (Elige solo una de esta lista exacta):\n"
            "Inmunología, Cardiología, Neurología, Oncología, Infectología, Reumatología, Gastroenterología, Medicina Interna, Pediatría, Cirugía General, Tórax, Abdomen, Hombro y Cadera, Cráneo, Mamografía.\n\n"
            "Si no encaja perfectamente en una especialidad, usa \"Medicina Interna\".\n\n"
            f"Literatura:\nTítulo: {title}\nResumen: {abstract}\n\n"
            "Devuelve tu respuesta ÚNICAMENTE en el siguiente formato JSON estricto:\n"
            "{\n  \"macro_category\": \"CategoriaDeLaLista\",\n  \"micro_pathology\": \"NombreCortoDeLaPatologia\"\n}"
        )
        async def run_class(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config={"temperature": 0.1}
                )
            else:
                return await ai.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        temperature=0.1,
                        response_mime_type="application/json"
                    )
                )
        response = await with_retry_and_timeout(run_class, 10000, "Clasificador Bibliotecario", 1)
        if response.text:
            return json.loads(clean_json(response.text))
        return {"macro_category": "Medicina Interna", "micro_pathology": "General"}
    except Exception as e:
        print(f"[Clasificador] Error al clasificar: {e}")
        return {"macro_category": "Medicina Interna", "micro_pathology": "General"}

async def generate_optimized_search_query(pathology: str, context: str) -> Dict[str, Any]:
    try:
        prompt = (
            "Eres un experto bibliotecario médico.\n"
            "Tu tarea es analizar la patología y contexto del paciente y generar un Plan de Búsqueda Multimodal en formato JSON.\n\n"
            "REGLA DE JERARQUÍA ETIOLÓGICA (¡CRÍTICO!):\n"
            "1. NIVEL 1 (Ancla): Si el contexto menciona un agente exógeno específico (fármaco, toxina, veneno), úsalo como primera palabra clave.\n"
            "2. NIVEL 2 (Consecuencia): Agrega el daño orgánico principal (ej. \"acute kidney injury\").\n"
            "3. NIVEL 3 (Síndromes): NO uses nombres de síndromes generales para reemplazar el fármaco. Usa el fármaco primero.\n\n"
            "DECISIÓN DE IMAGEN (GATILLO DINÁMICO):\n"
            "Determina si este caso tiene hallazgos visuales relevantes: anatómicos, estructurales, imagenológicos O ELECTROCARDIOGRÁFICOS (Rayos X, RM, TC, Ecografía, ECG/EKG, \"arritmia visualizable\", \"masa\", \"derrame\", etc.). Radiopaedia también almacena electros. Si es un problema puramente celular/bioquímico o psiquiátrico SIN manifestación visual medible (ni imagen ni ECG), requires_imaging es falso.\n\n"
            f"<patologia>{pathology}</patologia>\n"
            f"<contexto>{context}</contexto>\n\n"
            "Devuelve tu respuesta ÚNICAMENTE en este formato JSON estricto:\n"
            "{\n"
            "  \"step1_etiological_anchor\": \"Identifica el agente causal exacto (fármaco/toxina) o el signo patognomónico único. Si no hay, usa la patología base.\",\n"
            "  \"step2_triage_and_lethality\": \"DIFERENCIACIÓN CRÍTICA: Identifica cuál es la amenaza AGUDA, letal o descompensada actual, y cuáles son las enfermedades CRÓNICAS o de base. Ignora las crónicas.\",\n"
            "  \"step3_cohort_and_mechanism\": \"Identifica el perfil demográfico vital (ej. adult, pediatric, geriatric) y el mecanismo fisiopatológico principal implicado (ej. renal failure, liver failure).\",\n"
            "  \"pmc_query\": \"4 a 6 palabras clave en inglés. Combina: [Ancla Etiológica] + [Amenaza Aguda] + [Filtro Demográfico/Cohorte] + [Mecanismo]. PROHIBIDO incluir enfermedades crónicas estables.\",\n"
            "  \"requires_imaging\": true o false,\n"
            "  \"radiopaedia_query\": \"Si requires_imaging es true, pon 1 a 3 palabras clave en inglés del hallazgo o signo visual/ECG más RARO o ESPECÍFICO (ej. bidirectional tachycardia). Si es false, deja vacío.\"\n"
            "}"
        )
        async def run_opt(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
            else:
                return await ai.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json"
                    )
                )
        response = await with_retry_and_timeout(run_opt, 10000, "Generador de Búsqueda Multimodal", 1)
        if response.text:
            return json.loads(clean_json(response.text))
        return {"pmc_query": pathology, "requires_imaging": False, "radiopaedia_query": ""}
    except Exception as e:
        print(f"[Bibliotecario] Error al optimizar búsqueda: {e}")
        return {"pmc_query": pathology, "requires_imaging": False, "radiopaedia_query": ""}

async def translate_to_spanish_medical(text: str) -> str:
    if not text:
        return ""
    try:
        prompt = f"Traduce el siguiente texto médico (Abstract o Título) al Español, manteniendo el rigor científico y la fluidez gramatical. No agregues comentarios extra, solo devuelve la traducción.\n\nTexto:\n{text}"
        async def run_trans_es(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
            else:
                return await ai.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=types.GenerateContentConfig(safety_settings=medical_safety_settings)
                )
        response = await with_retry_and_timeout(run_trans_es, 12000, "Traducción Inversa", 1)
        return response.text.strip() if response.text else text
    except Exception as e:
        print(f"[Traductor Inverso] Error al traducir a español: {e}")
        return text

async def run_visual_triage(attached_files: List[Dict[str, Any]], context_topic: str = "") -> Dict[str, Any]:
    if not attached_files:
        return {"level": "VERDE", "justification": "Sin imágenes. Evaluación estándar."}
    try:
        instruction = (
            "INSTRUCCIÓN CRÍTICA (AGENTE DE TRIAJE DE EMERGENCIAS): Eres el Médico de Triaje. Tu ÚNICA responsabilidad es mirar la imagen y decidir si es una EMERGENCIA QUIRÚRGICA/CRÍTICA (CÓDIGO ROJO) o un caso ESTÁNDAR/NORMAL (CÓDIGO VERDE).\n\n"
            f"CONTEXTO: \"{context_topic}\"\n\n"
            "REGLAS DE TRIAJE:\n"
            "1. DECLARA CÓDIGO ROJO SI OBSERVAS:\n"
            "   - Disrupción estructural masiva o asimetría extrema.\n"
            "   - Ausencia total de flujo/contenido en zonas distales (ej. silencio radiológico distal, microcolon, corte abrupto).\n"
            "   - Colecciones extraluminales/extravasación masiva.\n"
            "   - Patrones de isquemia o tensión anatómica (ej. múltiples burbujas dilatadas sin gas distal).\n"
            "2. DECLARA CÓDIGO VERDE SI OBSERVAS:\n"
            "   - Continuidad anatómica y de flujo (ej. gas disperso por todo el trayecto hasta el recto).\n"
            "   - Ausencia de bloqueos mecánicos o masas evidentes.\n"
            "   - Patrones fisiológicos esperables.\n\n"
            "Responde en formato JSON estricto: { \"level\": \"ROJO\" | \"VERDE\", \"justification\": \"Breve explicación de los hallazgos que justifican la alerta.\" }"
        )
        parts = [{"text": instruction}]
        for idx, file in enumerate(attached_files):
            resolved = await resolve_attached_file_data(file, idx=idx)
            if resolved:
                parts.append(resolved)

        async def run_triage(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=parts
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "level": {"type": "STRING", "enum": ["ROJO", "VERDE"]},
                        "justification": {"type": "STRING"}
                    },
                    "required": ["level", "justification"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=parts,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        response = await with_retry_and_timeout(run_triage, 15000, "Agente de Triaje Visual", 1)
        raw_text = response.text or "{}"
        return json.loads(clean_json(raw_text))
    except Exception as e:
        print(f"Error en Triaje Visual: {e}")
        return {"level": "VERDE", "justification": "Error en el triaje. Se asume evaluación estándar."}

async def transcribe_audio(audio_base64: str, mime_type: str) -> str:
    try:
        instruction = (
            "INSTRUCCIÓN CRÍTICA: Eres un Escriba Médico Experto de Alto Nivel. Tu tarea es transcribir el siguiente dictado médico con precisión clínica absoluta.\n"
            "REGLAS ESTRICTAS:\n"
            "1. Corrige la ortografía y gramática de nombres de medicamentos, bacterias, síndromes y jerga médica (ej. si escuchas 'para el sol', corrige a 'paracetamol' si el contexto lo indica).\n"
            "2. Mantén el sentido exacto y el tono profesional del dictado original. No resumas ni inventes datos que no se mencionaron.\n"
            "3. Devuelve ÚNICAMENTE el texto transcrito. No añadas introducciones como \"Aquí está la transcripción:\"."
        )
        parts = [
            {"text": instruction},
            {
                "inline_data": {
                    "data": audio_base64,
                    "mime_type": mime_type
                }
            }
        ]
        
        async def run_transcribe(ai):
            # For transcribe audio, we FORCE Google API
            model_name = current_admin_config.get("dictationModel") or current_admin_config.get("dictation_model") or "gemini-2.5-flash"
            if isinstance(ai, OpenRouterWrapper):
                # Fallback to direct client if OpenRouter does not support direct binary audio
                direct_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ai.api_key))
                return await direct_client.aio.models.generate_content(
                    model=model_name,
                    contents=parts,
                    config=types.GenerateContentConfig(safety_settings=medical_safety_settings)
                )
            else:
                return await ai.aio.models.generate_content(
                    model=model_name,
                    contents=parts,
                    config=types.GenerateContentConfig(safety_settings=medical_safety_settings)
                )

        response = await with_retry_and_timeout(run_transcribe, 25000, "Transcripción de Audio Médico (Gemini Live)", 1, force_google=True)
        return response.text.strip() if response.text else ""
    except Exception as e:
        print(f"Error en transcribe_audio: {e}")
        raise Exception(f"Error detallado de Gemini: {e}")

async def filter_hive_mind_memory(topic: str, visual_phenotype: str, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not memories:
        return []
    try:
        memories_text = "\n\n".join([f"--- MEMORIA {i+1} ---\n{m.get('text', m.get('summary', ''))}" for i, m in enumerate(memories)])
        prompt = (
            "Eres el \"Auditor Maestro\" (Filtro de Memoria Evolutiva). Tu trabajo es evitar el Sesgo de Anclaje.\n"
            "El usuario ha presentado un nuevo caso con la siguiente información:\n"
            f"Texto del caso: \"{topic}\"\n"
            f"Fenotipo visual extraído de la imagen (morfología pura): \"{visual_phenotype}\"\n\n"
            f"Se han recuperado las siguientes memorias de casos pasados de la base de datos debido a similitud algorítmica:\n{memories_text}\n\n"
            "Tu tarea: Analiza fríamente si la \"Trampa Clínica\" o el \"Descubrimiento\" de cada memoria aplica verdaderamente al caso actual, o si es un \"Falso Positivo\" (ej. la imagen actual parece Linfoma/Absceso y el texto indica SIDA, pero la memoria es de Cisticercosis).\n"
            "Si la memoria inducirá al médico a un error o anclaje forzado, recházala.\n\n"
            "Responde estrictamente en formato JSON:\n"
            "{\n"
            "  \"filteredMemories\": [\n"
            "    { \"index\": number, \"status\": \"APROBADO\" | \"RECHAZADO\", \"reason\": \"string\" }\n"
            "  ]\n"
            "}"
        )
        async def run_filter(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=prompt
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "filteredMemories": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "index": {"type": "INTEGER"},
                                    "status": {"type": "STRING"},
                                    "reason": {"type": "STRING"}
                                },
                                "required": ["index", "status", "reason"]
                            }
                        }
                    },
                    "required": ["filteredMemories"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        response = await with_retry_and_timeout(run_filter, 10000, "Filtro Maestro", 1)
        raw_text = response.text or "{}"
        parsed_data = json.loads(clean_json(raw_text))

        if "filteredMemories" in parsed_data:
            approved_indices = [
                fm["index"] - 1 for fm in parsed_data["filteredMemories"] if fm.get("status") == "APROBADO"
            ]
            filtered = [memories[i] for i in approved_indices if 0 <= i < len(memories)]
            if len(filtered) < len(memories):
                print(f"[Filtro Maestro] Interceptó y descartó {len(memories) - len(filtered)} memorias irrelevantes para prevenir sesgo.")
            return filtered
        return memories
    except Exception as e:
        print(f"Error en Filtro Maestro: {e}")
        return memories

async def generate_embedding(text: str) -> List[float]:
    try:
        # Embeddings ALWAYS run via official Google client
        ai = get_random_ai_client(force_google=True)
        try:
            res = await ai.aio.models.embed_content(
                model="text-embedding-004",
                contents=text
            )
        except Exception as e:
            if "NOT_FOUND" in str(e) or "404" in str(e):
                print("[Embedding System] Fallback to embedding-001")
                res = await ai.aio.models.embed_content(
                    model="embedding-001",
                    contents=text
                )
            else:
                raise e

        # Extract values
        if res.embeddings and len(res.embeddings) > 0:
            return res.embeddings[0].values
        return [0.001] * 768
    except Exception as e:
        print(f"[Embedding System] Modelo de embedding no disponible. Usando vector nulo degradado: {e}")
        return [0.001] * 768

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b) or len(vec_a) == 0:
        return 0.0
    import math
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a)
    norm_b = sum(b * b for b in vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (math.sqrt(norm_a) * math.sqrt(norm_b))

async def find_relevant_sessions(
    current_topic: str,
    sessions: List[Dict[str, Any]],
    top_k: int = 2,
    current_mode: Optional[str] = None
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not sessions:
        return [], None

    sessions_with_emb = [s for s in sessions if s.get("embedding") and len(s["embedding"]) > 0]

    # Compartmentalization: isolate by mode
    if current_mode and current_mode != "investigator":
        sessions_with_emb = [s for s in sessions_with_emb if s.get("mode", "investigator") == current_mode]

    if not sessions_with_emb:
        return [], None

    query_emb = await generate_embedding(current_topic)
    if not query_emb or query_emb[0] == 0.001:
        return [], None

    scored_sessions = []
    for s in sessions_with_emb:
        sim = cosine_similarity(query_emb, s["embedding"])
        scored_sessions.append((s, sim))

    # Sort descending
    scored_sessions.sort(key=lambda x: x[1], reverse=True)

    relevant = [x[0] for x in scored_sessions[:top_k]]
    
    random_session = None
    if not current_mode or current_mode == "investigator":
        remaining = scored_sessions[top_k:]
        if remaining:
            random_session = random.choice(remaining)[0]

    return relevant, random_session

# --- Reasoning Engines ---

async def run_tribunal(
    topic: str,
    on_step_update,
    past_context: str = "",
    attached_files: Optional[List[Dict[str, Any]]] = None,
    region: Optional[str] = None,
    city: Optional[str] = None
) -> Dict[str, Any]:
    document_summary = None
    document_assimilation = None

    # Step 0: Document Assimilation
    if attached_files and len(attached_files) > 0:
        on_step_update({
            "id": "doc-1",
            "type": "analysis",
            "title": "Asimilación Dinámica de Documentos",
            "content": f"Analizando {len(attached_files)} documento(s) o imagen(es) médica(s) (HL7, FHIR, PDF, JPG) usando \"{topic}\" como lente de extracción...",
            "confidence": 0.95,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        })
        try:
            assimilation_parts = []
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, on_step_update, idx)
                if resolved:
                    assimilation_parts.append(resolved)
            assimilation_parts.append({
                "text": (
                    f"Lee estos documentos o imágenes médicas. El usuario quiere investigar sobre: \"{topic}\".\n"
                    "Identifica de qué tipo de documentos se trata (pueden ser reportes clínicos, archivos HL7/FHIR, imágenes médicas JPG/PNG, etc.) y extrae los 'Anclajes de Conocimiento' más críticos.\n\n"
                    "Si encuentras archivos HL7 o FHIR, interpreta los segmentos de datos (como PID, OBX, OBR) para extraer laboratorios o antecedentes.\n"
                    "Si encuentras imágenes médicas, realiza un análisis visual profundo para identificar anomalías.\n\n"
                    "No te limites a datos biológicos; extrae metodologías, demografía, limitaciones, o cualquier variable que sea vital para este contexto. Identifica también las brechas de conocimiento. Responde en ESPAÑOL en formato JSON."
                )
            })

            async def run_assimilate(ai):
                if isinstance(ai, OpenRouterWrapper):
                    return await ai.models.generate_content(
                        model=get_active_model(),
                        contents=assimilation_parts
                    )
                else:
                    schema = {
                        "type": "OBJECT",
                        "properties": {
                            "documentProfile": {
                                "type": "OBJECT",
                                "properties": {
                                    "type": {"type": "STRING"},
                                    "mainThesis": {"type": "STRING"}
                                },
                                "required": ["type", "mainThesis"]
                            },
                            "contextualAnchors": {
                                "type": "ARRAY",
                                "items": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "category": {"type": "STRING"},
                                        "value": {"type": "STRING"}
                                    },
                                    "required": ["category", "value"]
                                }
                            },
                            "knowledgeGaps": {
                                "type": "ARRAY",
                                "items": {"type": "STRING"}
                            }
                        },
                        "required": ["documentProfile", "contextualAnchors", "knowledgeGaps"]
                    }
                    return await ai.aio.models.generate_content(
                        model=get_active_model(),
                        contents=assimilation_parts,
                        config=types.GenerateContentConfig(
                            safety_settings=medical_safety_settings,
                            response_mime_type="application/json",
                            response_schema=schema
                        )
                    )

            assimilation_response = await with_retry_and_timeout(run_assimilate, 30000, "Asimilador", 1)
            document_assimilation = json.loads(clean_json(assimilation_response.text or "{}"))
            if document_assimilation:
                profile = document_assimilation.get("documentProfile", {})
                document_summary = f"{profile.get('type', '')}: {profile.get('mainThesis', '')}"
        except Exception as e:
            print(f"Error en la asimilación del documento: {e}")

    # Step 1: Investigator
    on_step_update({
        "id": "inv-1",
        "type": "investigator",
        "title": "El Investigador",
        "content": f"Generando 5 hipótesis radicalmente innovadoras sobre: {topic}...",
        "confidence": 0.9,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    })

    hypotheses = []
    connections = []
    parsed_data = {}
    try:
        investigator_parts = []
        if attached_files:
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, on_step_update, idx)
                if resolved:
                    investigator_parts.append(resolved)

        literature_context = await gather_literature_context(topic, on_step_update, "tribunal", attached_files)

        prompt_text = (
            "Eres un Investigador Médico de vanguardia impulsado por un sistema de aprendizaje continuo (Machine Learning) y una Arquitectura de Pensamiento Lateral Bio-Informático.\n"
            f"Tu objetivo es proponer exactamente 5 hipótesis radicalmente innovadoras sobre el tema/pregunta: \"{topic}\".\n\n"
            "Para garantizar innovación de nivel Premio Nobel sin caer en pseudociencia, DEBES aplicar rigurosamente estas 4 REGLAS HEURÍSTICAS INQUEBRANTABLES en orden:\n"
            "1. REGLA DE ABSTRACCIÓN FENOMENOLÓGICA (Motor Anti-Dogma): Tienes estrictamente prohibido abordar el problema usando únicamente etiquetas médicas tradicionales. Antes de generar tu hipótesis, DEBES traducir el problema clínico a un problema de física pura, termodinámica, mecánica de fluidos, o teoría de la información. (Ej: No es \"placa de colesterol\", es \"precipitación de solutos en un sistema cerrado bajo flujo turbulento\").\n"
            "2. REGLA DE EVOLUCIÓN DARWINIANA INVERSA (Motor Biomimético): Busca obligatoriamente de inspiración en la naturaleza. ¿Qué organismo en el planeta (extremófilo, hongo marino, hongo extremófilo) ya ha evolucionado para resolver un problema físico-químico idéntico en los últimos 4 mil millones de años? Extrae el mecanismo de acción.\n"
            "3. REGLA DE EXTRAPOLACIÓN ESTRICTA (Condiciones de Frontera): Toda idea extraída de la física o biología extrema debe sobrevivir en un cuerpo humano. Debes declarar explícitamente cómo tu solución tolerará el \"Terreno Biológico Humano\" (pH 7.4, T° 37°C, sistema inmune activo, no toxicidad sistémica).\n"
            "4. REGLA DEL EXPERIMENTUM CRUCIS (Falsabilidad Pragmática): Basado en Karl Popper, una teoría científica no es válida si no puede ser destruida en un laboratorio. Por cada hipótesis, DEBES diseñar la prueba in-vitro (Fase 0) exacta, utilizando reactivos, líneas celulares y equipos *comercialmente disponibles hoy mismo*, que probaría instantáneamente que tu hipótesis es FALSA. Si no se puede falsear hoy, no sirve.\n"
        )

        if document_assimilation:
            prompt_text += (
                f"\n=== ASIMILACIÓN DE DOCUMENTOS ADJUNTOS ===\nLos documentos adjuntos ya han sido pre-procesados con los siguientes hallazgos clave:\n"
                f"Perfil: {document_assimilation['documentProfile']['type']} - {document_assimilation['documentProfile']['mainThesis']}\n"
                f"Anclajes Contextuales: {json.dumps(document_assimilation['contextualAnchors'])}\n"
                f"Brechas de Conocimiento: {json.dumps(document_assimilation['knowledgeGaps'])}\n\n"
                "INSTRUCCIÓN CRÍTICA: Basa tus hipótesis en estas brechas y anclajes. Para cada hipótesis, DEBES extraer citas textuales exactas (sourceQuotes) de los documentos originales que respalden tu razonamiento.\n"
            )
        elif attached_files:
            prompt_text += "\n=== DOCUMENTOS ADJUNTOS ===\nSe han adjuntado documentos a esta investigación. INSTRUCCIÓN CRÍTICA: Analiza los documentos y basa tus hipótesis en la evidencia de estos documentos cruzada con tu conocimiento. Para cada hipótesis, DEBES extraer citas textuales exactas (sourceQuotes) de los documentos originales que respalden tu razonamiento.\n"

        if region:
            prompt_text += f"\n=== CONTEXTO REGIONAL ===\nEl usuario se encuentra en la región/guía: {region}{f' (Ciudad: {city})' if city else ''}.\nConsidera la disponibilidad tecnológica y la realidad epidemiológica de esta región si es relevante.\n"

        if past_context:
            prompt_text += (
                f"\n\n=== BASE DE CONOCIMIENTO GLOBAL (HIVE-MIND) ===\nAquí está la suma de aprendizajes pasados relevantes y/o aleatorios:\n{past_context}\n\n"
                "=== INSTRUCCIÓN DE SERENDIPIA ===\nUtiliza activamente esta información para cruzar conceptos. Si se te proporciona un CASO ALEATORIO, es tu obligación científica buscar conexiones transversales, reposicionamiento de fármacos o mecanismos compartidos.\n"
            )

        prompt_text = inject_video_scanning_protocol(prompt_text, attached_files)
        prompt_text += f"{literature_context}\n\nResponde en ESPAÑOL en formato JSON estructurado, rellenando todos los nodos de razonamiento para cada hipótesis."
        investigator_parts.append({"text": prompt_text})

        async def run_investigate(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=investigator_parts
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "hypotheses": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "id": {"type": "STRING"},
                                    "phenomenologicalTranslation": {"type": "STRING"},
                                    "biomimeticInspiration": {"type": "STRING"},
                                    "statement": {"type": "STRING"},
                                    "rationale": {"type": "STRING"},
                                    "boundaryConditionCheck": {"type": "STRING"},
                                    "experimentumCrucis": {"type": "STRING"},
                                    "noveltyScore": {"type": "NUMBER"},
                                    "sourceQuotes": {"type": "ARRAY", "items": {"type": "STRING"}}
                                },
                                "required": ["id", "phenomenologicalTranslation", "biomimeticInspiration", "statement", "rationale", "boundaryConditionCheck", "experimentumCrucis", "noveltyScore"]
                            }
                        },
                        "connections": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "pastTopic": {"type": "STRING"},
                                    "extractedInsight": {"type": "STRING"},
                                    "applicationToCurrent": {"type": "STRING"},
                                    "connectionType": {"type": "STRING", "enum": ["directa", "serendipia", "documento"]}
                                },
                                "required": ["pastTopic", "extractedInsight", "applicationToCurrent", "connectionType"]
                            }
                        }
                    },
                    "required": ["hypotheses", "connections"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=investigator_parts,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        investigator_response = await with_retry_and_timeout(run_investigate, 30000, "Investigador", 1)
        raw_text = investigator_response.text or "{}"
        parsed_data = json.loads(clean_json(raw_text))

        hypotheses = parsed_data.get("hypotheses", [])
        connections = parsed_data.get("connections", [])

        if not hypotheses:
            raise Exception("El Investigador no generó hipótesis válidas.")
    except Exception as e:
        raise Exception(f"Fallo en la fase de investigación: {e}")

    # Step 2: Critic
    on_step_update({
        "id": "crit-1",
        "type": "critic",
        "title": "El Crítico Clínico",
        "content": f"Analizando implacablemente las {len(hypotheses)} hipótesis generadas. Buscando fallos lógicos y viabilidad biológica...",
        "confidence": 0.85,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    })

    evaluations = []
    summary = "Sin resumen."

    try:
        critic_parts = []
        if attached_files:
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, on_step_update, idx)
                if resolved:
                    critic_parts.append(resolved)

        critic_prompt = (
            "Eres un Crítico Clínico Élite (El Tribunal de Isomorfismo), implacable, escéptico y experto en fisiología humana, farmacología y toxicología.\n"
            f"El investigador te presentará {len(hypotheses)} hipótesis innovadoras sobre \"{topic}\" generadas mediante Pensamiento Lateral Bio-Informático.\n"
            f"Aquí están las hipótesis:\n{json.dumps(hypotheses, indent=2)}\n\n"
        )
        if document_assimilation:
            critic_prompt += (
                f"=== ASIMILACIÓN DE DOCUMENTOS ADJUNTOS ===\nPerfil: {document_assimilation['documentProfile']['type']}\n"
                f"Tesis: {document_assimilation['documentProfile']['mainThesis']}\n\n"
                "Verifica rigurosamente que las citas textuales (sourceQuotes) proporcionadas por el Investigador sean reales. Destruye cualquier hipótesis que tergiverse el texto original.\n"
            )
        elif attached_files:
            critic_prompt += "=== DOCUMENTOS ADJUNTOS ===\nTienes acceso a los mismos documentos originales que el Investigador. Tu trabajo incluye verificar que el Investigador no haya alucinado o malinterpretado los datos.\n"

        critic_prompt += (
            "Tu misión sagrada es DESTRUIR las hipótesis peligrosas o pseudocientíficas. Busca agresivamente fallos lógicos en la abstracción física, violaciones a las leyes de la termodinámica, toxicidad inaceptable, o imposibilidad biológica.\n"
            "Si el Investigador propone algo que el cuerpo humano (pH, inmunidad) rechazaría letalmente, o si su \"Experimentum Crucis\" requiere tecnología que no existe hoy, DEBES vetarla.\n"
            "Selecciona SOLO las que sobrevivan a tu escrutinio de \"Isomorfismo Científico Riguroso\".\n"
            "Para cada hipótesis, da tu veredicto ('survived' o 'rejected') y una crítica feroz pero científica. Utiliza formato Markdown profesional en tus críticas. NUNCA uses viñetas en la misma línea. Usa SIEMPRE saltos de línea dobles para separar secciones como **Fallo Fisiológico:**, **Evaluación del Biomimetismo:**, **Viabilidad del Experimento:**, etc.\n"
        )
        if attached_files:
            critic_prompt += "También, asigna un 'documentFidelityScore' (0-100) que indique qué tan fiel es la hipótesis a la evidencia de los documentos.\n"
        
        critic_prompt = inject_video_scanning_protocol(critic_prompt, attached_files)
        critic_prompt += "Finalmente, escribe un resumen final del tribunal.\nResponde en ESPAÑOL en formato JSON estructurado."
        critic_parts.append({"text": critic_prompt})

        async def run_critic(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=critic_parts
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "evaluations": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "hypothesisId": {"type": "STRING"},
                                    "status": {"type": "STRING", "enum": ["survived", "rejected"]},
                                    "critique": {"type": "STRING"},
                                    "documentFidelityScore": {"type": "NUMBER"}
                                },
                                "required": ["hypothesisId", "status", "critique"]
                            }
                        },
                        "summary": {"type": "STRING"}
                    },
                    "required": ["evaluations", "summary"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=critic_parts,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        critic_response = await with_retry_and_timeout(run_critic, 30000, "Crítico Clínico", 1)
        raw_text = critic_response.text or "{}"
        critic_data = json.loads(clean_json(raw_text))

        evaluations = critic_data.get("evaluations", [])
        summary = critic_data.get("summary", "Sin resumen.")
    except Exception as e:
        raise Exception(f"Fallo en la fase de crítica: {e}")

    surviving_ids = [e["hypothesisId"] for e in evaluations if e.get("status") == "survived"]
    surviving_hypotheses = [h for h in hypotheses if h["id"] in surviving_ids]

    on_step_update({
        "id": "trib-1",
        "type": "verdict",
        "title": "Veredicto del Tribunal",
        "content": f"Debate concluido. Sobrevivieron {len(surviving_hypotheses)} hipótesis al escrutinio clínico.",
        "confidence": 0.95,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    })

    return {
        "topic": topic,
        "documentSummary": document_summary,
        "documentAssimilation": document_assimilation,
        "methodologicalAnalysis": parsed_data.get("methodologicalAnalysis"),
        "statisticalReview": parsed_data.get("statisticalReview"),
        "investigatorHypotheses": hypotheses,
        "evaluations": evaluations,
        "survivingHypotheses": surviving_hypotheses,
        "futureDirections": parsed_data.get("futureDirections"),
        "ethicalConsiderations": parsed_data.get("ethicalConsiderations"),
        "summary": summary,
        "connections": connections
    }

async def run_clinical_analysis(
    topic: str,
    on_step_update,
    past_context: str = "",
    attached_files: Optional[List[Dict[str, Any]]] = None,
    region: Optional[str] = None,
    city: Optional[str] = None,
    is_debate_mode: bool = False,
    search_category: Optional[str] = None,
    suspected_pathology: Optional[str] = None
) -> Dict[str, Any]:
    on_step_update({
        "id": "clin-1",
        "type": "analysis",
        "title": "Análisis Clínico Estructurado",
        "content": f"Procesando cuadro clínico y generando diagnósticos diferenciales para: {topic}...",
        "confidence": 0.9,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    })

    try:
        parts = []
        resolved_media_parts = []
        if attached_files:
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, on_step_update, idx)
                if resolved:
                    parts.append(resolved)
                    resolved_media_parts.append(resolved)

        literature_context = await gather_literature_context(topic, on_step_update, "clin", attached_files)

        triage_info = ""
        if attached_files and len(attached_files) > 0:
            on_step_update({
                "id": "clin-triage",
                "type": "analysis",
                "title": "Agente de Triaje Visual",
                "content": "Evaluando nivel de alarma en imágenes...",
                "confidence": 0.9,
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            })
            triage = await run_visual_triage(attached_files, topic)
            on_step_update({
                "id": "clin-triage-done",
                "type": "verdict",
                "title": f"Triaje Completado: CÓDIGO {triage.get('level', 'VERDE')}",
                "content": triage.get("justification", ""),
                "confidence": 0.95,
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            })

            if triage.get("level") == "ROJO":
                triage_info = (
                    f"\n\n🚨 ALARMA DE TRIAJE ACTIVADA (CÓDIGO ROJO): El Agente de Triaje ha detectado riesgo inminente: {triage.get('justification')}.\n"
                    "TIENES ESTRICTAMENTE PROHIBIDO USAR EL MODO GUILLOTINA O EL FILTRO DE NORMALIDAD. Enfócate exclusivamente en localizar la obstrucción anatómica, tensión mecánica o daño letal. NO diagnostiques 'variantes normales' frente a esta emergencia."
                )
            else:
                triage_info = (
                    f"\n\n✅ TRIAJE EN CALMA (CÓDIGO VERDE): El Agente de Triaje indica riesgo bajo: {triage.get('justification')}.\n"
                    "Aplica rigurosamente la regla de Sana Normalidad. Evita sobre-patologizar variantes fisiológicas. Si no hay evidencia contundente de enfermedad, diagnostica 'Normalidad'."
                )

        prompt_text = (
            "Eres un Médico Adscrito (Attending Physician) altamente experimentado y un Motor de Razonamiento Clínico Estructurado de Rango Élite.\n"
            f"Tu objetivo es analizar el siguiente cuadro clínico o consulta médica: \"{topic}\".\n"
            f"{triage_info}\n"
            "\n=== PROTOCOLO DE RAZONAMIENTO CLÍNICO AVANZADO (EVITACIÓN DE SESGO Y FALSACIÓN) ===\n"
            "Como médico y radiólogo elite de sistemas complejos, estás estrictamente obligado a seguir el método científico de falsación antes de emitir cualquier diagnóstico. Evita a toda costa el sesgo de anclaje (frequency bias o saltar a diagnósticos comunes por su ubicación) aplicando rigurosamente estas 8 leyes metacognitivas:\n"
            "1. LEY DE FALSACIÓN DE PARÁMETROS FÍSICOS (Falsación Popperiana): Todo diagnóstico diferencial tiene prerrequisitos físicos, biológicos o hemodinámicos específicos. Si sospechas una patología (ej: una neoplasia sólida activa, un tumor altamente vascularizado, etc.), debes listar mentalmente sus prerrequisitos en imagenología (ej: realce nodular de contraste, paredes gruesas e irregulares, restricción en difusión). Si estos prerrequisitos físicos están AUSENTES (ej: realce de contraste de 0.0%, señal puramente líquida y homogénea idéntica al agua o al fluido circundante sano), estás MATEMÁTICAMENTE OBLIGADO a degradar drásticamente la probabilidad de esa patología y descartarla en favor de variantes benignas, quísticas o anomalías anatómicas simples (ej: quistes simples fisiológicos, dilataciones benignas del saco tisular o variantes de normalidad sin compromiso funcional).\n"
            "2. LEY DE JERARQUÍA Y PONDERACIÓN DE IMAGENOLOGÍA FÍSICA (Gold Standards): No todas las modalidades de imagen tienen la misma capacidad de caracterización tisular. En tejidos blandos, márgenes y fluidos, la RESONANCIA MAGNÉTICA (especialmente T2, STIR, FLAIR y difusión) es el Gold Standard absoluto y anula cualquier suposición basada únicamente en tomografía computada (TAC) o ecografía simple. Si la TAC muestra una 'hipodensidad' dudosa sugerida como tumor por un diagnóstico externo superficial, pero la RMN T2 muestra un tono blanco brillante, homogéneo y sin paredes realzantes (señal idéntica al líquido sano), debes dictaminar con firmeza que la lesión es puramente líquida e inocua.\n"
            "3. LEY DE PARSIMONIA Y COHERENCIA DE MULTIPLICIDAD (Navaja de Ockham): En un paciente asintomático o con síntomas leves incidentales, la presencia de múltiples lesiones bilaterales, simétricas o idénticas debe explicarse bajo una única etiología parsimoniosa o variante anatómica benigna (como dilataciones o quistes benignos múltiples). Es clínicamente y estadísticamente inverosímil diagnosticar múltiples neoplasias sólidas independientes que decidieron comportarse todas de forma idéntica, puramente quística y silenciosa. Penaliza los diagnósticos tumorales multicéntricos raros si una variante normal o quiste benigno explica todo de forma natural.\n"
            "4. LEY DEL HALLAZGO NEGATIVO (El Principio de Sherlock Holmes): El hecho de que un signo clave NO esté presente (el 'perro que no ladró') es un hallazgo diagnóstico tan elocuente como el que sí está. Reporta y audita activamente la ausencia de perifocal edema, ausencia de realce, ausencia de destrucción ósea agresiva, ausencia de restricción a la difusión, y ausencia de clínica radicular/mielopática para blindar al paciente contra sobre-medicalización y biopsias iatrogénicas catastróficas.\n"
            "5. LEY DEL PROCESO DUAL (Sistema 1 vs. Sistema 2): Antes de emitir tu veredicto final, estás obligado a realizar un Double Check analítico de tus sospechas preliminares. Si tu Sistema 1 genera un diagnóstico asociativo rápido (intuición), debes activar tu Sistema 2 y verificar si la lesión cumple con todos y cada uno de los prerrequisitos obligatorios. Si falta algún criterio clave, reduce de inmediato la probabilidad y busca alternativas diagnósticas coherentes.\n"
            "6. LEY DE CONSISTENCIA ANATÓMICO-FUNCIONAL 3D (Voxel-Consistency): No analices imágenes como planos 2D aislados. Evalúa la consistencia tridimensional (axial, coronal y sagital) y clasifica la interacción estructural de cualquier anomalía: determina si la lesión desplaza las estructuras y vasos vecinos respetando los planos de clivaje de grasa (indicador de benignidad) o si los invade, borra y envuelve de forma infiltrativa (indicador de agresividad/neoplasia activa).\n"
            "7. LEY DE LA DINÁMICA TEMPORAL DE CONTRASTE (Wash-in / Wash-out): Analiza la hemodinámica del contraste. Si el estudio cuenta con fases dinámicas, evalúa las curvas de captación y lavado (arterial, portal y tardía). Si no se dispone de fases dinámicas y la masa es de densidad/señal intermedia, debes declarar la limitación: \"Se requiere evaluar la dinámica de lavado temporal antes de clasificar una captación intermedia como neoplasia sólida vascularizada\".\n"
            "8. HEURÍSTICA DE LA ZONA DE INCERTIDUMBRE Y SIGUIENTE PASO CLÍNICO (Saber decir \"No Sé\"): Si los parámetros físicos son limítrofes o indeterminados (ej: atenuación entre 15-30 HU en TC o señales mixtas dudosas), debes catalogar el diagnóstico como \"Indeterminado\" y sugerir de manera proactiva el examen de validación ideal (ej: RMN CISS/FIESTA de alta resolución, Angio-TC, Doppler, biopsia dirigida por aguja gruesa).\n"
        )
        if suspected_pathology:
            prompt_text += f"\n=== ETIQUETA CLÍNICA / FARO DEL MÉDICO ===\nEl médico ha indicado explícitamente la siguiente Sospecha Clínica o Contexto: \"{suspected_pathology}\".\nREGLA DEL FARO: Usa esta sospecha como tu \"Ground Truth\" o anclaje inicial. Dirige tu análisis visual y clínico para confirmar o refutar específicamente esta sospecha antes de divagar en diagnósticos remotos.\n"

        if attached_files and len(attached_files) > 0:
            prompt_text += (
                "\n=== DOCUMENTOS E IMÁGENES ADJUNTAS ===\nAnaliza los archivos adjuntos.\n"
                "REGLA CRÍTICA DE VIDEOS / CINE-LOOPS: Si se adjuntan videos o cine-loops (ultrasonido dinámico, barridos de resonancia magnética o tomografía), analiza con rigurosidad la secuencia temporal de fotogramas para evaluar la cinética de flujo, vascularidad, y comportamiento mecánico/dinámico de la anomalía.\n"
                "REGLA CRÍTICA (CONTRADICCIÓN Y JERARQUÍA DE EVIDENCIA): Compara el texto explícito (prompt del usuario o OCR) con los hallazgos visuales puros de las imágenes. Si existe una CONTRADICCIÓN CLARA entre lo que dice el texto (ej. \"Neurocisticercosis\") y lo que muestran las imágenes (ej. patrón clásico de \"Encefalitis Herpética\" en lóbulo temporal), DEBES DETENER TU ANÁLISIS DE ANCLAJE y declarar explícitamente una \"CONTRADICCIÓN CLÍNICO-RADIOLÓGICA\" al inicio de tu reporte. NO asumas ciegamente que la imagen es lo que dice el texto si la morfología es opuesta. Señala el error en los archivos al usuario.\n\n"
                "PASO 1 (Extracción de Datos/OCR e Historial): Lee meticulosamente todo el texto en las imágenes o documentos. Extrae antecedentes, laboratorios previos, diagnósticos y procedimientos. Coloca esto en 'extractedClinicalText'. REGLA DE NO ALUCINACIÓN: Si un dato no está en los documentos, no lo inventes. Pon \"Desconocido\".\n"
                "PASO 2 (Matriz de Signos Radiológicos/Endoscópicos): Busca signos clave en las imágenes. Identifica signos clásicos/epónimos en 'radiologicalSigns'.\n"
                "PASO 3 (Análisis Visual y Fenotipado Profundo): Analiza las imágenes. Detalla anomalías en 'diagnosticFindings'.\n"
                "  a) Topografía Exacta y Cuantificación de Campos: segmenta y cuantifica por zonas (ej. \"60% del calcáneo\").\n"
                "  b) Estructuras Adyacentes Críticas: evalúa órganos o vasos vitales vecinos en 'anatomicalSpecifics'.\n"
                "  c) Marcadores de Riesgo/Agresividad: necrosis intratumoral, elevación ST, etc. en 'riskMarkers'.\n"
                "  d) Parámetros Específicos: RM señal T1/T2, realce, ECG eje, en 'specificParameters'.\n"
                "  e) Vías de Propagación y Contigüidad: fistulización, invasión directa.\n"
                "  f) Inferencia y Correlación Físico-Técnica: secuencia tipo STIR/IDEAL, etc. vinculándolo a hallazgos.\n"
                "  g) Detección de Colecciones: busca fluidos atrapados o abscesos ocultos.\n"
                "  h) Marcadores Visuales (Flechas/Círculos): identifícalos y evalúalos.\n"
                "  i) REGLA DEL ANILLO BIOMECÁNICO: en estructuras en anillo (Pelvis, Mandíbula, etc.), si hay una lesión busca la segunda en el lado opuesto.\n"
                "  j) REGLA DE TRAZABILIDAD VASCULAR (EL PRINCIPIO DEL RÍO): ante isquemia navega río arriba buscando trombos, río abajo drenaje.\n"
                "  k) REGLA DE LOS ESPACIOS OLVIDADOS DINÁMICOS: reporta el estado de los 3 compartimentos externos contiguos.\n"
                "  l) REGLA DE CONGRUENCIA FÍSICA (ARTEFACTO VS BIOLOGÍA): descarta líneas anómalas que desafíen la anatomía como artefactos.\n"
                "  m) REGLA DE BÚSQUEDA ESCALAR (MACRO A MICRO): barrido para micro-hallazgos.\n"
                "  n) REGLA DE RELACIONALIDAD ELOCUENTE: traza vector de compresión contra áreas elocuentes.\n"
                "  o) REGLA DE CUANTIFICACIÓN ESPACIAL RELATIVA: si no hay regla, usa fracciones (ej. \"1/3 del lóbulo\").\n"
                "  p) REGLA DE TRAZABILIDAD DOCUMENTAL ESTRICTA: no inventes PMIDs. Pon \"Ausencia de correlación en literatura proporcionada\" si no concuerda.\n"
                "  q) REGLA DE AGNOSIA FORZADA (Desacoplamiento Percepción-Diagnóstico): estrictamente prohibido usar palabras patológicas (\"pus\", \"necrosis\", \"tumor\") mientras describes los píxeles en el Paso 3. Describe morfología pura.\n"
                "  r) REGLA DE CALIBRACIÓN ÓPTICA Y REFUTACIÓN DE FORMA: compara la señal del centro contra tejido sano de anclaje. Reporta neutro (\"Gris claro\", \"Negro profundo\") en todas las secuencias antes de emitir juicio.\n"
                "\n"
                "PASO 4 (Jerarquización por Significancia Clínica): Clasifica todos y cada uno de los hallazgos descritos en 'clinicalSignificanceGrouping'. Agrúpalos estrictamente en: 'criticalFindings' (compromiso vital inmediato), 'relevantIncidentalFindings' (hallazgos incidentales que aclaran o descartan el caso pero no son emergencias), y 'nonSignificantFindings' (variantes anatómicas comunes, quistes microscópicos estables o variantes normales). Evita a toda costa el sobrediagnóstico.\n"
                "PASO 5 (Memoria Comparativa y Cinética Espacio-Temporal): Revisa la base de conocimiento y el historial médico provisto. Si detectas estudios previos que detallen mediciones anteriores de la misma anomalía, calcula el Delta de Crecimiento Espacio-Temporal (growthDeltaPercent) y el intervalo en meses (timeSpanMonths). Si el delta es menor o igual al 5.0% (estabilidad biológica espacio-temporal), rebaja drásticamente la sospecha de neoplasia agresiva en favor de una variante benigna o quística estable, y justifícalo en 'stabilityRationale'. Si no hay estudios previos, clasifica el cálculo como 'indeterminado'.\n"
                "PASO 6 (Explicabilidad Médica Avanzada - XAI): Para cada diagnóstico en 'differentialDiagnoses', debes proveer un párrafo detallado en 'differentialExclusion' justificando científicamente por qué esa condición fue excluida como diagnóstico principal o por qué se catalogó con menor probabilidad, detallando los signos físicos/fisiológicos ausentes o incompatibles.\n"
            )

        if past_context:
            prompt_text += f"\n=== BASE DE CONOCIMIENTO (HIVE-MIND) ===\nAquí están los aprendizajes pasados:\n{past_context}\n"

        prompt_text = inject_video_scanning_protocol(prompt_text, attached_files)
        prompt_text += f"{literature_context}\n\nResponde en ESPAÑOL en formato JSON estricto."
        parts.append({"text": prompt_text})

        async def run_clinical(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=parts
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "patientProfile": {
                            "type": "OBJECT",
                            "properties": {
                                "demographics": {"type": "STRING"},
                                "chiefComplaint": {"type": "STRING"},
                                "pastMedicalHistory": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "socialHistory": {"type": "STRING"},
                                "comorbidities": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["demographics", "chiefComplaint", "pastMedicalHistory", "comorbidities"]
                        },
                        "extractedClinicalText": {"type": "STRING"},
                        "radiologicalSigns": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "sign": {"type": "STRING"},
                                    "present": {"type": "BOOLEAN"},
                                    "description": {"type": "STRING"}
                                },
                                "required": ["sign", "present", "description"]
                            }
                        },
                        "diagnosticFindings": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "modality": {"type": "STRING"},
                                    "findings": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "interpretation": {"type": "STRING"},
                                    "technicalDetails": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "specificParameters": {
                                                "type": "ARRAY",
                                                "items": {
                                                    "type": "OBJECT",
                                                    "properties": {
                                                        "name": {"type": "STRING"},
                                                        "value": {"type": "STRING"}
                                                    },
                                                    "required": ["name", "value"]
                                                }
                                            },
                                            "anatomicalSpecifics": {"type": "STRING"},
                                            "measurements": {"type": "STRING"},
                                            "riskMarkers": {"type": "ARRAY", "items": {"type": "STRING"}}
                                        }
                                    }
                                },
                                "required": ["modality", "findings", "interpretation"]
                            }
                        },
                        "syndromes": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "confoundingFactors": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "factor": {"type": "STRING"},
                                    "impact": {"type": "STRING"}
                                },
                                "required": ["factor", "impact"]
                            }
                        },
                        "absentSignsAnalysis": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "sign": {"type": "STRING"},
                                    "expectedIn": {"type": "STRING"},
                                    "clinicalSignificance": {"type": "STRING"}
                                },
                                "required": ["sign", "expectedIn", "clinicalSignificance"]
                            }
                        },
                        "differentialDiagnoses": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "condition": {"type": "STRING"},
                                    "probability": {"type": "STRING", "enum": ["alta", "media", "baja"]},
                                    "rationale": {"type": "STRING"},
                                    "differentialExclusion": {"type": "STRING"}
                                },
                                "required": ["condition", "probability", "rationale", "differentialExclusion"]
                            }
                        },
                        "redFlags": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "condition": {"type": "STRING"},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["condition", "rationale"]
                            }
                        },
                        "prognosticScores": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "name": {"type": "STRING"},
                                    "score": {"type": "STRING"},
                                    "interpretation": {"type": "STRING"},
                                    "mortalityRisk": {"type": "STRING"}
                                },
                                "required": ["name", "score", "interpretation"]
                            }
                        },
                        "interventionPriority": {
                            "type": "OBJECT",
                            "properties": {
                                "actionZero": {"type": "STRING"},
                                "rationale": {"type": "STRING"},
                                "urgency": {"type": "STRING", "enum": ["inmediata", "alta", "moderada"]}
                            },
                            "required": ["actionZero", "rationale", "urgency"]
                        },
                        "systemicIntegration": {
                            "type": "OBJECT",
                            "properties": {
                                "unifiedDiagnosis": {"type": "STRING"},
                                "pathophysiologicalConnection": {"type": "STRING"}
                            },
                            "required": ["unifiedDiagnosis", "pathophysiologicalConnection"]
                        },
                        "workup": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "category": {"type": "STRING"},
                                    "tests": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["category", "tests", "rationale"]
                            }
                        },
                        "treatment": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "phase": {"type": "STRING"},
                                    "interventions": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "contraindications": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "interactions": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["phase", "interventions", "rationale"]
                            }
                        },
                        "summary": {"type": "STRING"},
                        "clinicalSignificanceGrouping": {
                            "type": "OBJECT",
                            "properties": {
                                "criticalFindings": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "relevantIncidentalFindings": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "nonSignificantFindings": {"type": "ARRAY", "items": {"type": "STRING"}}
                            },
                            "required": ["criticalFindings", "relevantIncidentalFindings", "nonSignificantFindings"]
                        },
                        "temporalComparison": {
                            "type": "OBJECT",
                            "properties": {
                                "growthDeltaPercent": {"type": "NUMBER"},
                                "timeSpanMonths": {"type": "NUMBER"},
                                "previousMeasurement": {"type": "STRING"},
                                "currentMeasurement": {"type": "STRING"},
                                "stabilityAssessment": {"type": "STRING", "enum": ["estable", "progresion_lenta", "progresion_rapida", "indeterminada"]},
                                "stabilityRationale": {"type": "STRING"}
                            },
                            "required": ["stabilityAssessment", "stabilityRationale"]
                        }
                    },
                    "required": ["patientProfile", "differentialDiagnoses", "redFlags", "workup", "treatment", "summary", "clinicalSignificanceGrouping", "temporalComparison"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=parts,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        clinical_response = await with_retry_and_timeout(run_clinical, 60000, "Análisis Clínico Estructurado", 1)
        raw_text = clinical_response.text or "{}"
        parsed_data = json.loads(clean_json(raw_text))

        evaluations = []
        board_summary = None
        red_team_audit = None
        corrected_differential_diagnoses = None
        corrected_workup = None
        corrected_treatment = None
        corrected_intervention_priority = None
        corrected_syndromes = None
        corrected_clinical_significance_grouping = None
        corrected_temporal_comparison = None

        # Step 4: Red Team Debate Loop
        if is_debate_mode:
            on_step_update({
                "id": "clin-debate",
                "type": "critic",
                "title": "Junta Médica (Red Team)",
                "content": "Sometiendo el diagnóstico preliminar a debate de oposición médica cruzada...",
                "confidence": 0.85,
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            })
            try:
                debate_parts = list(resolved_media_parts)

                debate_prompt = (
                    "Eres el 'Red Team Médico' (Junta Médica Antagonista y Escéptica de Rango Élite).\n"
                    f"El Médico Adscrito ha elaborado este reporte preliminar para el tema: \"{topic}\":\n"
                    f"{json.dumps(parsed_data, indent=2)}\n\n"
                    "Tu ÚNICA misión es encontrar sesgos de anclaje, alucinaciones o errores lógicos. Sé implacable y destructivo.\n"
                    "Aplica las siguientes sub-reglas de debate:\n"
                    "1. Sub-regla de Volumetría y Magnitud: critica si omitió dimensiones, porcentajes de afectación o volúmenes relativos en la descripción de las imágenes.\n"
                    "2. Sub-regla de Correlación Técnica: critica si describió hallazgos sin justificar la secuencia (T1/T2/DWI) o tinción.\n"
                    "3. Sub-regla de Estructuras Adyacentes y Márgenes: critica ferozmente si no evaluó la compresión o contorno de órganos vecinos.\n"
                    "4. Sub-regla de Sesgo de Benignidad: ataca agresivamente si asumió una etiología benigna frente a signos de malignidad inminente (necrosis, erosión cortical, etc.).\n"
                    "5. Sub-regla de Sobre-Medicalización: critica si sugirió tratamientos agresivos para variantes normales o patologías estables.\n"
                    "6. Sub-regla de Falsación Científica y Anclaje (Anti-Sesgo): Audita si el adscrito asumió un diagnóstico tumoral/grave por mera frecuencia o ubicación (sesgo de anclaje) ignorando la falta de prerrequisitos físicos (ej: diagnosticar una neoplasia sólida activa en una lesión puramente líquida que tiene 0.0% de realce de contraste y señal idéntica al agua/líquido de anclaje). Si detectas esta contradicción física, VETA de inmediato el diagnóstico y reordena los diferenciales para colocar la variante benigna, dilatación o quiste simple al tope absoluto.\n"
                    "7. Sub-regla de Coherencia de Multiplicidad y Parsimonia (Ockham): Critica si el adscrito diagnosticó múltiples neoplasias independientes raras en un paciente asintomático, en lugar de unificar todo bajo una única variante anatómica benigna común y sistémica (como quistes o dilataciones benignas múltiples).\n"
                    "8. Sub-regla de la Zona de Incertidumbre y Proceso Dual: Audita si el adscrito incurrió en cierre prematuro (Sistema 1) sin realizar el Double Check analítico del Sistema 2, o si omitió declarar un hallazgo limítrofe o indeterminado como tal e indicar de forma proactiva el Gold Standard de validación idóneo.\n"
                    "9. Sub-regla de Invasión de Planos y Consistencia 3D: Audita si el adscrito omitió evaluar rigurosamente los planos de grasa de clivaje, borramiento de márgenes o envolvimiento de estructuras vasculares y nerviosas como marcador tridimensional de agresividad o benignidad.\n"
                    "10. Sub-regla de Coherencia Terapéutica Post-Refutación (Vacuna contra el Arrastre / Leakage Vaccine): Si tu auditoría anula o degrada el diagnóstico inicial en favor de una variante benigna, quística o no quirúrgica (ej: de Schwannoma a Meningocele o Quiste de Tarlov), estás OBLIGADO a actualizar también la Prioridad de Intervención (correctedInterventionPriority) y la Agrupación Sindromática (correctedSyndromes) para que recomienden un manejo clínico conservador de vigilancia activa. 🛡️ VACUNA CONTRA EL ARRASTRE DE CONTEXTO: Tienes estrictamente prohibido copiar, heredar o arrastrar la urgencia o la acción del reporte del médico de primer nivel si has vetado su diagnóstico. Si has clasificado la lesión como de manejo conservador o variante benigna asintomática, estás obligado a reescribir de raíz correctedInterventionPriority, forzando la urgencia a 'moderada' o 'baja' y la Acción Cero a 'Vigilancia clínica neurológica y/o resonancia de control'. Cualquier contradicción donde recomiendes cirugía en Acción Cero pero digas que es benigna no quirúrgica en el tratamiento será penalizada como un fallo crítico de lógica médica.\n\n"
                    "Si encuentras fallas, VETA los diagnósticos erróneos y re-formula la jerarquía diagnóstica (correctedDifferentialDiagnoses - asegurando incluir differentialExclusion en cada item), la significancia clínica (correctedClinicalSignificanceGrouping), la estabilidad temporal (correctedTemporalComparison), plan (correctedWorkup), tratamiento (correctedTreatment), la prioridad de intervención (correctedInterventionPriority) y los síndromes (correctedSyndromes).\n"
                    "Responde en ESPAÑOL en formato JSON."
                )
                debate_parts.append({"text": debate_prompt})

                async def run_debate(ai):
                    if isinstance(ai, OpenRouterWrapper):
                        return await ai.models.generate_content(
                            model=get_active_model(),
                            contents=debate_parts
                        )
                    else:
                        schema = {
                            "type": "OBJECT",
                            "properties": {
                                "evaluations": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "condition": {"type": "STRING"},
                                            "status": {"type": "STRING", "enum": ["survived", "rejected"]},
                                            "critique": {"type": "STRING"}
                                        },
                                        "required": ["condition", "status", "critique"]
                                    }
                                },
                                "boardSummary": {"type": "STRING"},
                                "redTeamAudit": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "missedMicroFindings": {"type": "STRING"},
                                        "volumetryCritique": {"type": "STRING"},
                                        "technicalCorrelationCritique": {"type": "STRING"},
                                        "adjacentStructuresCritique": {"type": "STRING"},
                                        "benignityBiasCritique": {"type": "STRING"},
                                        "overMedicalizationCritique": {"type": "STRING"}
                                    },
                                    "required": ["missedMicroFindings", "volumetryCritique", "technicalCorrelationCritique"]
                                },
                                "correctedDifferentialDiagnoses": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "condition": {"type": "STRING"},
                                            "probability": {"type": "STRING", "enum": ["alta", "media", "baja"]},
                                            "rationale": {"type": "STRING"},
                                            "differentialExclusion": {"type": "STRING"}
                                        },
                                        "required": ["condition", "probability", "rationale", "differentialExclusion"]
                                    }
                                },
                                "correctedWorkup": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "category": {"type": "STRING"},
                                            "tests": {"type": "ARRAY", "items": {"type": "STRING"}},
                                            "rationale": {"type": "STRING"}
                                        },
                                        "required": ["category", "tests", "rationale"]
                                    }
                                },
                                "correctedTreatment": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "phase": {"type": "STRING"},
                                            "interventions": {"type": "ARRAY", "items": {"type": "STRING"}},
                                            "rationale": {"type": "STRING"}
                                        },
                                        "required": ["phase", "interventions", "rationale"]
                                    }
                                },
                                "correctedSystemicIntegration": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "unifiedDiagnosis": {"type": "STRING"},
                                        "pathophysiologicalConnection": {"type": "STRING"}
                                    }
                                },
                                "correctedSummary": {"type": "STRING"},
                                "correctedSyndromes": {
                                    "type": "ARRAY",
                                    "items": {"type": "STRING"}
                                },
                                "correctedInterventionPriority": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "actionZero": {"type": "STRING"},
                                        "rationale": {"type": "STRING"},
                                        "urgency": {"type": "STRING", "enum": ["inmediata", "alta", "moderada"]}
                                    },
                                    "required": ["actionZero", "rationale", "urgency"]
                                },
                                "correctedClinicalSignificanceGrouping": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "criticalFindings": {"type": "ARRAY", "items": {"type": "STRING"}},
                                        "relevantIncidentalFindings": {"type": "ARRAY", "items": {"type": "STRING"}},
                                        "nonSignificantFindings": {"type": "ARRAY", "items": {"type": "STRING"}}
                                    },
                                    "required": ["criticalFindings", "relevantIncidentalFindings", "nonSignificantFindings"]
                                },
                                "correctedTemporalComparison": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "growthDeltaPercent": {"type": "NUMBER"},
                                        "timeSpanMonths": {"type": "NUMBER"},
                                        "previousMeasurement": {"type": "STRING"},
                                        "currentMeasurement": {"type": "STRING"},
                                        "stabilityAssessment": {"type": "STRING", "enum": ["estable", "progresion_lenta", "progresion_rapida", "indeterminada"]},
                                        "stabilityRationale": {"type": "STRING"}
                                    },
                                    "required": ["stabilityAssessment", "stabilityRationale"]
                                }
                            },
                            "required": ["evaluations", "boardSummary", "redTeamAudit"]
                        }
                        return await ai.aio.models.generate_content(
                            model=get_active_model(),
                            contents=debate_parts,
                            config=types.GenerateContentConfig(
                                safety_settings=medical_safety_settings,
                                response_mime_type="application/json",
                                response_schema=schema
                            )
                        )

                debate_response = await with_retry_and_timeout(run_debate, 60000, "Junta Médica (Red Team)", 1)
                debate_data = json.loads(clean_json(debate_response.text or "{}"))

                evaluations = debate_data.get("evaluations", [])
                board_summary = debate_data.get("boardSummary")
                red_team_audit = debate_data.get("redTeamAudit")
                corrected_differential_diagnoses = debate_data.get("correctedDifferentialDiagnoses")
                corrected_workup = debate_data.get("correctedWorkup")
                corrected_treatment = debate_data.get("correctedTreatment")
                corrected_intervention_priority = debate_data.get("correctedInterventionPriority")
                corrected_syndromes = debate_data.get("correctedSyndromes")
                corrected_clinical_significance_grouping = debate_data.get("correctedClinicalSignificanceGrouping")
                corrected_temporal_comparison = debate_data.get("correctedTemporalComparison")

                # 🛡️ CAPA DE VALIDACIÓN METACOGNITIVA (JUEZ DE LA JUNTA):
                # Erradicar cualquier discrepancia residual de urgencia si la junta médica determinó que el manejo es conservador.
                if corrected_intervention_priority and isinstance(corrected_intervention_priority, dict):
                    urgency_val = str(corrected_intervention_priority.get("urgency", "")).lower()
                    action_val = str(corrected_intervention_priority.get("actionZero", "")).lower()
                    
                    consenso_val = str(board_summary).lower() if board_summary else ""
                    treatment_val = ""
                    if corrected_treatment and isinstance(corrected_treatment, list):
                        treatment_val = " ".join([str(t.get("rationale", "")).lower() + " " + " ".join([str(i).lower() for i in t.get("interventions", [])]) for t in corrected_treatment])
                    
                    # Si el consenso de la junta o las fases de tratamiento sugieren vigilancia/conservador/observación
                    if any(kw in consenso_val or kw in treatment_val for kw in ["vigilancia", "observación", "observacion", "no quirúrgic", "no quirurgic", "conservador"]):
                        if urgency_val in ["inmediata", "alta"] or any(kw in action_val for kw in ["urgente", "quirúrgic", "quirurgic", "descompresió", "descompresio", "resección", "reseccion"]):
                            print("[Juez de la Junta] Detectada discrepancia de urgencia residual en Acción Cero. Corrigiendo...")
                            corrected_intervention_priority["urgency"] = "moderada"
                            corrected_intervention_priority["actionZero"] = "Vigilancia clínica neurológica y resonancia magnética de seguimiento"
                            corrected_intervention_priority["rationale"] = (
                                "La Junta Médica determinó la naturaleza benigna e incidental de la lesión (meningocele/quiste), "
                                "por lo que se descarta la descompresión urgente y se opta por observación y control evolutivo conservador."
                            )

                if debate_data.get("correctedSystemicIntegration"):
                    parsed_data["systemicIntegration"] = debate_data["correctedSystemicIntegration"]
                if debate_data.get("correctedSummary"):
                    parsed_data["summary"] = debate_data["correctedSummary"]


                on_step_update({
                    "id": "clin-debate-done",
                    "type": "verdict",
                    "title": "Consenso de la Junta (Red Team)",
                    "content": f"La junta médica ha evaluado los diagnósticos y auditado el reporte. {len([e for e in evaluations if e.get('status') == 'survived'])} diagnósticos sobrevivieron al escrutinio.",
                    "confidence": 0.95,
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                })
            except Exception as e:
                print(f"Error en el debate clínico: {e}")
                on_step_update({
                    "id": "clin-debate-error",
                    "type": "critic",
                    "title": "Error en la Junta Médica",
                    "content": f"No se pudo completar el debate: {e}",
                    "confidence": 0.5,
                    "timestamp": int(asyncio.get_event_loop().time() * 1000)
                })
        else:
            on_step_update({
                "id": "clin-2",
                "type": "verdict",
                "title": "Reporte Clínico Completado",
                "content": f"Se han identificado {len(parsed_data.get('differentialDiagnoses', []))} diagnósticos diferenciales y {len(parsed_data.get('redFlags', []))} banderas rojas.",
                "confidence": 0.95,
                "timestamp": int(asyncio.get_event_loop().time() * 1000)
            })

        return {
            "topic": topic,
            "patientProfile": parsed_data.get("patientProfile"),
            "physicalExam": parsed_data.get("physicalExam"),
            "laboratoryData": parsed_data.get("laboratoryData") or [],
            "extractedClinicalText": parsed_data.get("extractedClinicalText"),
            "radiologicalSigns": parsed_data.get("radiologicalSigns") or [],
            "diagnosticFindings": parsed_data.get("diagnosticFindings") or [],
            "syndromes": parsed_data.get("syndromes") or [],
            "confoundingFactors": [f for f in parsed_data.get("confoundingFactors", []) if f and f.get("factor") and f.get("factor").strip() != "" and f.get("factor").lower() != "sin datos"],
            "absentSignsAnalysis": parsed_data.get("absentSignsAnalysis") or [],
            "differentialDiagnoses": corrected_differential_diagnoses or parsed_data.get("differentialDiagnoses") or [],
            "evaluations": evaluations if evaluations else None,
            "boardSummary": board_summary,
            "redTeamAudit": red_team_audit,
            "redFlags": parsed_data.get("redFlags") or [],
            "prognosticScores": parsed_data.get("prognosticScores") or [],
            "workup": corrected_workup or parsed_data.get("workup") or [],
            "treatment": corrected_treatment or parsed_data.get("treatment") or [],
            "contingencyPlan": parsed_data.get("contingencyPlan"),
            "disposition": parsed_data.get("disposition"),
            "clinicalEvolution": parsed_data.get("clinicalEvolution") or [],
            "ethicalLegalConsiderations": parsed_data.get("ethicalLegalConsiderations") or [],
            "interventionPriority": parsed_data.get("interventionPriority"),
            "systemicIntegration": parsed_data.get("systemicIntegration"),
            "summary": parsed_data.get("summary", "Sin resumen."),
            "historicalAuditor": parsed_data.get("historicalAuditor"),
            "clinicalSignificanceGrouping": corrected_clinical_significance_grouping or parsed_data.get("clinicalSignificanceGrouping"),
            "temporalComparison": corrected_temporal_comparison or parsed_data.get("temporalComparison")
        }
    except Exception as e:
        raise Exception(f"Fallo en el análisis clínico: {e}")

async def amend_clinical_report(old_report: Dict[str, Any], cognitive_autopsy: Dict[str, Any]) -> Dict[str, Any]:
    try:
        prompt_text = (
            "Eres un Auditor Médico Jefe y Experto en Integración Sistémica.\n"
            "Tu objetivo es RE-ESCRIBIR por completo un Reporte Clínico que ha sido identificado como defectuoso debido a un sesgo cognitivo.\n"
            "Se ha realizado una \"Autopsia Cognitiva\" que revela la verdad oculta. Debes tomar el reporte original y reescribir todas sus secciones (especialmente Diagnósticos Diferenciales, Plan de Abordaje y Tratamiento) para que sean 100% congruentes con esta Verdad Revelada.\n\n"
            "=== VERDAD REVELADA (NUEVO DESCUBRIMIENTO) ===\n"
            f"Verdad: {cognitive_autopsy.get('verdad_revelada')}\n"
            f"Trampa Clínica Cometida: {cognitive_autopsy.get('trampa_clinica')}\n"
            f"Aforismo: {cognitive_autopsy.get('aforismo_medico')}\n\n"
            f"=== REPORTE ORIGINAL (A CORREGIR) ===\n{json.dumps(old_report, indent=2)}\n\n"
            "INSTRUCCIONES CRÍTICAS:\n"
            "1. JERARQUÍA DIAGNÓSTICA (OBLIGATORIA): Reescribe la sección de 'differentialDiagnoses' para que la 'Verdad Revelada' sea el diagnóstico número uno con Probabilidad ALTA. Elimina o baja de categoría los diagnósticos previos que ahora sabes que son incorrectos.\n"
            "2. TRATAMIENTO DIRECCIONADO: Elimina por completo los tratamientos (ej. Aciclovir, cirugías innecesarias) que estaban dirigidos al diagnóstico erróneo original. Reescribe el Plan de Abordaje (workup) y Tratamiento (treatment) para que se enfoquen directamente en confirmar y tratar la Verdad Revelada (ej. si la verdad es un parásito, sugiere antiparasitarios como Albendazol/Praziquantel).\n"
            "3. INTEGRACIÓN Y CONSENSO: Reescribe la 'systemicIntegration', el 'summary' y si existe, el Consenso de la Junta, reflejando este diagnóstico certero. No puedes decir que el reporte \"sospecha de neoplasia\" si la verdad revelada es otra.\n"
            "4. Mantén la estructura JSON exacta del reporte clínico. No omitas las secciones de patientProfile, physicalExam, etc. Mantenlas igual si no necesitan cambiar.\n\n"
            "Responde ÚNICAMENTE en formato JSON usando la estructura estándar de un reporte clínico."
        )

        async def run_amend(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=prompt_text
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "patientProfile": {"type": "OBJECT"},
                        "physicalExam": {"type": "OBJECT"},
                        "laboratoryData": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "extractedClinicalText": {"type": "STRING"},
                        "radiologicalSigns": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "diagnosticFindings": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "syndromes": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "confoundingFactors": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "factor": {"type": "STRING"},
                                    "impact": {"type": "STRING"}
                                },
                                "required": ["factor", "impact"]
                            }
                        },
                        "absentSignsAnalysis": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "differentialDiagnoses": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "redFlags": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "prognosticScores": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "workup": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "treatment": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "contingencyPlan": {"type": "OBJECT"},
                        "disposition": {"type": "OBJECT"},
                        "clinicalEvolution": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "ethicalLegalConsiderations": {"type": "ARRAY", "items": {"type": "OBJECT"}},
                        "systemicIntegration": {"type": "OBJECT"},
                        "summary": {"type": "STRING"}
                    },
                    "required": ["patientProfile", "syndromes", "differentialDiagnoses", "workup", "treatment", "summary", "systemicIntegration"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        response = await with_retry_and_timeout(run_amend, 120000, "Enmienda de Reporte Clínico", 1)
        raw_text = response.text or "{}"
        amended_data = json.loads(clean_json(raw_text))

        result = dict(old_report)
        result.update(amended_data)
        result["summary"] = f"[ENMIENDA OFICIAL: DIAGNÓSTICO CORREGIDO]\nVerdad Revelada: {cognitive_autopsy.get('verdad_revelada')}\n\n{amended_data.get('summary', '')}"
        return result
    except Exception as e:
        raise Exception(f"Fallo en la Enmienda del Reporte: {e}")

async def run_epidemiology_analysis(
    topic: str,
    on_step_update,
    past_context: str = "",
    attached_files: Optional[List[Dict[str, Any]]] = None,
    region: Optional[str] = None,
    city: Optional[str] = None
) -> Dict[str, Any]:
    on_step_update({
        "id": "epi-1",
        "type": "analysis",
        "title": "Vigilancia Epidemiológica Macro",
        "content": f"Extrayendo datos clínicos, analizando vulnerabilidad poblacional y modelando escenarios para: {topic}...",
        "confidence": 0.9,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    })

    try:
        parts = []
        if attached_files:
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, on_step_update, idx)
                if resolved:
                    parts.append(resolved)

        literature_context = await gather_literature_context(topic, on_step_update, "epi", attached_files)

        prompt_text = (
            "Eres un Epidemiólogo de Vanguardia y Experto en Vigilancia Sanitaria Inteligente a Nivel Macro.\n"
            f"Tu objetivo es realizar un análisis profundo de la información proporcionada: \"{topic}\".\n\n"
        )
        if attached_files and len(attached_files) > 0:
            prompt_text += f"\n=== DOCUMENTOS E IMÁGENES ADJUNTAS ===\nSe han adjuntado {len(attached_files)} archivo(s). Realiza un análisis visual profundo o interpreta datos clínicos de los archivos.\n"
        if past_context:
            prompt_text += f"\n=== BASE DE CONOCIMIENTO GLOBAL ===\n{past_context}\n"
        prompt_text += f"{literature_context}\n"
        if region:
            prompt_text += f"\n=== CONTEXTO REGIONAL Y EPIDEMIOLÓGICO ===\nEl análisis se centra en la región: {region}{f' (Ciudad: {city})' if city else ''}.\nConsidera la epidemiología local al proponer medidas.\n"

        prompt_text += (
            "Debes generar un reporte epidemiológico estructurado. ADAPTA las secciones según el contexto (Infeccioso, Crónico, Ambiental, etc.).\n"
            "SECCIONES OBLIGATORIAS:\n"
            "1. Perfil de la Región (regionProfile)\n"
            "2. Factores Ambientales (environmentalFactors)\n"
            "3. Vulnerabilidad Poblacional (populationVulnerability)\n"
            "4. Impacto en el Sistema de Salud (healthcareSystemImpact)\n"
            "5. Análisis de Riesgo (riskAnalysis)\n"
            "6. Optimización de Recursos (resourceOptimization)\n"
            "7. Medidas Preventivas (preventiveMeasures)\n"
            "8. Alertas de Vigilancia (surveillanceAlerts)\n"
            "9. Resumen (summary)\n\n"
            "Responde en ESPAÑOL en formato JSON estricto."
        )
        prompt_text = inject_video_scanning_protocol(prompt_text, attached_files)
        parts.append({"text": prompt_text})

        async def run_epi(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=parts
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "regionProfile": {
                            "type": "OBJECT",
                            "properties": {
                                "location": {"type": "STRING"},
                                "populationAtRisk": {"type": "STRING"},
                                "epidemiologicalWeek": {"type": "STRING"},
                                "incidenceRate": {"type": "STRING"},
                                "prevalenceRate": {"type": "STRING"},
                                "demographicContext": {"type": "STRING"}
                            },
                            "required": ["location", "populationAtRisk"]
                        },
                        "outbreakDynamics": {
                            "type": "OBJECT",
                            "properties": {
                                "basicReproductionNumber": {"type": "STRING"},
                                "transmissionVectors": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "epidemicCurveTrend": {"type": "STRING", "enum": ["crecimiento_exponencial", "crecimiento_lineal", "meseta", "declive", "indeterminado"]},
                                "rationale": {"type": "STRING"}
                            },
                            "required": ["transmissionVectors", "epidemicCurveTrend", "rationale"]
                        },
                        "genomicEpidemiology": {
                            "type": "OBJECT",
                            "properties": {
                                "variantsOrSerotypes": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "mutationRateAnalysis": {"type": "STRING"},
                                "transmissionAdvantage": {"type": "STRING"},
                                "impactOnDiagnostics": {"type": "STRING"},
                                "impactOnTherapeutics": {"type": "STRING"}
                            }
                        },
                        "environmentalFactors": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "factor": {"type": "STRING"},
                                    "impact": {"type": "STRING", "enum": ["facilitador", "barrera", "neutral"]},
                                    "description": {"type": "STRING"}
                                },
                                "required": ["factor", "impact", "description"]
                            }
                        },
                        "populationVulnerability": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "groupOrZone": {"type": "STRING"},
                                    "riskFactor": {"type": "STRING"},
                                    "vulnerabilityScore": {"type": "STRING", "enum": ["baja", "media", "alta", "crítica"]},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["groupOrZone", "riskFactor", "vulnerabilityScore", "rationale"]
                            }
                        },
                        "socioeconomicImpact": {
                            "type": "OBJECT",
                            "properties": {
                                "economicBurden": {"type": "STRING"},
                                "laborProductivityImpact": {"type": "STRING"},
                                "socialInequityFactor": {"type": "STRING"},
                                "educationalImpact": {"type": "STRING"}
                            }
                        },
                        "healthcareSystemImpact": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "resourceType": {"type": "STRING"},
                                    "currentStatus": {"type": "STRING", "enum": ["holgado", "tensión", "saturado", "colapso"]},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["resourceType", "currentStatus", "rationale"]
                            }
                        },
                        "riskAnalysis": {
                            "type": "OBJECT",
                            "properties": {
                                "currentThreats": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "condition": {"type": "STRING"},
                                            "riskLevel": {"type": "STRING", "enum": ["bajo", "medio", "alto", "crítico"]},
                                            "rationale": {"type": "STRING"}
                                        },
                                        "required": ["condition", "riskLevel", "rationale"]
                                    }
                                },
                                "futurePredictions": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "potentialCondition": {"type": "STRING"},
                                            "timeframe": {"type": "STRING"},
                                            "probability": {"type": "NUMBER"},
                                            "rationale": {"type": "STRING"}
                                        },
                                        "required": ["potentialCondition", "timeframe", "probability", "rationale"]
                                    }
                                }
                            },
                            "required": ["currentThreats", "futurePredictions"]
                        },
                        "resourceOptimization": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "resourceType": {"type": "STRING"},
                                    "recommendedAllocation": {"type": "STRING"},
                                    "urgency": {"type": "STRING", "enum": ["baja", "media", "alta", "inmediata"]},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["resourceType", "recommendedAllocation", "urgency", "rationale"]
                            }
                        },
                        "scenarioSimulation": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "scenario": {"type": "STRING"},
                                    "predictedOutcome": {"type": "STRING"},
                                    "impactLevel": {"type": "STRING", "enum": ["positivo", "neutral", "negativo", "catastrófico"]}
                                },
                                "required": ["scenario", "predictedOutcome", "impactLevel"]
                            }
                        },
                        "preventiveMeasures": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "action": {"type": "STRING"},
                                    "priority": {"type": "STRING", "enum": ["baja", "media", "alta", "inmediata"]},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["action", "priority", "rationale"]
                            }
                        },
                        "riskCommunication": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "targetAudience": {"type": "STRING"},
                                    "keyMessage": {"type": "STRING"},
                                    "mediaChannels": {"type": "ARRAY", "items": {"type": "STRING"}}
                                },
                                "required": ["targetAudience", "keyMessage", "mediaChannels"]
                            }
                        },
                        "policyRecommendations": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "recommendation": {"type": "STRING"},
                                    "legalFramework": {"type": "STRING"},
                                    "implementationDifficulty": {"type": "STRING", "enum": ["baja", "media", "alta"]},
                                    "expectedOutcome": {"type": "STRING"}
                                },
                                "required": ["recommendation", "implementationDifficulty", "expectedOutcome"]
                            }
                        },
                        "epidemicProjection": {
                            "type": "OBJECT",
                            "properties": {
                                "timeUnit": {"type": "STRING"},
                                "dataPoints": {
                                    "type": "ARRAY",
                                    "items": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "time": {"type": "STRING"},
                                            "projectedCases": {"type": "NUMBER"}
                                        },
                                        "required": ["time", "projectedCases"]
                                    }
                                },
                                "description": {"type": "STRING"}
                            },
                            "required": ["timeUnit", "dataPoints", "description"]
                        },
                        "surveillanceAlerts": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "level": {"type": "STRING", "enum": ["info", "warning", "critical"]},
                                    "message": {"type": "STRING"},
                                    "trigger": {"type": "STRING"}
                                },
                                "required": ["level", "message", "trigger"]
                            }
                        },
                        "summary": {"type": "STRING"}
                    },
                    "required": ["regionProfile", "environmentalFactors", "populationVulnerability", "healthcareSystemImpact", "riskAnalysis", "resourceOptimization", "preventiveMeasures", "surveillanceAlerts", "summary"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=parts,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        response = await with_retry_and_timeout(run_epi, 240000, "Análisis Epidemiológico Macro", 1)
        raw_text = response.text or "{}"
        parsed_data = json.loads(clean_json(raw_text))

        on_step_update({
            "id": "epi-2",
            "type": "verdict",
            "title": "Vigilancia Macro Completada",
            "content": f"Se han modelado {len(parsed_data.get('scenarioSimulation', []))} escenarios y evaluado {len(parsed_data.get('populationVulnerability', []))} grupos vulnerables.",
            "confidence": 0.95,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        })

        return parsed_data
    except Exception as e:
        raise Exception(f"Fallo en el análisis epidemiológico macro: {e}")

async def run_immunology_analysis(
    topic: str,
    on_step_update,
    past_context: str = "",
    attached_files: Optional[List[Dict[str, Any]]] = None,
    region: Optional[str] = None,
    city: Optional[str] = None
) -> Dict[str, Any]:
    on_step_update({
        "id": "imm-1",
        "type": "analysis",
        "title": "Modelado Molecular Inmunológico",
        "content": f"Ejecutando modelado predictivo de interacciones antígeno-anticuerpo y respuesta celular para: {topic}...",
        "confidence": 0.9,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    })

    try:
        parts = []
        if attached_files:
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, on_step_update, idx)
                if resolved:
                    parts.append(resolved)

        literature_context = await gather_literature_context(topic, on_step_update, "imm", attached_files)

        prompt_text = (
            "Eres un Inmunólogo Computacional de Élite y Experto en Identidad Biológica.\n"
            f"Tu objetivo es realizar un análisis profundo a nivel micro (molecular y celular) de la información proporcionada: \"{topic}\".\n\n"
        )
        if attached_files and len(attached_files) > 0:
            prompt_text += f"Se han adjuntado {len(attached_files)} archivo(s). Asimila su contenido.\n"
        if past_context:
            prompt_text += f"\n=== BASE DE CONOCIMIENTO GLOBAL ===\n{past_context}\n"
        prompt_text += f"{literature_context}\n"

        prompt_text += (
            "Debes generar un reporte inmunológico estructurado.\n"
            "SECCIONES OBLIGATORIAS:\n"
            "1. Perfil Molecular (molecularProfile)\n"
            "2. Inmunidad Innata (innateImmunity)\n"
            "3. Reconocimiento de Antígenos (antigenRecognition)\n"
            "4. Respuesta Inmune (immuneResponse)\n"
            "5. Modelado Terapéutico (vaccineSimulation)\n"
            "6. Resumen (summary)\n\n"
            "Responde en ESPAÑOL en formato JSON estricto."
        )
        prompt_text = inject_video_scanning_protocol(prompt_text, attached_files)
        parts.append({"text": prompt_text})

        async def run_imm(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=parts
                )
            else:
                schema = {
                    "type": "OBJECT",
                    "properties": {
                        "molecularProfile": {
                            "type": "OBJECT",
                            "properties": {
                                "pathogenOrTarget": {"type": "STRING"},
                                "targetProteins": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "mutationRisk": {"type": "STRING", "enum": ["bajo", "medio", "alto", "crítico"]},
                                "virulenceFactors": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "crossReactivity": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "hlaAssociations": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "selfAntigenSimilarity": {"type": "STRING"}
                            },
                            "required": ["pathogenOrTarget", "targetProteins", "mutationRisk", "virulenceFactors"]
                        },
                        "innateImmunity": {
                            "type": "OBJECT",
                            "properties": {
                                "barrierStatus": {"type": "STRING"},
                                "complementSystem": {"type": "STRING"},
                                "phagocyticActivity": {"type": "STRING"},
                                "patternRecognition": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "rationale": {"type": "STRING"}
                            },
                            "required": ["barrierStatus", "complementSystem", "phagocyticActivity", "patternRecognition", "rationale"]
                        },
                        "antigenRecognition": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "epitopes": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "bindingAffinity": {"type": "STRING", "enum": ["débil", "moderada", "fuerte"]},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["epitopes", "bindingAffinity", "rationale"]
                            }
                        },
                        "immuneResponse": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "cellType": {"type": "STRING"},
                                    "activationLevel": {"type": "STRING"},
                                    "cytokineProfile": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "humoralResponse": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "antibodyIsotypes": {"type": "ARRAY", "items": {"type": "STRING"}},
                                            "neutralizationCapacity": {"type": "STRING"},
                                            "memoryBcellPotential": {"type": "STRING"}
                                        }
                                    },
                                    "cellularResponse": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "cytotoxicityLevel": {"type": "STRING"},
                                            "tCellPolarization": {"type": "STRING"},
                                            "exhaustionMarkers": {"type": "ARRAY", "items": {"type": "STRING"}}
                                        }
                                    },
                                    "rationale": {"type": "STRING"},
                                    "cytokineStormRisk": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "riskLevel": {"type": "STRING", "enum": ["bajo", "medio", "alto", "crítico"]},
                                            "predictedMarkers": {"type": "ARRAY", "items": {"type": "STRING"}},
                                            "clinicalImplications": {"type": "STRING"}
                                        },
                                        "required": ["riskLevel", "predictedMarkers", "clinicalImplications"]
                                    },
                                    "immuneEvasion": {
                                        "type": "OBJECT",
                                        "properties": {
                                            "mechanisms": {"type": "ARRAY", "items": {"type": "STRING"}},
                                            "impactOnMemory": {"type": "STRING"}
                                        },
                                        "required": ["mechanisms", "impactOnMemory"]
                                    }
                                },
                                "required": ["cellType", "activationLevel", "cytokineProfile", "rationale"]
                            }
                        },
                        "tumorSurveillance": {
                            "type": "OBJECT",
                            "properties": {
                                "neoantigenLoad": {"type": "STRING"},
                                "immuneCheckpointStatus": {"type": "STRING"},
                                "microenvironmentType": {"type": "STRING", "enum": ["inflamado", "excluido", "desierto"]},
                                "metabolicEnvironment": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "hypoxiaLevel": {"type": "STRING"},
                                        "lactateConcentration": {"type": "STRING"},
                                        "phStatus": {"type": "STRING"}
                                    }
                                },
                                "tertiaryLymphoidStructures": {
                                    "type": "OBJECT",
                                    "properties": {
                                        "presence": {"type": "BOOLEAN"},
                                        "maturity": {"type": "STRING"},
                                        "impact": {"type": "STRING"}
                                    }
                                },
                                "rationale": {"type": "STRING"}
                            },
                            "required": ["neoantigenLoad", "immuneCheckpointStatus", "microenvironmentType", "rationale"]
                        },
                        "autoimmunityRisk": {
                            "type": "OBJECT",
                            "properties": {
                                "targetOrgans": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "molecularMimicryPotential": {"type": "STRING"},
                                "toleranceBreakdownMechanism": {"type": "STRING"},
                                "riskLevel": {"type": "STRING", "enum": ["bajo", "medio", "alto", "crítico"]},
                                "rationale": {"type": "STRING"}
                            },
                            "required": ["targetOrgans", "molecularMimicryPotential", "toleranceBreakdownMechanism", "riskLevel", "rationale"]
                        },
                        "adaptiveSynapse": {
                            "type": "OBJECT",
                            "properties": {
                                "coStimulatorySignals": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "inhibitorySignals": {"type": "ARRAY", "items": {"type": "STRING"}},
                                "synapseStability": {"type": "STRING"},
                                "antigenPresentationEfficiency": {"type": "STRING"}
                            }
                        },
                        "vaccineSimulation": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "strategy": {"type": "STRING"},
                                    "predictedEfficacy": {"type": "NUMBER"},
                                    "escapeVariants": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "targetedTherapies": {"type": "ARRAY", "items": {"type": "STRING"}},
                                    "rationale": {"type": "STRING"}
                                },
                                "required": ["strategy", "predictedEfficacy", "escapeVariants", "rationale"]
                            }
                        },
                        "cohortImpact": {
                            "type": "OBJECT",
                            "properties": {
                                "herdImmunityThreshold": {"type": "STRING"},
                                "populationVulnerability": {"type": "STRING"},
                                "recommendedSurveillance": {"type": "STRING"}
                            },
                            "required": ["herdImmunityThreshold", "populationVulnerability", "recommendedSurveillance"]
                        },
                        "summary": {"type": "STRING"}
                    },
                    "required": ["molecularProfile", "innateImmunity", "antigenRecognition", "immuneResponse", "vaccineSimulation", "summary"]
                }
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=parts,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json",
                        response_schema=schema
                    )
                )

        response = await with_retry_and_timeout(run_imm, 240000, "Modelado Inmunológico", 1)
        raw_text = response.text or "{}"
        parsed_data = json.loads(clean_json(raw_text))

        on_step_update({
            "id": "imm-2",
            "type": "verdict",
            "title": "Modelado Completado",
            "content": f"Se han analizado {len(parsed_data.get('antigenRecognition', []))} perfiles de reconocimiento y {len(parsed_data.get('vaccineSimulation', []))} estrategias de inmunización.",
            "confidence": 0.95,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        })

        result = {"topic": topic}
        result.update(parsed_data)
        return result
    except Exception as e:
        raise Exception(f"Fallo en el modelado inmunológico: {e}")

async def continue_debate(
    session: Dict[str, Any],
    user_message: str,
    global_knowledge: str = "",
    region: Optional[str] = None,
    city: Optional[str] = None
) -> Dict[str, Any]:
    # Exclude last message
    chat_history = session.get("chatHistory") or session.get("chat_history") or []
    previous_history = chat_history[:-1] if chat_history else []
    chat_history_text = "\n\n".join([
        f"{m['role'].upper()}: {m['content']}" for m in previous_history if m.get("role") != "system"
    ])

    chat_parts = []
    has_document_context = False

    attached_files = session.get("attachedFiles") or session.get("attached_files") or []
    tribunal_result = session.get("tribunalResult") or session.get("tribunal_result") or {}

    if attached_files:
        if tribunal_result.get("documentAssimilation") or tribunal_result.get("documentSummary"):
            assim_text = json.dumps(tribunal_result.get("documentAssimilation"), indent=2) if tribunal_result.get("documentAssimilation") else ""
            sum_text = tribunal_result.get("documentSummary", "")
            chat_parts.append({
                "text": (
                    "=== RESUMEN Y ASIMILACIÓN DE DOCUMENTOS ADJUNTOS ===\n"
                    "El usuario adjuntó documentos originales para este debate. Para optimizar la memoria, aquí tienes la asimilación y el resumen extraídos previamente:\n\n"
                    f"Asimilación:\n{assim_text}\n\nResumen:\n{sum_text}\n\nÚsalo como fuente primaria de verdad para responder a sus preguntas y profundizar en el análisis."
                )
            })
            has_document_context = True
        else:
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, idx=idx)
                if resolved:
                    chat_parts.append(resolved)
            has_document_context = True

    mode = session.get("mode", "investigator")
    is_clinical = mode == "clinical"
    is_epidemiology_macro = mode == "epidemiology_macro"
    is_immunology = mode == "immunology"

    prompt_text = ""
    if is_clinical:
        clinical_result = session.get("clinicalResult") or session.get("clinical_result") or {}
        socratic_instruction = (
            "\n    INSTRUCCIÓN CRÍTICA: ESTÁS EN MODO SOCRÁTICO PARA ESTUDIANTES.\n"
            "    NO des la respuesta directa al usuario. Tu objetivo es guiarlo para que él mismo llegue a la conclusión mediante preguntas reflexivas, pistas clínicas y razonamiento paso a paso.\n"
            "    Felicítalo cuando acierte, corrige suavemente sus errores conceptuales y hazle la siguiente pregunta lógica en el abordaje del paciente."
            if session.get("isSocraticMode") or session.get("is_socratic_mode")
            else "\n    Responde al usuario de forma directa, concisa y basada en evidencia, como una interconsulta entre colegas médicos."
        )

        prompt_text = (
            "Eres un Médico Adscrito (Attending Physician) de Élite, experto en diagnóstico diferencial y razonamiento clínico estructurado.\n"
            f"Estás discutiendo un caso clínico con un usuario sobre el siguiente tema/paciente: \"{session.get('topic')}\"\n\n"
            f"Resumen Clínico previo: {clinical_result.get('summary')}\n"
            f"Diagnósticos Diferenciales: {json.dumps(clinical_result.get('differentialDiagnoses'))}\n"
            f"Banderas Rojas: {json.dumps(clinical_result.get('redFlags'))}\n"
            f"Plan de Abordaje: {json.dumps(clinical_result.get('workup'))}\n"
        )
        if has_document_context:
            prompt_text += "\n=== DOCUMENTO ADJUNTO ===\nEl usuario adjuntó un documento original. Úsalo como fuente primaria de verdad.\n"
        if global_knowledge:
            prompt_text += f"\n=== BASE DE CONOCIMIENTO GLOBAL ===\n{global_knowledge}\nATENCIÓN: La Base es solo una referencia estadística. NUNCA debe sobreescribir la evolución clínica del caso actual.\n"

        prompt_text += (
            "\n=== LEYES INQUEBRANTABLES DE RAZONAMIENTO CLÍNICO ===\n"
            "1. REGLA DE SUPREMACÍA DEL TEXTO Y ANTECEDENTES: Si el usuario te proporciona un diagnóstico explícito en el prompt original (ej. \"Toxoplasmosis in a 55-year-old female\"), una localización anatómica (ej. \"ganglios basales\") o hallazgos como \"lesiones hemorrágicas\", DEBES asumirlo como la VERDAD ABSOLUTA del caso. Ignorar el texto explícito para forzar un diagnóstico de la memoria es un sesgo de anclaje inaceptable.\n"
            "2. LÓGICA DE EVOLUCIÓN TEMPORAL (MÁQUINA DEL TIEMPO): En medicina, el factor tiempo es la prueba reina. Si el usuario te presenta explícitamente la evolución temporal, DEBES interpretar que la lesión final es la respuesta a un tratamiento o cicatrización.\n"
            "3. REGLA DE ANÁLISIS COMPARATIVO DE PANELES (SUSTRACCIÓN VISUAL CERO-TEXTO): Incluso si el usuario NO proporciona fechas o texto explícito, SI detectas múltiples paneles o imágenes (ej. Panel A y Panel B), TIENES LA OBLIGACIÓN MÁXIMA de compararlos visualmente. Si un panel muestra lesión activa (edema, realce) y otro panel muestra cicatriz (calcificación, resolución de edema) en la misma zona, DEBES deducir que hay una línea de tiempo biológica de curación. Prohibido analizarlos como cortes estáticos del mismo segundo.\n"
        )

        if region:
            prompt_text += f"\n=== CONTEXTO REGIONAL ===\nRegión/Guía: {region}{f' (Ciudad: {city})' if city else ''}.\nINSTRUCCIÓN CRÍTICA: Si sugieres tratamientos, ajústate estrictamente a las guías de esta región.\n"

        prompt_text += (
            f"\nHistorial de la conversación:\n{chat_history_text}\n\n"
            f"USUARIO: {user_message}\n"
            f"{socratic_instruction}\n\n"
            "Responde en ESPAÑOL en formato JSON."
        )

    elif is_epidemiology_macro:
        epi_result = session.get("epidemiologyResult") or session.get("epidemiology_result") or {}
        prompt_text = (
            "Eres un Epidemiólogo de Vanguardia y Experto en Vigilancia Sanitaria Inteligente a Nivel Macro.\n"
            f"Estás discutiendo un análisis de vigilancia con un usuario sobre el siguiente tema: \"{session.get('topic')}\"\n\n"
            f"Resumen Epidemiológico previo: {epi_result.get('summary')}\n"
            f"Perfil de la Región: {json.dumps(epi_result.get('regionProfile'))}\n"
            f"Dinámica del Brote: {json.dumps(epi_result.get('outbreakDynamics'))}\n"
            f"Medidas Preventivas: {json.dumps(epi_result.get('preventiveMeasures'))}\n"
            f"Alertas de Vigilancia: {json.dumps(epi_result.get('surveillanceAlerts'))}\n"
        )
        if has_document_context:
            prompt_text += "\n=== DOCUMENTO/IMAGEN ADJUNTO ===\nEl usuario adjuntó un archivo original. Úsalo como fuente primaria.\n"
        if global_knowledge:
            prompt_text += f"\n=== BASE DE CONOCIMIENTO GLOBAL ===\n{global_knowledge}\n"
        if region:
            prompt_text += f"\n=== CONTEXTO REGIONAL ===\nRegión/Guía: {region}{f' (Ciudad: {city})' if city else ''}.\n"

        prompt_text += (
            "\nHistorial de la conversación:\n{chat_history_text}\n\n"
            f"USUARIO: {user_message}\n\n"
            "Responde en ESPAÑOL en formato JSON."
        )

    elif is_immunology:
        imm_result = session.get("immunologyResult") or session.get("immunology_result") or {}
        prompt_text = (
            "Eres un Inmunólogo Computacional y Experto en Modelado Molecular de Inteligencia Artificial.\n"
            f"Estás discutiendo un análisis inmunológico a nivel micro con un usuario sobre el siguiente tema: \"{session.get('topic')}\"\n\n"
            f"Resumen Inmunológico previo: {imm_result.get('summary')}\n"
            f"Perfil Molecular: {json.dumps(imm_result.get('molecularProfile'))}\n"
            f"Modelado de Vacunas/Terapias: {json.dumps(imm_result.get('vaccineSimulation'))}\n"
        )
        if has_document_context:
            prompt_text += "\n=== DOCUMENTO/IMAGEN ADJUNTO ===\nEl usuario adjuntó un archivo. Úsalo como fuente primaria.\n"
        if global_knowledge:
            prompt_text += f"\n=== BASE DE CONOCIMIENTO GLOBAL ===\n{global_knowledge}\n"

        prompt_text += (
            "\nHistorial de la conversación:\n{chat_history_text}\n\n"
            f"USUARIO: {user_message}\n\n"
            "Responde en ESPAÑOL en formato JSON."
        )

    else: # Tribunal mode / investigator
        prompt_text = (
            "Eres el Tribunal Médico (compuesto por el Investigador y el Crítico Clínico).\n"
            f"Estás debatiendo con un usuario humano sobre el siguiente tema: \"{session.get('topic')}\"\n\n"
            f"Veredicto previo del tribunal: {tribunal_result.get('summary')}\n"
            f"Hipótesis Sobrevivientes: {json.dumps(tribunal_result.get('survivingHypotheses'))}\n"
        )
        clin_result = session.get("clinicalResult") or session.get("clinical_result") or {}
        if clin_result.get("redTeamAudit"):
            prompt_text += f"\n=== AUDITORÍA DEL RED TEAM ===\n{json.dumps(clin_result['redTeamAudit'])}\nINSTRUCCIÓN CRÍTICA: El Red Team detectó sesgos. Pivota si el usuario se alinea con sus críticas.\n"

        if has_document_context:
            prompt_text += "\n=== DOCUMENTO ADJUNTO ===\nEl usuario adjuntó un archivo. Úsalo como fuente primaria.\n"
        if global_knowledge:
            prompt_text += f"\n=== BASE DE CONOCIMIENTO GLOBAL ===\n{global_knowledge}\n"

        prompt_text += (
            "\nHistorial de la conversación:\n{chat_history_text}\n\n"
            f"USUARIO: {user_message}\n\n"
            "Responde en ESPAÑOL en formato JSON."
        )

    prompt_text = inject_video_scanning_protocol(prompt_text, attached_files)
    chat_parts.append({"text": prompt_text})

    async def run_chat(ai):
        if isinstance(ai, OpenRouterWrapper):
            return await ai.models.generate_content(
                model=get_active_model(),
                contents=chat_parts
            )
        else:
            schema = {
                "type": "OBJECT",
                "properties": {
                    "content": {"type": "STRING"},
                    "connections": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "pastTopic": {"type": "STRING"},
                                "extractedInsight": {"type": "STRING"},
                                "applicationToCurrent": {"type": "STRING"},
                                "connectionType": {"type": "STRING", "enum": ["directa", "serendipia", "documento"]}
                            },
                            "required": ["pastTopic", "extractedInsight", "applicationToCurrent", "connectionType"]
                        }
                    },
                    "newDiscovery": {
                        "type": "OBJECT",
                        "properties": {
                            "etiqueta_diagnostica": {"type": "STRING"},
                            "hallazgo": {"type": "STRING"}
                        },
                        "required": ["etiqueta_diagnostica", "hallazgo"]
                    },
                    "cognitiveAutopsy": {
                        "type": "OBJECT",
                        "properties": {
                            "hipotesis_inicial": {"type": "STRING"},
                            "trampa_clinica": {"type": "STRING"},
                            "evidencia_correccion": {"type": "STRING"},
                            "etiqueta_diagnostica": {"type": "STRING"},
                            "verdad_revelada": {"type": "STRING"},
                            "aforismo_medico": {"type": "STRING"}
                        },
                        "required": ["hipotesis_inicial", "trampa_clinica", "evidencia_correccion", "etiqueta_diagnostica", "verdad_revelada", "aforismo_medico"]
                    }
                },
                "required": ["content", "connections"]
            }
            return await ai.aio.models.generate_content(
                model=get_active_model(),
                contents=chat_parts,
                config=types.GenerateContentConfig(
                    safety_settings=medical_safety_settings,
                    response_mime_type="application/json",
                    response_schema=schema
                )
            )

    response = await with_retry_and_timeout(run_chat, 120000, "Chat", 1)
    raw_text = response.text or "{}"
    parsed_data = json.loads(clean_json(raw_text))

    import time
    return {
        "id": str(int(time.time() * 1000)),
        "role": "assistant",
        "content": parsed_data.get("content", ""),
        "timestamp": int(time.time() * 1000),
        "connections": parsed_data.get("connections", []),
        "newDiscovery": parsed_data.get("newDiscovery"),
        "cognitiveAutopsy": parsed_data.get("cognitiveAutopsy")
    }

async def expand_hypothesis(
    hypothesis: Dict[str, Any],
    action: str, # 'ensayo' | 'compuestos'
    global_knowledge: str = "",
    session: Optional[Dict[str, Any]] = None,
    region: Optional[str] = None,
    city: Optional[str] = None
) -> str:
    prompt = (
        f"Diseña un ensayo clínico teórico (Fases, Criterios de Inclusión, Biomarcadores, Endpoints) para esta hipótesis: \"{hypothesis.get('statement')}\"\nRazón original: {hypothesis.get('rationale')}"
        if action == "ensayo"
        else f"Propón 3 compuestos químicos (teóricos o existentes) o vías de administración novedosas para abordar esta hipótesis: \"{hypothesis.get('statement')}\"\nRazón original: {hypothesis.get('rationale')}"
    )

    parts = []
    has_document_context = False

    attached_files = session.get("attachedFiles") or session.get("attached_files") if session else []
    tribunal_result = session.get("tribunalResult") or session.get("tribunal_result") or {} if session else {}

    if attached_files:
        if tribunal_result.get("documentAssimilation") or tribunal_result.get("documentSummary"):
            assim_text = json.dumps(tribunal_result.get("documentAssimilation"), indent=2) if tribunal_result.get("documentAssimilation") else ""
            sum_text = tribunal_result.get("documentSummary", "")
            parts.append({
                "text": (
                    "=== RESUMEN Y ASIMILACIÓN DE DOCUMENTOS ADJUNTOS ===\n"
                    "El usuario adjuntó documentos originales para este debate. Para optimizar la memoria, aquí tienes la asimilación y el resumen extraídos previamente:\n\n"
                    f"Asimilación:\n{assim_text}\n\nResumen:\n{sum_text}\n\nÚsalo como fuente primaria de verdad para responder a sus preguntas y profundizar en el análisis."
                )
            })
            has_document_context = True
        else:
            for idx, file in enumerate(attached_files):
                resolved = await resolve_attached_file_data(file, idx=idx)
                if resolved:
                    parts.append(resolved)
            has_document_context = True

    final_text = ""
    if has_document_context:
        final_text += "=== DOCUMENTO ADJUNTO ===\nEl usuario adjuntó un documento original. Úsalo como fuente primaria de verdad para responder a sus preguntas y profundizar en el análisis.\n\n"
    if global_knowledge:
        final_text += f"=== BASE DE CONOCIMIENTO GLOBAL ===\n{global_knowledge}\n\nUsa este conocimiento para informar tu diseño o propuesta.\n\n"
    if region:
        final_text += f"=== CONTEXTO REGIONAL ===\nRegión/Guía: {region}{f' (Ciudad: {city})' if city else ''}.\nTen en cuenta este contexto regional si es relevante.\n\n"

    final_text += f"{prompt}\n\nResponde en ESPAÑOL con un enfoque altamente científico, estructurado y detallado. Actúa como el Investigador Principal. Utiliza formato Markdown profesional. Usa SIEMPRE saltos de línea dobles para separar secciones y subtítulos, evitando viñetas en la misma línea."
    parts.append({"text": final_text})

    async def run_expand(ai):
        if isinstance(ai, OpenRouterWrapper):
            return await ai.models.generate_content(
                model=get_active_model(),
                contents=parts
            )
        else:
            return await ai.aio.models.generate_content(
                model=get_active_model(),
                contents=parts,
                config=types.GenerateContentConfig(safety_settings=medical_safety_settings)
            )

    response = await with_retry_and_timeout(run_expand, 30000, "Expansión", 1)
    return response.text or ""

async def run_delta_analysis(
    patient: Dict[str, Any],
    reports: List[Dict[str, Any]],
    on_step_update
) -> Dict[str, Any]:
    on_step_update({
        "id": "delta-1",
        "type": "analysis",
        "title": "Análisis Longitudinal",
        "content": f"Procesando {len(reports)} reportes históricos para el paciente {patient.get('name')}...",
        "confidence": 0.9,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    })

    try:
        from datetime import datetime
        history_summary = []
        for r in reports:
            # Safe date parse
            try:
                date_str = datetime.fromtimestamp(r["date"] / 1000.0).strftime('%d/%m/%Y')
            except:
                date_str = str(r.get("date", ""))
            
            history_summary.append({
                "fecha": date_str,
                "tipo": r.get("type"),
                "tema": r.get("topic"),
                "resumen": r.get("summary")
            })

        prompt_text = (
            "Eres un Médico Especialista en Análisis Longitudinal y Seguimiento Clínico.\n"
            "Tu objetivo es analizar el historial médico de un paciente y generar un reporte de evolución (Análisis Delta).\n\n"
            "=== DATOS DEL PACIENTE ===\n"
            f"Nombre: {patient.get('name')}\n"
            f"DNI: {patient.get('dni')}\n"
            f"Edad: {patient.get('age')}\n"
            f"Ciudad: {patient.get('city')}\n\n"
            f"=== HISTORIAL DE REPORTES (Ordenados del más reciente al más antiguo) ===\n"
            f"{json.dumps(history_summary, indent=2)}\n\n"
            "Instrucciones:\n"
            "1. Compara el estado actual (reporte más reciente) con los estados pasados.\n"
            "2. Identifica qué ha mejorado (improvements), qué ha empeorado (worsenings) y qué se mantiene estable (stableConditions).\n"
            "3. Extrae correlaciones entre tratamientos y efectos (treatmentCorrelations).\n"
            "4. REGLA DE BIOMARCADORES PARA TRAYECTORIA (trajectoryData): Si los reportes pasados incluyen datos numéricos REALES (ej. 'tumor de 4 cm', 'leucocitos 15,000'), tienes ESTRICTAMENTE PROHIBIDO usar una escala genérica de 1 a 10. DEBES graficar ese biomarcador exacto (ej. metric: 'Tamaño tumoral (cm)'). Solo si TODO es subjetivo, usarás la escala 'Severidad (1-10)'.\n"
            "5. Hitos Evolutivos (milestone): Asigna a cada punto de la gráfica una cadena corta de texto 'milestone' que resuma el hito clínico.\n"
            "6. Análisis de Trayectoria (trajectoryAnalysis): Explica brevemente el porqué de la curva.\n"
            "7. Priorización de Intervención (interventionPriority): Identifica la \"Acción Cero\" y su justificación.\n"
            "8. Score de Sepsis (sepsisRiskScore): Riesgo de sepsis (qSOFA/SIRS).\n"
            "9. Genera alertas predictivas (predictiveAlerts).\n"
            "10. Escribe un resumen ejecutivo (executiveSummary).\n\n"
            f"Responde en ESPAÑOL en formato JSON estricto con la siguiente estructura:\n"
            "{\n"
            f"  \"patientDni\": \"{patient.get('dni')}\",\n"
            f"  \"patientName\": \"{patient.get('name')}\",\n"
            "  \"comparisonPeriod\": \"ej. Enero 2023 - Octubre 2023\",\n"
            "  \"improvements\": [\"mejora 1\", \"mejora 2\"],\n"
            "  \"worsenings\": [\"empeoramiento 1\"],\n"
            "  \"stableConditions\": [\"condición estable 1\"],\n"
            "  \"treatmentCorrelations\": [\n"
            "    { \"treatment\": \"Fármaco X\", \"effect\": \"Reducción de dolor\", \"timeline\": \"A las 2 semanas\" }\n"
            "  ],\n"
            "  \"trajectoryData\": [\n"
            "    { \"date\": \"2023-01-01\", \"metric\": \"Tamaño Tumoral (cm)\", \"value\": 2.5, \"milestone\": \"Diagnóstico inicial\" },\n"
            "    { \"date\": \"2023-10-01\", \"metric\": \"Tamaño Tumoral (cm)\", \"value\": 4.0, \"milestone\": \"Fracaso a corticoide, nueva lesión\" }\n"
            "  ],\n"
            "  \"trajectoryAnalysis\": \"El aumento del tamaño se correlaciona con la ineficacia del tratamiento primario...\",\n"
            "  \"interventionPriority\": {\n"
            "    \"actionZero\": \"Acción prioritaria\",\n"
            "    \"rationale\": \"Justificación\",\n"
            "    \"urgency\": \"inmediata\"\n"
            "  },\n"
            "  \"sepsisRiskScore\": {\n"
            "    \"score\": \"Valor\",\n"
            "    \"interpretation\": \"Interpretación clínica\",\n"
            "    \"trend\": \"estable\"\n"
            "  },\n"
            "  \"predictiveAlerts\": [\"alerta 1\"],\n"
            "  \"executiveSummary\": \"Resumen empático...\"\n"
            "}"
        )

        async def run_delta(ai):
            if isinstance(ai, OpenRouterWrapper):
                return await ai.models.generate_content(
                    model=get_active_model(),
                    contents=prompt_text
                )
            else:
                return await ai.aio.models.generate_content(
                    model=get_active_model(),
                    contents=prompt_text,
                    config=types.GenerateContentConfig(
                        safety_settings=medical_safety_settings,
                        response_mime_type="application/json"
                    )
                )

        response = await with_retry_and_timeout(run_delta, 30000, "Análisis Delta", 1)
        raw_text = response.text or "{}"
        parsed_data = json.loads(clean_json(raw_text))

        result = {
            "patientDni": parsed_data.get("patientDni") or patient.get("dni"),
            "patientName": parsed_data.get("patientName") or patient.get("name"),
            "comparisonPeriod": parsed_data.get("comparisonPeriod") or "No especificado",
            "improvements": parsed_data.get("improvements") if isinstance(parsed_data.get("improvements"), list) else [],
            "worsenings": parsed_data.get("worsenings") if isinstance(parsed_data.get("worsenings"), list) else [],
            "stableConditions": parsed_data.get("stableConditions") if isinstance(parsed_data.get("stableConditions"), list) else [],
            "treatmentCorrelations": parsed_data.get("treatmentCorrelations") if isinstance(parsed_data.get("treatmentCorrelations"), list) else [],
            "trajectoryData": parsed_data.get("trajectoryData") if isinstance(parsed_data.get("trajectoryData"), list) else [],
            "trajectoryAnalysis": parsed_data.get("trajectoryAnalysis"),
            "interventionPriority": parsed_data.get("interventionPriority"),
            "sepsisRiskScore": parsed_data.get("sepsisRiskScore"),
            "predictiveAlerts": parsed_data.get("predictiveAlerts") if isinstance(parsed_data.get("predictiveAlerts"), list) else [],
            "executiveSummary": parsed_data.get("executiveSummary") or "No se pudo generar el resumen."
        }

        on_step_update({
            "id": "delta-2",
            "type": "verdict",
            "title": "Análisis Completado",
            "content": f"Se ha generado el reporte de evolución para {patient.get('name')}.",
            "confidence": 0.95,
            "timestamp": int(asyncio.get_event_loop().time() * 1000)
        })

        return result
    except Exception as e:
        raise Exception(f"Fallo en el Análisis Delta: {e}")

async def format_clinical_text(raw_text: str) -> str:
    ai = get_random_ai_client()
    model_name = get_active_model()

    prompt = (
        "Actúa como un Secretario Médico Experto. "
        "Tu tarea es tomar el siguiente texto \"crudo\" dictado por voz de un médico y organizarlo, darle formato profesional y estructurarlo adecuadamente utilizando jerga médica correcta.\n\n"
        "El texto crudo puede estar desorganizado, tener muletillas, o estar en un bloque denso. "
        "Organízalo lógicamente en viñetas y secciones claras (ej. \"Motivo de Consulta\", \"Hallazgos\", \"Síntomas\", \"Datos Relevantes\", \"Signos Vitales\", etc., dependiendo de la información presente). "
        "NO inventes datos, solo organiza, pule la redacción y dale un formato elegante y fácil de leer.\n\n"
        "TEXTO CRUDO A ORGANIZAR:\n"
        "\"\"\"\n"
        f"{raw_text}\n"
        "\"\"\"\n\n"
        "Responde SOLO con el texto estructurado, sin introducciones ni comentarios adicionales."
    )

    try:
        if isinstance(ai, OpenRouterWrapper):
            response = await ai.models.generate_content(
                model=model_name,
                contents=prompt,
                config={"temperature": 0.2}
            )
        else:
            response = await ai.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    safety_settings=medical_safety_settings
                )
            )
        return response.text or ""
    except Exception as e:
        raise Exception(f"Fallo en la organización del texto clínico: {e}")

async def audit_redundancy_agent(new_article: Dict[str, Any], existing_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    print(f"[Agente Auditor] Auditando artículo: {new_article.get('title')} contra {len(existing_articles)} existentes.")

    articles_text = ""
    if len(existing_articles) == 0:
        articles_text = "No hay artículos similares. Es conocimiento 100% nuevo."
    else:
        for idx, art in enumerate(existing_articles):
            articles_text += (
                f"\n[Artículo Existente {idx + 1}]\n"
                f"Título: {art.get('title')}\n"
                f"Patología: {art.get('pathology') or 'Desconocida'}\n"
                f"Contenido/Abstract: {str(art.get('content_text', ''))[:800]}...\n"
            )

    prompt_text = (
        "Eres el Agente Auditor de Redundancia de una Biblioteca Médica de Élite.\n"
        "Tu misión es comparar un \"Artículo Nuevo\" entrante contra una lista de \"Artículos Existentes\" en la base de datos principal, para determinar si el artículo nuevo aporta valor clínico real o si es simple basura redundante.\n\n"
        "=== ARTÍCULO NUEVO (A EVALUAR) ===\n"
        f"Título: {new_article.get('title') or 'Sin título'}\n"
        f"Patología / Tema: {new_article.get('topic') or 'Desconocido'}\n"
        f"Fuente: {new_article.get('source') or 'Desconocida'}\n"
        "Resumen / Contenido:\n"
        f"{new_article.get('content') or 'Sin contenido'}\n\n"
        f"=== ARTÍCULOS EXISTENTES (EN LA BASE DE DATOS) ===\n{articles_text}\n\n"
        "INSTRUCCIONES DE ANÁLISIS:\n"
        "1. Evalúa si el \"Artículo Nuevo\" trata exactamente de la misma patología, mismo enfoque, y mismas conclusiones clínicas que alguno de los \"Artículos Existentes\".\n"
        "2. Busca \"Diferencias Clínicas de Valor\": ¿El artículo nuevo tiene una población diferente? ¿Habla de una complicación distinta? ¿Plantea un diagnóstico diferencial nuevo?\n"
        "3. Genera un Veredicto Final (\"Aprobar\" o \"Rechazar\").\n\n"
        "Responde ESTRICTAMENTE en este formato JSON:\n"
        "{\n"
        "  \"coincidencias\": \"Explica brevemente qué información del artículo nuevo YA EXISTE en los artículos de la base de datos.\",\n"
        "  \"diferencias_valor\": \"Explica qué información es ÚNICA o NOVEDOSA en el artículo nuevo que justifica su inyección.\",\n"
        "  \"veredicto\": \"Aprobar\" o \"Rechazar\",\n"
        "  \"razon_veredicto\": \"Justificación concisa de 1-2 líneas de tu veredicto.\"\n"
        "}\n"
        "No incluyas markdown ```json ni nada fuera del objeto JSON."
    )

    try:
        ai = get_random_ai_client(force_google=True)
        if isinstance(ai, OpenRouterWrapper):
            response = await ai.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_text,
                config={"temperature": 0.2}
            )
        else:
            response = await ai.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt_text,
                config=types.GenerateContentConfig(
                    safety_settings=medical_safety_settings,
                    temperature=0.2
                )
            )
        text = response.text or ""
        clean_json_str = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json_str)
    except Exception as e:
        print(f"[Agente Auditor] Falló la evaluación: {e}")
        return {
            "coincidencias": "Error en la evaluación de la IA.",
            "diferencias_valor": "No se pudo determinar.",
            "veredicto": "Rechazar",
            "razon_veredicto": f"Fallo de comunicación con Gemini: {e}. Se recomienda revisión manual."
        }
