import os
import datetime
import asyncio
from typing import Dict, Any, List, Optional
from supabase import create_client, Client

from .literature import search_europe_pmc
from .radiopaedia import search_radiopaedia
from .gemini_core import (
    generate_embedding,
    extract_visual_phenotype,
    generate_optimized_search_query,
    translate_to_spanish_medical,
    translate_and_tag_literature,
    classify_literature
)

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL", "https://dominio-faltante.supabase.co")
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "llave-faltante-ey")
supabase_admin: Client = create_client(supabase_url, supabase_key)

async def check_redundancy(embedding: List[float]) -> bool:
    """
    Escudo de Redundancia: Verifica si el conocimiento ya fue asimilado previamente.
    """
    try:
        # DETECCIÓN DE DEGRADACIÓN SILENCIOSA
        # Si el embedding es el de emergencia (comienza con 0.001), saltamos el chequeo
        # para evitar colisiones matemáticas (falsos positivos del 100%).
        if embedding and len(embedding) > 1 and embedding[0] == 0.001 and embedding[1] == 0.001:
            print("[Shadow Librarian] ⚠️ Vector matemático degradado detectado. Saltando escudo de redundancia para permitir revisión humana.")
            return False

        # Verificar en Cuarentena usando la función RPC
        res = supabase_admin.rpc("match_knowledge_staging", {
            "query_embedding": embedding,
            "match_threshold": 0.90,  # Alta similitud requerida
            "match_count": 1
        }).execute()

        if res.data and len(res.data) > 0:
            return True

        return False
    except Exception as e:
        print(f"[Shadow Librarian] Error al verificar redundancia: {e}")
        # En caso de error, asumimos que no es duplicado para no frenar la asimilación
        return False

async def run_shadow_librarian(job: Dict[str, Any]):
    """
    El Shadow Librarian (Bibliotecario en la Sombra).
    Proceso asíncrono que busca, asimila y pone en cuarentena conocimientos médicos.
    """
    try:
        print("[Shadow Librarian] Iniciando asimilación en background...")

        suspected_pathology = job.get("suspectedPathology", "").strip()
        patient_context = job.get("patientContext", "").strip()
        attached_files = job.get("attachedFiles", [])
        original_topic = job.get("originalTopic", "").strip()

        # 1. Determinar el "Faro" o diagnosticar a ciegas
        search_topic = suspected_pathology

        if not search_topic:
            print("[Shadow Librarian] No hay Faro. Extrayendo fenotipo visual para deducción autónoma (Ruta B)...")
            visual_findings = await extract_visual_phenotype(attached_files, patient_context)
            if visual_findings:
                # Generar una sospecha basada en el fenotipo
                search_topic = visual_findings[:200]
            else:
                search_topic = patient_context[:200]

        if not search_topic:
            print("[Shadow Librarian] ⚠️ No hay datos suficientes para buscar. Abortando.")
            return

        print(f"[Shadow Librarian] Tópico de búsqueda (Ground Truth): \"{search_topic[:50]}...\"")

        # 2. Escudo de Redundancia (Evitar duplicados)
        topic_vector = await generate_embedding(search_topic)
        is_duplicate = await check_redundancy(topic_vector)
        if is_duplicate:
            print("[Shadow Librarian] 🛑 Redundancia detectada. Este conocimiento ya existe o está en cuarentena. Abortando asimilación.")
            return

        # 3. Generar Query Optimizado Multimodal (Context-Aware Search)
        print("[Shadow Librarian] 🔤 Generando Plan de Búsqueda Multimodal (Enrutador Cognitivo)...")
        search_plan = await generate_optimized_search_query(search_topic, patient_context)
        pmc_query = search_plan.get("pmc_query", search_topic)
        requires_imaging = search_plan.get("requires_imaging", False)
        radiopaedia_query = search_plan.get("radiopaedia_query", "")

        print(f"[Shadow Librarian] Plan: PMC -> \"{pmc_query}\" | Radiopaedia -> \"{radiopaedia_query if requires_imaging else 'NO REQUERIDA'}\"")

        # 4. Ejecutar búsqueda Dual Asíncrona Tolerante a Fallos
        print("[Shadow Librarian] 📚 Ejecutando minería de datos Dual...")
        
        fetch_tasks = []

        # Agente A: Europe PMC
        async def pmc_task_func():
            try:
                results = await search_europe_pmc(pmc_query, 3)
                if not results:
                    raise Exception("No PMC results")
                anchor = results[0]
                title = await translate_to_spanish_medical(anchor.get("title", search_topic))
                abstract = await translate_and_tag_literature(
                    anchor.get("abstract", "Sin abstract."),
                    suspected_pathology or search_topic
                )
                original_url = anchor.get("fullTextUrl") or f"https://europepmc.org/search?query={pmc_query}"
                abstract += f"\n\n<!-- SOURCE_URL: {original_url} -->"
                return {"type": "pmc", "title": title, "abstract": abstract, "source": "Europe PMC"}
            except Exception as e:
                print(f"[Shadow Librarian] Falló Agente Europe PMC: {e}")
                raise e

        fetch_tasks.append(pmc_task_func())

        # Agente B: Radiopaedia
        if requires_imaging and radiopaedia_query:
            async def rad_task_func():
                try:
                    result = await search_radiopaedia(radiopaedia_query)
                    if not result:
                        raise Exception("No Radiopaedia results")
                    title = await translate_to_spanish_medical(result.get("title", ""))
                    abstract = await translate_and_tag_literature(
                        result.get("abstract", ""),
                        suspected_pathology or search_topic
                    )
                    original_url = result.get("url") or f"https://radiopaedia.org/search?q={radiopaedia_query}"
                    abstract += f"\n\n<!-- SOURCE_URL: {original_url} -->"
                    return {"type": "radiopaedia", "title": title, "abstract": abstract, "source": "Radiopaedia"}
                except Exception as e:
                    print(f"[Shadow Librarian] Falló Agente Radiopaedia: {e}")
                    raise e
            
            fetch_tasks.append(rad_task_func())

        # Run tasks concurrently using gather with return_exceptions=True
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        successful_extractions = []
        for r in results:
            if isinstance(r, dict):
                successful_extractions.append(r)
            elif isinstance(r, Exception):
                pass # Already logged inside functions

        if not successful_extractions:
            print("[Shadow Librarian] ❌ Ambos agentes fallaron o no encontraron resultados relevantes.")
            return

        # 5 & 6. Procesar cada extracción exitosa, clasificarla y enviarla a Cuarentena
        for extraction in successful_extractions:
            print(f"[Shadow Librarian] Clasificando literatura de {extraction['source']}...")
            classification = await classify_literature(extraction["title"], extraction["abstract"])
            macro_category = classification.get("macro_category", "Medicina Interna")
            micro_pathology = classification.get("micro_pathology", "General")
            print(f"[Shadow Librarian] Clasificación: {macro_category} / {micro_pathology}")

            print(f"[Shadow Librarian] Generando embeddings para: {extraction['title']}")
            embedding_text = f"{extraction['title']}. {extraction['abstract']}"
            embedding_values = await generate_embedding(embedding_text)

            print(f"[Shadow Librarian] 📦 Empaquetando y enviando a Cuarentena ({extraction['source']})...")
            
            staging_payload = {
                "topic": original_topic or search_topic,
                "title": extraction["title"],
                "macro_category": macro_category,
                "micro_pathology": micro_pathology,
                "content": extraction["abstract"],
                "source": extraction["source"],
                "status": "pending_review",
                "embedding": embedding_values,  # Supabase-py parses List[float] to array/vector automatically
                "created_at": datetime.datetime.utcnow().isoformat()
            }

            try:
                res = supabase_admin.from_("knowledge_staging").insert([staging_payload]).execute()
                print(f"[Shadow Librarian] ✅ Ingesta exitosa ({extraction['source']}). Conocimiento en espera de revisión.")
            except Exception as save_err:
                print(f"[Shadow Librarian] Error al guardar {extraction['source']} en Cuarentena: {save_err}")

    except Exception as error:
        print(f"[Shadow Librarian] Fallo crítico durante la asimilación: {error}")
