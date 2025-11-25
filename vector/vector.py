

import warnings
from dotenv import load_dotenv
import os
from typing import List

# Suprimir warning deprecado de OllamaEmbeddings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from qdrant_client import QdrantClient
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_qdrant import QdrantVectorStore
from langchain_core.tools import Tool
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.llms import Ollama

# DeepAgent imports
from deep_agent.planner import DeepAgentPlanner
from deep_agent.neo4j_tool import get_neo4j_tool

# ==============
# Config & setup
# ==============
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None

EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER", "ollama").lower()
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Selección dinámica de embeddings
if EMBEDDINGS_PROVIDER == "openai":
    EMB = OpenAIEmbeddings()
    print("[INFO] Usando OpenAIEmbeddings para embeddings.")
elif EMBEDDINGS_PROVIDER == "gemini":
    EMB = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GOOGLE_API_KEY)
    print("[INFO] Usando GoogleGenerativeAIEmbeddings (Gemini) para embeddings.")
else:
    EMB = OllamaEmbeddings(base_url=OLLAMA_BASE_URL, model="nomic-embed-text")
    print(f"[INFO] Usando OllamaEmbeddings para embeddings (modelo: nomic-embed-text, url: {OLLAMA_BASE_URL}).")

def _client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

def get_qdrant_collection(name: str) -> QdrantVectorStore:
    client = _client()
    return QdrantVectorStore(
        client=client,
        collection_name=name,
        embedding=EMB,
    )

def get_llm():
    """
    Devuelve el LLM adecuado según LLM_PROVIDER para clasificación.
    """
    if LLM_PROVIDER == "openai":
        return ChatOpenAI(api_key=OPENAI_API_KEY, model="gpt-3.5-turbo")
    elif LLM_PROVIDER == "gemini":
        return ChatGoogleGenerativeAI(google_api_key=GOOGLE_API_KEY, model="gemini-2.5-flash")
    else:
        return Ollama(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)

def classify_query_category(query: str) -> str:
    """
    Usa el LLM para mapear la consulta a una categoría del catálogo.
    """
    llm = get_llm()
    prompt = (
        "Eres un asistente que clasifica consultas de productos en categorías del catálogo. "
        "Las categorías posibles son: calzado, ropa, accesorios, pulseras "
        "Dada la consulta del usuario, responde SOLO con la categoría más relevante, sin explicaciones ni adornos. "
        "Si no corresponde a ninguna, responde SOLO con 'ninguna'.\n\n"
        f"Consulta: {query}\nCategoría:"
    )
    try:
        # Para modelos chat, usar invoke con mensaje de sistema+usuario
        if LLM_PROVIDER in ["openai", "gemini"]:
            result = llm.invoke([
                {"role": "system", "content": "Clasifica la consulta en una categoría del catálogo."},
                {"role": "user", "content": prompt}
            ])
            # El resultado puede ser un objeto Message o string
            if hasattr(result, "content"):
                category = result.content.strip().lower()
            else:
                category = str(result).strip().lower()
        else:
            # Ollama: prompt plano
            category = llm.invoke(prompt).strip().lower()
        if category in ["calzado", "ropa", "accesorios", "pulseras"]:
            return category
        return ""
    except Exception as e:
        print(f"[ERROR] LLM classification failed: {e}")
        return ""

# ===================
# Retrievers por KB
# ===================
def products_retriever(k: int = 3):
    vs = get_qdrant_collection("catalog_kb")
    return vs.as_retriever(search_kwargs={"k": k})


# ==========================
# Funciones RAG por dominio
# ==========================
def _combine_docs_text(docs: List) -> str:
    if not docs:
        return "No se encontraron resultados relevantes."
    lines = []
    for d in docs:
        text = getattr(d, "page_content", str(d))
        meta = getattr(d, "metadata", {})
        meta = {k: v for k, v in meta.items() if k != "extras"}
        if meta:
            lines.append(f"{text}\n{meta}")
        else:
            lines.append(text)
    return "\n\n".join(lines)

def get_products_rag(query: str) -> str:
    print(f"[QDRANT] 🔍 Iniciando búsqueda semántica en catalog_kb: '{query}'")
    """
    Recupera información relevante del vectorstore 'catalog_kb' (productos)
    para la consulta dada y devuelve un texto combinado.
    Siempre filtra por stock_status="instock".
    """
    vs = get_qdrant_collection("catalog_kb")
    
    # Filtro: solo stock_status
    filter_dict = {
        "must": [
            {"key": "metadata.stock_status", "match": {"value": "instock"}}
        ]
    }
    
    print("[QDRANT] 📋 Aplicando filtro: stock_status = 'instock'")
    
    # Buscar con filtro
    results = vs.similarity_search(query, k=20, filter=filter_dict)
    
    print(f"[QDRANT] 📊 Encontrados {len(results)} documentos relevantes")
    result_text = _combine_docs_text(results)
    print(f"[QDRANT] ✅ Búsqueda completada (longitud resultado: {len(result_text)})")
    
    return result_text

def get_products_qdrant_list(query: str, k: int = 5) -> List[dict]:
    """
    Recupera productos de Qdrant como lista de dicts para DeepAgent.
    Filtra por stock_status="instock".
    """
    vs = get_qdrant_collection("catalog_kb")
    
    filter_dict = {
        "must": [
            {"key": "metadata.stock_status", "match": {"value": "instock"}}
        ]
    }
    
    results = vs.similarity_search(query, k=k, filter=filter_dict)
    
    products = []
    for doc in results:
        meta = getattr(doc, "metadata", {})
        products.append({
            "id": meta.get("sku", ""),
            "name": meta.get("name", ""),
            "price": meta.get("price", 0),
            "stock_status": meta.get("stock_status", ""),
            "categories": meta.get("categories", [])
        })
    
    return products


def products_tool_wrapper(query: str):
    print(f"[TOOL] 🛍️  products_retrieval_tool invocado con query: '{query}'")
    result = get_products_rag(query)
    print(f"[TOOL] ✅ products_retrieval_tool completado (longitud: {len(result)})")
    return result

products_tool = Tool(
    name="products_retrieval_tool",
    func=products_tool_wrapper,
    description=(
        "Usa esta herramienta para responder preguntas sobre productos del catálogo. "
        "La entrada es una consulta en texto; la salida es un resumen concatenado "
        "de los documentos relevantes en 'catalog_kb'."
    ),
)


# ==========================
# DeepAgent Tool Integration
# ==========================
def deep_agent_search(query: str) -> str:
    """
    Herramienta que integra DeepAgent para consultas complejas.
    Usa razonamiento simbólico (Neo4j) y búsqueda semántica (Qdrant) según el plan.
    """
    print(f"[DEEP AGENT] 🔍 Evaluando consulta: '{query}'")
    
    planner = DeepAgentPlanner(token_budget=2000)
    
    # Verificar si se debe activar DeepAgent
    should_activate = planner.should_activate_deep_agent(query)
    print(f"[DEEP AGENT] 🤔 ¿Activar DeepAgent? {should_activate}")
    
    if not should_activate:
        print("[DEEP AGENT] 📋 Consulta simple detectada, usando búsqueda directa en Qdrant")
        result = get_products_rag(query)
        print(f"[DEEP AGENT] ✅ Búsqueda Qdrant completada (longitud resultado: {len(result)})")
        return result
    
    # Crear plan de ejecución
    plan = planner.create_plan(query)
    print(f"[DEEP AGENT] 📝 Plan creado - Tipo: {plan.query_type}")
    print(f"[DEEP AGENT] 🔧 Parámetros extraídos: {plan.extracted_params}")
    print(f"[DEEP AGENT] 🛠️  Herramientas a usar - Neo4j: {plan.use_neo4j}, Qdrant: {plan.use_qdrant}")
    
    # Definir funciones de herramientas para el plan
    def neo4j_executor(plan_obj):
        """Ejecuta consultas en Neo4j según el tipo de plan."""
        print(f"[DEEP AGENT] 🗄️  Ejecutando consulta Neo4j - Tipo: {plan_obj.query_type}")
        neo4j_tool = get_neo4j_tool()
        
        if plan_obj.query_type == 'similarity':
            ref_product = plan_obj.extracted_params.get('reference_product', '')
            print(f"[DEEP AGENT] 🔗 Buscando productos similares a: '{ref_product}'")
            results = neo4j_tool.find_similar_products(ref_product, limit=5)
            print(f"[DEEP AGENT] ✅ Neo4j encontró {len(results)} productos similares")
            return results
        
        elif plan_obj.query_type == 'price_comparison':
            ref_product = plan_obj.extracted_params.get('reference_product', '')
            print(f"[DEEP AGENT] 💰 Buscando alternativas más baratas que: '{ref_product}'")
            results = neo4j_tool.find_cheaper_alternatives(ref_product, limit=5)
            print(f"[DEEP AGENT] ✅ Neo4j encontró {len(results)} alternativas más económicas")
            return results
        
        elif plan_obj.query_type == 'comparison':
            p1 = plan_obj.extracted_params.get('product1', '')
            p2 = plan_obj.extracted_params.get('product2', '')
            print(f"[DEEP AGENT] ⚖️  Comparando productos: '{p1}' vs '{p2}'")
            results = neo4j_tool.compare_products(p1, p2)
            print(f"[DEEP AGENT] ✅ Neo4j completó comparación")
            return results
        
        elif plan_obj.query_type == 'recommendation':
            use_case = plan_obj.extracted_params.get('use_case', '')
            print(f"[DEEP AGENT] 🎯 Generando recomendaciones para: '{use_case}'")
            # Intentar buscar por categoría inferida del caso de uso
            results = neo4j_tool.find_by_category(use_case, limit=10)
            print(f"[DEEP AGENT] ✅ Neo4j encontró {len(results)} recomendaciones")
            return results
        
        print(f"[DEEP AGENT] ⚠️  Tipo de consulta no reconocido: {plan_obj.query_type}")
        return []
    
    def qdrant_executor(plan_obj):
        """Ejecuta búsqueda semántica en Qdrant si es necesario."""
        print(f"[DEEP AGENT] 🔍 Ejecutando búsqueda semántica Qdrant - Tipo: {plan_obj.query_type}")
        # Para planes que necesitan complementar con búsqueda semántica
        if plan_obj.query_type in ['recommendation', 'comparison', 'similarity']:
            results = get_products_qdrant_list(query, k=5)
            print(f"[DEEP AGENT] ✅ Qdrant encontró {len(results)} productos relevantes")
            return results
        print(f"[DEEP AGENT] ⏭️  Qdrant no necesario para tipo: {plan_obj.query_type}")
        return []
    
    # Ejecutar plan
    print(f"[DEEP AGENT] 🚀 Ejecutando plan completo...")
    result = planner.execute_plan(plan, neo4j_executor, qdrant_executor)
    print(f"[DEEP AGENT] 🎉 Plan ejecutado exitosamente (longitud resultado: {len(result)})")
    return result

deep_agent_tool = Tool(
    name="deep_agent_search_tool",
    func=deep_agent_search,
    description=(
        "Usa esta herramienta para consultas complejas sobre productos que requieren "
        "razonamiento simbólico, comparaciones, recomendaciones o búsqueda de alternativas. "
        "Ejemplos: 'similar a X', 'comparar X vs Y', 'más barato que X', 'lo mejor para correr'. "
        "Activa automáticamente DeepAgent para planificación multi-stage y consultas en Neo4j."
    ),
)

RETRIEVAL_TOOLS = [deep_agent_tool, products_tool]
