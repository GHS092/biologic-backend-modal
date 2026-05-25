# GUÍA DE RAZONAMIENTO CINÉTICO-TEMPORAL Y ANÁLISIS DE VIDEO SIN HARDCODING (BioLogic System)

Esta guía define la arquitectura cognitiva, las leyes metacognitivas y las reglas de escaneo clínico para el procesamiento de secuencias de video, cine-loops y barridos de imagen médica (tomografía axial computada, resonancia magnética, ecografía dinámica y endoscopia) en **BioLogic**. 

El objetivo es erradicar el **sesgo de promedio (average bias)** y el **sesgo de normalidad (normalcy bias)** en IAs generativas de forma genérica y abstracta, garantizando diagnósticos de nivel élite sin recurrir al hardcoding.

---

## 🔎 El Diagnóstico del Fallo de IA en Videos: El "Sesgo de Promedio"

Los modelos de lenguaje y visión multimodales procesan los videos muestreando cuadros (frames) a lo largo del tiempo. En barridos médicos extensos (como una TC abdominal de 30 segundos), el 90% de los fotogramas suelen mostrar anatomía normal (los pulmones al inicio, el hígado sano, los riñones sanos).
*   **La Trampa del Promedio**: La IA asimila todos los fotogramas y deduce asociativamente que "la mayoría del estudio es normal". Por lo tanto, diluye o ignora una patología crítica (como un cáncer de páncreas, una pancreatitis focal masa, o una apendicitis aguda) que solo aparece visible durante un breve grupo de fotogramas (ej: frames 40 al 55).
*   **La Solución Metacognitiva**: Obligar al modelo a ejecutar una **auditoría espacial cronológica continua y de falsación sectorial**, tratando a cada estructura anatómica con el mismo peso en su ventana temporal respectiva, sin importar la normalidad de los fotogramas circundantes.

---

## 🛡️ Las 8 Leyes Metacognitivas del Análisis Clínico de Video

Cualquier agente de BioLogic que procese una secuencia cinética o de barrido de video está estrictamente obligado a seguir estas ocho leyes conceptuales:

### Ley 1: Continuidad Espacio-Temporal Continua (Voxel-Time Continuity)
> *"Un video de tomografía, resonancia o ecografía no es una colección de imágenes estáticas; representa el desplazamiento tridimensional continuo de estructuras a través del espacio y el tiempo. Tienes estrictamente prohibido emitir un juicio basado únicamente en fotogramas aislados. Debes reconstruir mentalmente la progresión anatómica (ej: cefalocaudal en cortes axiales, o de proximal a distal en barridos ecográficos), mapeando de forma espacial cada hallazgo a lo largo de la línea temporal."*

### Ley 2: Ley de la Anomalía Focal Transitoria (Transient Pathology Rule)
> *"Las patologías críticas en barridos de video (neoplasias sólidas activas, trombosis vasculares, stops obstructivos, colecciones líquidas ocultas o micro-calcificaciones) suelen ser altamente localizadas y transitorias en la línea del tiempo. Tienen prohibido diluir la significancia de un hallazgo por el predominio de fotogramas normales. Un solo grupo de fotogramas patológicos invalida por completo cualquier dictamen de normalidad del resto del barrido. Si se detecta una asimetría o densidad sospechosa en solo el 5% de la secuencia, se considerará críticamente significativa."*

### Ley 3: Ley de la Dinámica de Conductos y Trazabilidad (Ductal and Vascular Kinetic Tracing)
> *"Sigue meticulosamente el trayecto de los conductos naturales y estructuras tubulares (vía biliar intra/extrahepática, conducto de Wirsung pancreático, uréteres, arterias y venas principales) fotograma a fotograma como si navegaras por un río. Busca de forma dinámica cambios de calibre, estenosis abruptas, dilataciones retrógradas (ej: el signo del doble conducto) o defectos de llenado intraluminales (sugerentes de litiasis, trombos o neoplasias intraductales) a lo largo del scroll temporal."*

### Ley 4: Ley de la Consistencia de Contraste y Perfusión Temporal (Perfusion Kinetics)
> *"Analiza el flujo y distribución del medio de contraste a lo largo del tiempo del video. Identifica qué fases de perfusión (arterial, portal o tardía) están representadas en cada segmento temporal. Si una estructura presenta una densidad intermedia dudosa en cortes estáticos, evalúa su comportamiento dinámico: busca hiperrealce arterial rápido seguido de lavado portal (wash-out), o realce nodular periférico. Compara la señal del centro de la lesión contra tejidos sanos de anclaje de referencia en el mismo fotograma."*

### Ley 5: Ley del Escrutinio Sectorial y Desacoplamiento (Anatomical Sectorial Check)
> *"Queda estrictamente prohibido utilizar atajos cognitivos o reportar un veredicto general de normalidad al inicio. Estás obligado a realizar una auditoría negativa sistemática sector a sector a medida que el video avanza en el tiempo, reportando explícitamente el estado de:
> 1.  **Tórax / Mediastino / Pleura**: parénquima pulmonar basal y ganglios.
> 2.  **Abdomen Superior (Lóbulo Hepato-Esplénico)**: hígado, bazo, estómago y duodeno.
> 3.  **El Complejo Pancreático-Biliar**: cabeza, proceso uncinado, cuerpo y cola del páncreas de forma específica.
> 4.  **Retroperitoneo y Vasos**: riñones, glándulas suprarrenales, aorta y vena cava.
> 5.  **Abdomen Inferior y Pelvis**: asas intestinales, colon, vejiga y espacio peritoneal libre."*

### Ley 6: Ley del Doble Chequeo y Evitación de Cierre Prematuro (Anti-Cierre Prematuro)
> *"La localización de una lesión primaria o anomalía severa al inicio de la secuencia de video no justifica suspender el escaneo meticuloso. En estudios dinámicos de barrido, la coexistencia de múltiples lesiones, metástasis satélites pequeñas en el peritoneo o complicaciones obstructivas a distancia es un factor crítico. Tienes prohibido incurrir en cierre cognitivo prematuro; debes evaluar la secuencia con el mismo rigor hasta el último fotograma."*

### Ley 7: Ley de Falsación Biomecánica y Dinámica (Kinetic Mechanical Falsification)
> *"En estudios dinámicos (especialmente ecografías y cine-loops mecánicos), evalúa la interacción de las interfaces tisulares. Las lesiones benignas e inocuas (como quistes simples o grasa) son elásticas, se comprimen bajo presión y se deslizan suavemente sobre los planos de clivaje de grasa adyacentes. Las masas malignas o procesos infiltrativos activos son rígidos, fijos y demuestran tracción mecánica, borramiento de planos grasos e invaginación de vasos o estructuras vecinas."*

### Ley 8: Ley de la Zona de Incertidumbre Temporal (Temporal Uncertainty Rule)
> *"Si un hallazgo sospechoso aparece en un número muy reducido de fotogramas, o si el scroll es demasiado veloz o de baja resolución para clasificar los márgenes o la hemodinámica de contraste, debes declarar explícitamente la limitación en tu reporte de explicabilidad (XAI): 'Se identifica una atenuación focal dudosa en los frames X-Y. La dinámica temporal de perfusión en esta ventana es indeterminada. Se sugiere de forma mandatoria un estudio confirmatorio de cortes finos (ej: RMN contrastada dinámica pancreática/hepática)'."*
