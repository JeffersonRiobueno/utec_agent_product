import os
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain.agents import create_tool_calling_agent, AgentExecutor

from vector.vector import RETRIEVAL_TOOLS

load_dotenv()

SYSTEM_PROMPT = (
    "Eres un asistente experto en buscar productos de la tienda de zapatos. "
    "Ayudas a usuarios a responder preguntas sobre productos y encontrar información relevante. "
    "Tienes acceso a múltiples herramientas:\n"
    "- deep_agent_search_tool: Para consultas complejas (comparaciones, similitudes, recomendaciones)\n"
    "- products_retrieval_tool: Para búsquedas simples de productos\n"
    "- other_retrieval_tool: Para información general no relacionada con productos\n\n"
    "IMPORTANTE: Para consultas como 'similar a...', 'comparar... vs...', 'más barato que...', "
    "'lo mejor para...', SIEMPRE usa deep_agent_search_tool primero.\n"
    "Cuando tengas la respuesta, proporciona la información del producto y su stock si está disponible."
)

app = FastAPI()

DEFAULT_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()  # openai | ollama | gemini
DEFAULT_MODEL = os.getenv("MODEL_NAME", "gpt-4o-mini")          # por proveedor
DEFAULT_TEMPERATURE = float(os.getenv("MODEL_TEMPERATURE", "0.2"))

# (Opcional) URLs/keys por proveedor
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # requerido si usas gemini

class ProductAgentRequest(BaseModel):
    text: str
    provider: Optional[str] = DEFAULT_PROVIDER
    model: Optional[str] = DEFAULT_MODEL
    temperature: Optional[float] = DEFAULT_TEMPERATURE

class ProductAgentResponse(BaseModel):
    result: str



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
        # Requiere: OPENAI_API_KEY
        return ChatOpenAI(model=model, temperature=temperature)

    if provider == "ollama":
        # Requiere: Ollama corriendo localmente o remoto
        # Modelos típicos: "llama3.1", "qwen2.5", "phi3", etc.
        return ChatOllama(model=model, base_url=OLLAMA_BASE_URL, temperature=temperature)

    if provider == "gemini":
        # Requiere: GOOGLE_API_KEY
        if not GOOGLE_API_KEY:
            raise RuntimeError("Falta GOOGLE_API_KEY para usar Gemini.")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature, google_api_key=GOOGLE_API_KEY)

    raise ValueError(f"Proveedor LLM no soportado: {provider}. Usa: openai | ollama | gemini")

@app.post("/products_agent_search", response_model=ProductAgentResponse)
def products_agent_endpoint(req: ProductAgentRequest):
    print(f"[API] Nueva consulta recibida: '{req.text}' (provider: {req.provider}, model: {req.model})")
    
    llm = make_llm(req.provider, req.model, req.temperature)
    tools = RETRIEVAL_TOOLS  # Ahora incluye deep_agent_tool, products_tool, other_tool
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
        ("ai", "{agent_scratchpad}")
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
    
    print(f"[API] Ejecutando agente con {len(tools)} herramientas disponibles")
    # Ejecuta el agente de forma completamente automática
    result = executor.invoke({"input": req.text})
    
    # El resultado puede estar en diferentes campos según el modelo
    if isinstance(result, dict) and "output" in result:
        final_result = str(result["output"])
    else:
        final_result = str(result)
    
    print(f"[API] Respuesta generada (longitud: {len(final_result)} caracteres)")
    return ProductAgentResponse(result=final_result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
