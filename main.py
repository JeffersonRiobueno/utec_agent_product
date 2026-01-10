import os
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor
from metrics.prometheus_metrics import get_metrics
from vector.vector import RETRIEVAL_TOOLS


try:
    from vector.vector import _client
except Exception:
    _client = None
try:
    from neo4j import GraphDatabase
except Exception:
    GraphDatabase = None

load_dotenv()

SYSTEM_PROMPT = (
    "Eres un asistente experto en ventas. "
    "Tu objetivo es ayudar a los usuarios a encontrar el producto ideal. "
    "Tienes acceso a una herramienta unificada: `unified_product_search_tool`. "
    "INSTRUCCIÓN CRÍTICA: Tienes prohibido responder sobre disponibilidad de productos basándote en tu memoria o en el resumen de la conversación. "
    "SIEMPRE debes usar la herramienta `unified_product_search_tool` para verificar el estado actual en tiempo real. "
    "El resumen de la conversación es solo para mantener el hilo de la charla, pero la información de stock allí puede ser vieja o incorrecta. "
    "Si el usuario insiste en un producto, BÚSCALO DE NUEVO con la herramienta. "
    "Después de obtener los datos de la herramienta, responde de forma amable, persuasiva y profesional."
)

app = FastAPI()

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()  # only openai supported
DEFAULT_MODEL = os.getenv("MODEL_NAME", "gpt-4o-mini")          # por proveedor
DEFAULT_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.2"))

# (Opcional) URLs/keys por proveedor
# Only OpenAI is supported now

class ProductAgentRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    context_summary: Optional[str] = None
    provider: Optional[str] = DEFAULT_PROVIDER
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = DEFAULT_TEMPERATURE

class ProductAgentResponse(BaseModel):
    result: str
    intermediate_steps: Optional[list] = None



# =========================
# Fábrica de LLMs
# =========================
def make_llm(
    provider: str,
    model: str,
    temperature: float
):
    provider = (provider or DEFAULT_PROVIDER).lower()
    if provider == "openai":
        return ChatOpenAI(model=model, temperature=temperature)

    raise ValueError(f"Proveedor LLM no soportado: {provider}. Solo 'openai' está soportado ahora.")


# Prometheus metrics endpoint

@app.get("/metrics")
def metrics():
    return get_metrics()

@app.post("/products_agent_search", response_model=ProductAgentResponse)
def products_agent_endpoint(req: ProductAgentRequest):
    print(f"[API] Nueva consulta recibida: '{req.text}' (provider: {req.provider}, model: {req.model}, session_id: {req.session_id})")
    if req.context_summary:
        print(f"[API] Context summary received: {req.context_summary}")

    # Si el context_summary contiene indicios de error, realizar validaciones de salud y devolver diagnóstico
    def _contains_error(text: str) -> bool:
        if not text:
            return False
        patterns = [r"\berror\b", r"\bproblema\b", r"\bfailed\b", r"\bfallo\b", r"\bexception\b", r"server error", r"no se pudo", r"no puedo"]
        combined = re.compile("|".join(patterns), flags=re.IGNORECASE)
        return bool(combined.search(text))

    def _check_qdrant() -> Tuple[bool, str]:
        if _client is None:
            return False, "Qdrant client no disponible en este entorno"
        try:
            client = _client()
            cols = client.get_collections()
            names = []
            if hasattr(cols, "collections"):
                names = [c.name for c in cols.collections]
            elif isinstance(cols, dict) and "collections" in cols:
                names = [c["name"] for c in cols["collections"]]
            else:
                names = []
            if names:
                if "catalog_kb" in names:
                    return True, f"Qdrant reachable, collections: {names}"
                else:
                    return False, f"Qdrant reachable but 'catalog_kb' no existe. Collections: {names}"
            return True, "Qdrant reachable (no list returned)"
        except Exception as e:
            return False, f"Qdrant check failed: {e}"

    def _check_neo4j() -> Tuple[bool, str]:
        uri = os.getenv("NEO4J_URI")
        user = os.getenv("NEO4J_USER")
        pwd = os.getenv("NEO4J_PASSWORD")
        if not uri or not user or not pwd or GraphDatabase is None:
            return False, "Neo4j not configured or driver not installed"
        try:
            driver = GraphDatabase.driver(uri, auth=(user, pwd))
            with driver.session() as session:
                _ = session.run("RETURN 1").single()
            driver.close()
            return True, "Neo4j reachable"
        except Exception as e:
            return False, f"Neo4j check failed: {e}"

    # Si no hay indicios de error en el summary, proceder como antes
    llm = make_llm(req.provider, req.model, req.temperature)
    tools = RETRIEVAL_TOOLS  # Ahora incluye deep_agent_tool, products_tool

    system_prompt = SYSTEM_PROMPT
    if req.context_summary:
        system_prompt = SYSTEM_PROMPT + "\n\n[HISTORIAL DE CHAT (SOLO PARA CONTEXTO, NO USAR PARA DATOS DE STOCK)]: " + req.context_summary

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "{input}"),
        ("ai", "{agent_scratchpad}")
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    # Habilitamos return_intermediate_steps para poder extraer contexto en evaluaciones
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True, return_intermediate_steps=True)
    
    print(f"[API] Ejecutando agente con {len(tools)} herramientas disponibles")
    # Ejecuta el agente usando SOLO el texto del usuario (sin context_summary)
    result = executor.invoke({"input": req.text})
    
    # Extraer la respuesta final
    final_output = result.get("output", str(result))
    # Extraer pasos intermedios (contexto de herramientas)
    steps = result.get("intermediate_steps", [])
    
    # Formatear pasos para serialización
    serializable_steps = []
    for step in steps:
        action, observation = step
        serializable_steps.append({
            "tool": action.tool,
            "tool_input": action.tool_input,
            "observation": str(observation)
        })

    print(f"[API] Respuesta generada (longitud: {len(str(final_output))} caracteres)")
    return ProductAgentResponse(result=str(final_output), intermediate_steps=serializable_steps)
    
    print(f"[API] Respuesta generada (longitud: {len(str(final_result))} caracteres)")
    return ProductAgentResponse(result=str(final_result))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
