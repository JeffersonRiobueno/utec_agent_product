"""Métricas de Prometheus compartidas para el agente product.

Copiado desde el orquestador principal para mantener métricas comunes.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Métricas de requests
REQUEST_COUNT = Counter(
    'agent_product_requests_total',
    'Total number of requests to orchestrator',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'agent_product_request_duration_seconds',
    'Request latency in seconds',
    ['method', 'endpoint']
)

# Métricas de agentes
AGENT_REQUEST_COUNT = Counter(
    'agent_product_agent_requests_total',
    'Total number of requests to each agent',
    ['agent_name', 'status']
)

AGENT_LATENCY = Histogram(
    'agent_product_agent_duration_seconds',
    'Agent request latency in seconds',
    ['agent_name']
)

# Métricas de LLM
LLM_TOKEN_COUNT = Counter(
    'agent_product_llm_tokens_total',
    'Total number of LLM tokens used',
    ['token_type', 'model']
)

LLM_REQUEST_COUNT = Counter(
    'agent_product_llm_requests_total',
    'Total number of LLM requests',
    ['model', 'status']
)

# Métricas de intents
INTENT_COUNT = Counter(
    'agent_product_intent_total',
    'Total number of intents classified',
    ['intent']
)

# Métricas de guardrail
GUARDRAIL_COUNT = Counter(
    'agent_product_guardrail_total',
    'Total number of guardrail checks',
    ['result']
)

# Active sessions gauge
ACTIVE_SESSIONS = Gauge(
    'agent_product_active_sessions',
    'Number of active user sessions'
)

def get_metrics():
    """Obtener métricas en formato Prometheus."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# Helper functions para instrumentar el código
def increment_request_count(method: str, endpoint: str, status: str):
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()

def observe_request_latency(method: str, endpoint: str, duration: float):
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

def increment_agent_request_count(agent_name: str, status: str = "success"):
    AGENT_REQUEST_COUNT.labels(agent_name=agent_name, status=status).inc()

def observe_agent_latency(agent_name: str, duration: float):
    AGENT_LATENCY.labels(agent_name=agent_name).observe(duration)

def increment_llm_tokens(token_type: str, model: str, count: int):
    LLM_TOKEN_COUNT.labels(token_type=token_type, model=model).inc(count)

def increment_llm_request_count(model: str, status: str = "success"):
    LLM_REQUEST_COUNT.labels(model=model, status=status).inc()

def increment_intent_count(intent: str):
    INTENT_COUNT.labels(intent=intent).inc()

def increment_guardrail_count(result: str):
    GUARDRAIL_COUNT.labels(result=result).inc()

def update_active_sessions(count: int):
    ACTIVE_SESSIONS.set(count)
