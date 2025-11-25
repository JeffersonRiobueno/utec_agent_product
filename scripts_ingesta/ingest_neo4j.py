import os
import json
import uuid
import requests
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

# Configuración Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

# MCP config (reutilizado de ingest_catalog.py)
MCP_URL = os.getenv("MCP_URL", "http://192.168.18.42:8200/mcp")
MCP_API_KEY = os.getenv("MCP_API_KEY", "your_secure_api_key_here")

def initialize_mcp_session(mcp_url: str, api_key: str):
    """Inicializa sesión MCP y devuelve sessionId."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ingestion-client", "version": "1.0.0"}
        }
    }
    response = requests.post(mcp_url, json=payload, headers=headers)
    response.raise_for_status()
    session_id = response.headers.get("Mcp-Session-Id")
    if not session_id:
        raise ValueError("No se pudo obtener sessionId del MCP")
    return session_id

def call_mcp_tool(mcp_url: str, api_key: str, session_id: str, tool_name: str, arguments: dict):
    """Llama a una herramienta MCP y devuelve la respuesta parseada."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {api_key}",
        "Mcp-Session-Id": session_id
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments}
    }
    response = requests.post(mcp_url, json=payload, headers=headers, stream=True)
    response.raise_for_status()
    for line in response.iter_lines():
        if line.startswith(b"data: "):
            data = json.loads(line[6:].decode('utf-8'))
            return data.get("result", {}).get("structuredContent", {}).get("result", [])
    raise ValueError("No se pudo parsear respuesta MCP")

def create_neo4j_nodes_and_relations(driver, products):
    """Crea nodos y relaciones en Neo4j."""
    with driver.session() as session:
        # Crear nodos Producto y Categoría
        for product in products:
            product_id = product["id"]
            name = product.get("name", "Unknown")
            price = float(product.get("price", "0") or 0)
            stock_status = product.get("stock_status", "unknown")
            categories = product.get("categories", [])
            
            # Nodo Producto
            session.run(
                "MERGE (p:Producto {id: $id}) "
                "SET p.name = $name, p.price = $price, p.stock_status = $stock_status",
                id=product_id, name=name, price=price, stock_status=stock_status
            )
            
            # Nodos Categoría y relaciones
            for cat in categories:
                cat_name = cat["name"]
                session.run(
                    "MERGE (c:Categoria {name: $cat_name}) "
                    "MERGE (p:Producto {id: $product_id})-[:PERTENECE_A]->(c)",
                    cat_name=cat_name, product_id=product_id
                )
        
        # Relaciones simbólicas básicas (ejemplo: similar_a basado en categoría, más_barato_que)
        session.run(
            "MATCH (p1:Producto)-[:PERTENECE_A]->(c:Categoria)<-[:PERTENECE_A]-(p2:Producto) "
            "WHERE p1.id < p2.id AND p1.stock_status = 'instock' AND p2.stock_status = 'instock' "
            "MERGE (p1)-[:SIMILAR_A]->(p2)"
        )
        # Agregar SIMILAR_A basado en precio similar (±20%)
        session.run(
            "MATCH (p1:Producto), (p2:Producto) "
            "WHERE p1.id < p2.id AND p1.stock_status = 'instock' AND p2.stock_status = 'instock' "
            "AND p1.price > 0 AND p2.price > 0 "
            "AND abs(p1.price - p2.price) / p1.price <= 0.2 "
            "MERGE (p1)-[:SIMILAR_A]->(p2)"
        )
        # Agregar SIMILAR_A basado en categorías que contienen palabras clave comunes (ej. "Pulseras")
        session.run(
            "MATCH (p1:Producto)-[:PERTENECE_A]->(c1:Categoria), (p2:Producto)-[:PERTENECE_A]->(c2:Categoria) "
            "WHERE p1.id < p2.id AND p1.stock_status = 'instock' AND p2.stock_status = 'instock' "
            "AND c1.name CONTAINS 'Pulseras' AND c2.name CONTAINS 'Pulseras' "
            "MERGE (p1)-[:SIMILAR_A]->(p2)"
        )
        session.run(
            "MATCH (p1:Producto), (p2:Producto) "
            "WHERE p1.price < p2.price AND p1.stock_status = 'instock' AND p2.stock_status = 'instock' "
            "MERGE (p1)-[:MAS_BARATO_QUE]->(p2)"
        )

def run():
    """Ejecuta la ingesta completa."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    try:
        print("[INFO] Inicializando sesión MCP...")
        session_id = initialize_mcp_session(MCP_URL, MCP_API_KEY)
        
        print("[INFO] Llamando a list_products...")
        products = call_mcp_tool(MCP_URL, MCP_API_KEY, session_id, "list_products", {"per_page": 100})
        
        print(f"[INFO] Obtenidos {len(products)} productos del MCP")
        
        print("[INFO] Creando nodos y relaciones en Neo4j...")
        create_neo4j_nodes_and_relations(driver, products)
        
        print("[INFO] Ingesta a Neo4j completada.")
    finally:
        driver.close()

if __name__ == "__main__":
    run()