import os, sys, requests, json, uuid
from sseclient import SSEClient
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.embeddings import OllamaEmbeddings

# Cargar el .env correcto siempre
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
print(f"[INFO] Usando Qdrant en: {QDRANT_URL}")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None

# Selección dinámica de embeddings
EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER", "ollama").lower()
if EMBEDDINGS_PROVIDER == "openai":
    EMB = OpenAIEmbeddings()
    print("[INFO] Usando OpenAIEmbeddings para embeddings.")
elif EMBEDDINGS_PROVIDER == "gemini":
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    if not GOOGLE_API_KEY:
        print("[ERROR] Falta GOOGLE_API_KEY en el entorno para usar GeminiEmbeddings.", file=sys.stderr)
        sys.exit(1)
    EMB = GoogleGenerativeAIEmbeddings(model="models/embedding-001", google_api_key=GOOGLE_API_KEY)
    print("[INFO] Usando GoogleGenerativeAIEmbeddings (Gemini) para embeddings.")
else:
    # Por defecto usa Ollama
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "nomic-embed-text")
    EMB = OllamaEmbeddings(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)
    print(f"[INFO] Usando OllamaEmbeddings para embeddings (modelo: {OLLAMA_MODEL}, url: {OLLAMA_BASE_URL}).")

def initialize_mcp_session(mcp_url, api_key):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ingestion-client", "version": "1.0.0"}
        }
    }
    response = requests.post(mcp_url, headers=headers, json=data, stream=True)
    response.raise_for_status()
    
    # Extraer sessionId del header
    session_id = response.headers.get("Mcp-Session-Id")
    if not session_id:
        raise ValueError("No se pudo obtener sessionId del header de respuesta")
    
    # Consumir la respuesta SSE para completar la inicialización
    client = SSEClient(response)
    for event in client.events():
        if event.event == 'message':
            # No necesitamos procesar el contenido, solo confirmar
            break
    
    return session_id

def call_mcp_tool(mcp_url, api_key, session_id, tool_name, arguments):
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {api_key}",
        "Mcp-Session-Id": session_id
    }
    data = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }
    response = requests.post(mcp_url, headers=headers, json=data, stream=True)
    response.raise_for_status()
    
    products = []
    client = SSEClient(response)
    for event in client.events():
        if event.event == 'message':
            data = json.loads(event.data)
            if 'result' in data and 'structuredContent' in data['result'] and 'result' in data['result']['structuredContent']:
                products.extend(data['result']['structuredContent']['result'])
    return products

def run(mcp_url=None, collection="catalog_kb"):
    if mcp_url is None:
        mcp_url = os.getenv("MCP_URL", "http://host.docker.internal:8200/mcp")
    api_key = os.getenv("MCP_API_KEY")
    if not api_key:
        print("[ERROR] MCP_API_KEY no definida en el entorno.", file=sys.stderr)
        sys.exit(1)
    
    docs = []
    
    try:
        # Inicializar sesión
        session_id = initialize_mcp_session(mcp_url, api_key)
        print(f"[INFO] Sesión MCP inicializada: {session_id}")
        
        # Llamar a la herramienta list_products
        products = call_mcp_tool(mcp_url, api_key, session_id, "list_products", {"per_page": 100})
        print(f"[INFO] Obtenidos {len(products)} productos del MCP")
        
        for product in products:
            title = product.get("name") or ""
            brand = ""  # No hay brand en la respuesta
            price = product.get("price") or ""
            cat = ", ".join([c.get("name", "") for c in product.get("categories", [])]) or ""
            sku = int(product.get("id", 0))
            stock_status = product.get("stock_status", "")
            sizes = product.get("sizes", "")  # Campo para tallas, si existe

            if not title:
                print(f"[WARN] Producto omitido por falta de 'name': {product}")
                continue

            text = f"{title} — {brand} — ./S (Soles Peruanos) {price} — {cat}".strip(" —")
            meta = {"sku": str(sku), "brand": brand, "price": price, "category": cat, "stock_status": stock_status, "sizes": sizes}
            doc_id = uuid.uuid5(uuid.NAMESPACE_DNS, str(sku))  # UUID consistente basado en sku
            docs.append(Document(page_content=text, metadata=meta, id=str(doc_id)))  # id como string UUID

    except Exception as e:
        print(f"[ERROR] Error al procesar MCP: {e}", file=sys.stderr)
        if isinstance(e, requests.RequestException) and e.response:
            print(f"[DEBUG] Respuesta error: {e.response.text}", file=sys.stderr)
        sys.exit(1)

    if not docs:
        print("[WARN] No se generaron documentos desde el MCP.")
        sys.exit(1)

    # Crear vectorstore si no existe, y agregar documentos con upsert
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    if not client.collection_exists(collection):
        print(f"[INFO] Creando colección '{collection}'.")
        # Calcular dimensión de embeddings
        test_emb = EMB.embed_query("test")
        vectors_config = {"size": len(test_emb), "distance": "Cosine"}
        client.create_collection(collection_name=collection, vectors_config=vectors_config)
    
    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=collection,
        embedding=EMB,
    )
    vectorstore.add_documents(documents=docs, ids=[doc.id for doc in docs])

    print(f"✅ Procesados {len(docs)} productos desde MCP en Qdrant ({collection}). Se actualizaron si el ID existía.")

if __name__ == "__main__":
    run()
