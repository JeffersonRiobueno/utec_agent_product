# Agente de Búsqueda de Productos con RAG Híbrido (Neo4j + Qdrant)

Agente inteligente para ecommerce con:
- **Razonamiento simbólico** (Neo4j) para comparaciones y relaciones estructuradas
- **Búsqueda semántica** (Qdrant) para queries naturales
- **DeepAgent** con planificación multi-stage para consultas complejas
- Compatible con **OpenAI**, **Gemini** y **Ollama**

**Estado Actual: ✅ Completamente Funcional**
- Tests: 9/9 pasan (100%)
- Neo4j: 435 productos, 33,588 relaciones simbólicas
- API: Responde a consultas simples y complejas

---

## 🚀 Inicio Rápido

### 1. Levantar servicios con Docker Compose

```bash
# Levantar Neo4j + Agent Product
docker compose up -d

# Verificar que los servicios estén corriendo
docker compose ps
```

### 2. Configurar `.env`

Copia y edita el archivo `.env` con tus credenciales:

```env
# Qdrant (externo en tu red)
QDRANT_URL=http://192.168.18.21:6333/

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password  # Cámbiala por seguridad

# Embeddings provider
EMBEDDINGS_PROVIDER=openai  # Opciones: ollama, gemini, openai
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text

# LLM provider
LLM_PROVIDER=openai  # Opciones: gemini, openai, ollama
MODEL_NAME=gpt-4o-mini

# API Keys
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...

# MCP para ingesta desde WooCommerce
MCP_URL=http://192.168.18.42:8200/mcp
MCP_API_KEY=your_secure_api_key_here
```

### 3. Instalar dependencias (si usas local)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Ingestar productos

```bash
# Ingestar a Qdrant (búsqueda semántica)
docker compose exec agent_product python scripts_ingesta/ingest_catalog.py

# Ingestar a Neo4j (razonamiento simbólico)
docker compose exec agent_product python scripts_ingesta/ingest_neo4j.py

# Verificar productos en Qdrant (opcional)
docker compose exec agent_product python scripts_ingesta/list_qdrant_products.py
```

### 5. Probar el agente

**Interfaz Neo4j Browser:**
- Abre http://localhost:7474
- Usuario: `neo4j` / Password: `password`
- Ejecuta queries Cypher para explorar el grafo

**Test del DeepAgent:**
```bash
docker compose exec agent_product python test_deep_agent.py
```

**API FastAPI:**
```bash
# Consulta simple (usa Qdrant)
curl -X POST http://localhost:8100/products_agent_search \
  -H "Content-Type: application/json" \
  -d '{"text": "zapatos deportivos", "provider": "openai"}'

# Consulta compleja (activa DeepAgent + Neo4j)
curl -X POST http://localhost:8100/products_agent_search \
  -H "Content-Type: application/json" \
  -d '{"text": "similar al Metcon 9 pero más barato", "provider": "openai"}'
```

---

## 📁 Estructura del Proyecto

```
.
├── main.py                    # API FastAPI con endpoint del agente
├── docker-compose.yml         # Servicios: agent_product + neo4j
├── Dockerfile                 # Imagen del agente
├── requirements.txt           # Dependencias Python
├── .env                       # Variables de entorno
│
├── vector/
│   ├── __init__.py
│   └── vector.py              # Tools RAG: deep_agent, products
│
├── deep_agent/                # ⭐ NUEVO: DeepAgent + Neo4j
│   ├── __init__.py
│   ├── planner.py             # Planificador multi-stage
│   └── neo4j_tool.py          # Executor de queries Cypher
│
├── scripts_ingesta/
│   ├── ingest_catalog.py      # Ingesta a Qdrant desde MCP
│   ├── ingest_neo4j.py        # ⭐ NUEVO: Ingesta a Neo4j desde MCP
│   └── list_qdrant_products.py
│
├── data/
│   └── catalog_samples.csv    # Datos de ejemplo (opcional)
│
├── test_deep_agent.py         # ⭐ NUEVO: Tests del DeepAgent
├── test_integration.py        # ⭐ NUEVO: Tests de integración
├── README.md                  # Este archivo
└── DEEPAGENT_README.md        # Documentación detallada del DeepAgent
```

---

## 🎯 Capacidades del Agente

### Consultas Simples (Qdrant)
- "zapatos deportivos rojos"
- "zapatillas para correr"
- "calzado cómodo para caminar"

→ Búsqueda semántica vectorial rápida (<100ms)

### Consultas Complejas (DeepAgent + Neo4j)
- **Similitud:** "similar al Metcon 9"
- **Comparación:** "comparar Nike Air Zoom vs Adidas Ultraboost"
- **Precio:** "alternativas más baratas que el Metcon 9"
- **Recomendación:** "lo mejor para trail running"

→ Razonamiento simbólico + planificación multi-stage

---

## 🧪 Tests

```bash
# Test completo del DeepAgent
docker compose exec agent_product python test_deep_agent.py

# Tests de integración (Qdrant + Neo4j + API)
docker compose exec agent_product python test_integration.py

# Test individual de Neo4j
docker compose exec agent_product python -c "
from deep_agent.neo4j_tool import get_neo4j_tool
tool = get_neo4j_tool()
print(tool.find_similar_products('metcon', limit=3))
tool.close()
"
```

---

## 📊 Modelo de Datos

### Neo4j (Grafo de Conocimiento)

**Nodos:**
- `Producto` (id, name, price, stock_status)
- `Categoria` (name)

**Relaciones:**
- `PERTENECE_A`: Producto → Categoría
- `SIMILAR_A`: Producto ↔ Producto (misma categoría)
- `MAS_BARATO_QUE`: Producto → Producto (precio menor)

**Query de ejemplo:**
```cypher
// Productos similares al Metcon 9
MATCH (p1:Producto)-[:SIMILAR_A]-(p2:Producto)
WHERE toLower(p1.name) CONTAINS 'metcon'
AND p2.stock_status = 'instock'
RETURN p2.name, p2.price
LIMIT 5
```

### Qdrant (Vector Store)

**Colección:** `catalog_kb`

**Metadata:**
- sku, brand, price, category, stock_status, sizes

**Filtros aplicados:**
- `stock_status = "instock"` (solo productos disponibles)

---

## 🔧 Configuración Avanzada

### Cambiar provider de embeddings

```env
# Usar Ollama local
EMBEDDINGS_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=nomic-embed-text

# Asegúrate de tener el modelo
ollama pull nomic-embed-text
```

### Cambiar provider de LLM

```env
# Usar Gemini
LLM_PROVIDER=gemini
GOOGLE_API_KEY=...

# Usar Ollama
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
```

### Ajustar token budget del DeepAgent

En `vector/vector.py`:
```python
planner = DeepAgentPlanner(token_budget=2000)  # Cambiar valor
```

---

## 🐛 Troubleshooting

### Neo4j no conecta
```bash
# Verificar que el contenedor esté corriendo
docker compose ps

# Ver logs
docker compose logs neo4j

# Verificar credenciales en .env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### Qdrant no encuentra productos
```bash
# Verificar que Qdrant esté en tu red
curl http://192.168.18.21:6333/collections

# Re-ingestar
docker compose exec agent_product python scripts_ingesta/ingest_catalog.py
```

### Error de importación `neo4j`
```bash
# Reconstruir imagen con dependencias actualizadas
docker compose build agent_product
docker compose up -d
```

### DeepAgent no se activa
Verifica que tu consulta contenga patrones de activación:
- "similar a...", "comparar...", "más barato que...", "lo mejor para..."

---

## 📚 Documentación Adicional

- **[DEEPAGENT_README.md](DEEPAGENT_README.md)**: Arquitectura detallada del DeepAgent, comparación híbrido vs solo Neo4j, ejemplos avanzados

---

## 🎓 Créditos

Proyecto desarrollado como parte de experimentos de razonamiento simbólico en agentes conversacionales para ecommerce.

**Stack tecnológico:**
- FastAPI + LangChain + LangGraph
- Neo4j (grafo de conocimiento)
- Qdrant (búsqueda vectorial)
- OpenAI / Gemini / Ollama (LLMs y embeddings)
- WooCommerce MCP (ingesta de productos)
