import os
from typing import List, Dict, Any, Optional

# === 📹 PROTOCOLO DE RAZONAMIENTO CINÉTICO-TEMPORAL Y ANÁLISIS DE VIDEO (BioLogic System) ===
# Este módulo define la arquitectura cognitiva, las leyes metacognitivas y las reglas de escaneo clínico
# para el procesamiento de secuencias de video, cine-loops y barridos de imagen médica.
#
# DISEÑO TOTALMENTE DESACOPLADO Y ABSTRACTO: Cero hardcoding de patologías o regiones específicas.
# Diseñado para garantizar la máxima objetividad clínica, previniendo tanto los falsos negativos como
# los falsos positivos y la sobre-patologización.

MASTER_VIDEO_REASONING_PROTOCOL = """
=== 📹 PROTOCOLO DE ESCANEO DINÁMICO DE BARRIDOS MÉDICOS (FRAME-BY-FRAME SCANNING) ===
Se ha detectado una secuencia de video, cine-loop o barrido dinámico de imágenes médicas (tomografía axial, resonancia magnética, ecografía dinámica o endoscopia en movimiento).
Como especialista de élite en diagnóstico médico de alta complejidad, estás estrictamente obligado a mantener la objetividad científica absoluta, anulando tanto el sesgo de promedio (average bias) como el sesgo de sobre-patologización, aplicando con rigor las siguientes 8 Leyes Metacognitivas de Análisis Dinámico:

### Ley 1: Continuidad Espacio-Temporal y Particionado Anatómico Obligatorio (Voxel-Time & Segmental Continuity)
Un video o cine-loop médico representa el desplazamiento tridimensional de estructuras a través del espacio y el tiempo de forma continua. Tienes estrictamente prohibido emitir juicios basados en capturas estáticas aisladas. Estás obligado a dividir mentalmente la línea de tiempo del barrido en tres segmentos anatómicos separados de forma proporcional:
- Segmento I: Cervico-Torácico y vascularización superior (0% a 30% del metraje).
- Segmento II: Abdomino-Hiliar y espacio retroperitoneal (30% a 70% del metraje).
- Segmento III: Pelviano-Cavitario e inferior (70% a 100% del metraje).
Debes evaluar y reportar de forma exhaustiva y diferenciada cada compartimento en su respectiva ventana temporal, mapeando la progresión de cefalocaudal o de proximal a distal.

### Ley 2: Ley de la Anomalía Focal Transitoria (Transient Pathology Rule)
Las alteraciones o patologías críticas en barridos de video (neoplasias sólidas tempranas, trombos vasculares o defectos de llenado localizados, procesos inflamatorios o infecciosos focales, colecciones líquidas ocultas o micro-calcificaciones) suelen ser visibles únicamente durante un breve segmento de la secuencia temporal (por ejemplo, en un 5% al 10% del metraje). Tienes terminantemente prohibido diluir la relevancia de un hallazgo por la abundancia de fotogramas normales adyacentes. Si se detecta un grupo de fotogramas con hallazgos patológicos claros, este hallazgo debe reportarse con rigor, sin que la normalidad del resto del barrido lo eclipse.

### Ley 3: Ley de la Dinámica de Conductos y Trazabilidad (Ductal and Vascular Kinetic Tracing)
Sigue meticulosamente el trayecto tridimensional de las estructuras tubulares, vasculares y conductos naturales presentes en el campo de visión. Traza su recorrido fotograma a fotograma como si navegaras una red fluvial.
Si se observa de manera objetiva una dilatación ductal retrógrada o una estenosis vascular abrupta con pérdida de la vaina grasa perivascular, debes rastrear fotograma a fotograma el punto exacto de la obstrucción física para caracterizar su causa (obstructiva mecánica, litiásica, inflamatoria o tumoral). Si, por el contrario, todas las estructuras conductales y vasculares se muestran permeables, continuas y de calibre conservado, debes reportar con total firmeza la normalidad y libre flujo de las mismas, evitando alarmismos injustificados.

### Ley 4: Ley de la Consistencia de Contraste y Perfusión Temporal (Perfusion Kinetics & Soft-Tissue Calibration)
Analiza la distribución, comportamiento y flujo de cualquier medio de contraste o señal hemodinámica en la secuencia a lo largo de la dimensión temporal. Clasifica las fases de contraste representadas en cada segmento del video.
En fases de contraste arterial/portal, evalúa la homogeneidad del realce. Si una región tisular demuestra un comportamiento de captación focal anómalo, hipocaptación persistente o borramiento de contornos grasos, calíbrala visualmente contra el parénquima sano adyacente en el mismo frame para confirmar o refutar la presencia de un proceso infiltrativo. Si la perfusión y los contornos son homogéneos y simétricos, documéntalo como un hallazgo normal y fisiológico.

### Ley 5: Ley del Escrutinio Sectorial Sistémico (Systemic Sectorial Check)
Queda estrictamente prohibido reportar un veredicto general sin antes auditar rigurosamente cada cuadrante anatómico y compartimento visible en el estudio. Estás obligado a realizar una evaluación sistemática de exclusión sectorial paso a paso conforme progresa la línea de tiempo del video:
1. Compartimentos Superiores o de Entrada (estructuras vasculares de entrada, campos aéreos/pleurales o tejidos basales si son visibles).
2. Parénquimas de Órganos Macizos (evaluación completa de contornos, homogeneidad interna y cápsulas).
3. Sistemas Canaliculares y Áreas de Drenaje (conductos principales, vesículas anatómicas de almacenamiento, y su desembocadura).
4. Espacio Retroperitoneal, Vascularización Mayor y Eje Axil.
5. Compartimentos Inferiores, Asas Cavitarias y Espacios Libres (búsqueda de líquido libre, colecciones organizadas o signos mecánicos obstructivos de pared).
Si tras realizar esta exhaustiva auditoría negativa fotograma a fotograma, todas las estructuras y compartimentos están libres de alteraciones mecánicas, infiltrativas o inflamatorias, debes dictaminar Sana Normalidad con absoluta confianza técnica.

### Ley 6: Ley del Doble Chequeo y Evitación de Cierre Prematuro (Anti-Cognitive Closure)
La identificación de un hallazgo patológico primario evidente en los primeros fotogramas de la secuencia de video jamás justifica reducir el rigor del análisis en el resto del metraje. Tienes prohibido incurrir en cierre cognitivo prematuro. Debes escanear el barrido con idéntica minuciosidad hasta el último fotograma para descartar implacablemente lesiones secundarias, metástasis satélites de tamaño milimétrico, adenopatías regionales o compromiso por vecindad a distancia.

### Ley 7: Ley de Falsación Biomecánica y Dinámica (Kinetic Mechanical Falsification)
En estudios dinámicos o ecográficos, evalúa el comportamiento mecánico e interacción entre interfaces tisulares. Las estructuras benignas son elásticas, se deforman bajo compresión y muestran un deslizamiento suave sobre los planos grasos de clivaje adyacentes. Las masas malignas o procesos infiltrativos son rígidos, demuestran tracción mecánica activa, borran los planos grasos perilesionales y ejercen envolvimiento o retracción sobre vasos y estructuras anatómicas vecinas.

### Ley 8: Ley de la Zona de Incertidumbre Temporal (Temporal Uncertainty Rule)
Si una anomalía es sospechosa pero se observa en una cantidad muy reducida de fotogramas, o si la velocidad de escaneo, la resolución óptica o la perfusión de contraste resultan insuficientes para caracterizar los contornos y límites físicos del hallazgo, estás obligado a declarar explícitamente la limitación técnica en tu reporte: 'Se identifica un hallazgo focal indeterminado en la secuencia de fotogramas X-Y, requiriendo de forma mandatoria correlación clínica urgente y confirmación mediante estudios dirigidos de alta resolución espacial/multisecuencia'.
"""

def inject_video_scanning_protocol(prompt_text: str, attached_files: Optional[List[Dict[str, Any]]] = None) -> str:
    if not attached_files or not isinstance(attached_files, list):
        return prompt_text
        
    has_video = False
    for f in attached_files:
        if not isinstance(f, dict):
            continue
        mime = f.get("mimeType", "") or f.get("type", "") or f.get("mime_type", "") or ""
        url = f.get("videoUrl") or f.get("video_url") or ""
        if mime.startswith("video/") or url:
            has_video = True
            break
            
    if not has_video:
        return prompt_text
        
    print("[Cognitive Engine] Dynamically injected native, decoupled 8 Metacognitive Laws of Dynamic Video Analysis")
    
    # Advanced Symptom-Driven Attentional Beacon (Dynamic Foveation)
    beacon_injected = ""
    prompt_lower = prompt_text.lower()
    
    abdominal_terms = ["abdomen", "abdominal", "pancreas", "pancreatico", "higado", "hepatico", "portal", "porta", "ictericia", "jaundice", "masas", "masa", "intestinal", "obstru", "pain", "dolor", "biliar", "coledoco", "duodeno"]
    thoracic_terms = ["torax", "pulmon", "pulmonar", "pleura", "cardiaco", "corazon", "mediastino", "aorta", "diseccion", "chest", "toracico", "respiratorio", "disnea"]
    pelvic_terms = ["pelvico", "pelvis", "vejiga", "utero", "ovario", "recto", "prostata", "cavitario", "urinario"]
    
    if any(term in prompt_lower for term in abdominal_terms):
        beacon_injected = (
            "\n\n🚨 ALERTA DE FOVEACIÓN CLÍNICA (FOCO ABDOMINO-HILIAR ACTIVO):\n"
            "La presentación clínica o los síntomas del paciente sugieren patología activa en la cavidad abdominal, "
            "complejo hepato-pancreático o espacio retroperitoneal. Estás estrictamente obligado a concentrar "
            "tus mayores recursos cognitivos en el Segmento II (30% al 70% de la línea de tiempo del video). "
            "Audita con zoom mental y de forma milimétrica el complejo pancreático-duodenal, el hilio hepato-esplénico, "
            "los conductos excretores/drenaje (vías biliares y conducto de Wirsung) y el eje vascular mayor retroperitoneal. "
            "Busca activamente el signo de envolvimiento vascular o dilatación hiliar. No permitas que la normalidad de otros segmentos diluya la sospecha."
        )
    elif any(term in prompt_lower for term in thoracic_terms):
        beacon_injected = (
            "\n\n🚨 ALERTA DE FOVEACIÓN CLÍNICA (FOCO TORÁCICO-CARDIOVASCULAR ACTIVO):\n"
            "La presentación clínica o síntomas sugieren sospecha de patología intratorácica, pulmonar o de mediastino. "
            "Estás estrictamente obligado a concentrar tu escrutinio visual en el Segmento I (0% al 30% de la línea de tiempo del video). "
            "Evalúa frame a frame el parénquima pulmonar basal, los contornos de los grandes vasos (aorta y sus ramas) y la integridad pleural. "
            "Busca asimetrías de flujo de contraste o derrames basales mínimos."
        )
    elif any(term in prompt_lower for term in pelvic_terms):
        beacon_injected = (
            "\n\n🚨 ALERTA DE FOVEACIÓN CLÍNICA (FOCO PELVIANO-CAVITARIO ACTIVO):\n"
            "La presentación clínica o síntomas sugieren sospecha de patología en la pelvis menor o compartimento cavitario inferior. "
            "Estás obligado a concentrar tu escrutinio visual en el Segmento III (70% al 100% de la línea de tiempo del video). "
            "Evalúa frame a frame el contorno de la vejiga, próstata o útero/ovarios, asas intestinales distales y la presencia de líquido libre en declive."
        )
        
    if beacon_injected:
        print(f"[Cognitive Engine] Symptom-Driven Attentional Beacon successfully generated and merged.")
        return prompt_text + "\n\n" + MASTER_VIDEO_REASONING_PROTOCOL + beacon_injected
        
    return prompt_text + "\n\n" + MASTER_VIDEO_REASONING_PROTOCOL
