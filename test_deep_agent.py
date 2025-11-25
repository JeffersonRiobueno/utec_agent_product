"""
Script de prueba para el DeepAgent con Neo4j
"""
from deep_agent.planner import DeepAgentPlanner
from deep_agent.neo4j_tool import get_neo4j_tool

# Casos de prueba
test_queries = [
    "Busco pulseras de cuero",  # Simple - no activa DeepAgent
    "Productos similares al pulsera 9",  # Similarity - activa DeepAgent
    "Comparar cuarzo rosa Air Zoom vs negra Ultraboost",  # Comparison
    "Alternativas más baratas que el pulsera 9",  # Price comparison
    "Lo mejor para regalo de papá de noche",  # Recommendation
]

def test_planner():
    """Prueba el planificador sin ejecutar queries reales."""
    planner = DeepAgentPlanner()
    
    print("=" * 80)
    print("PRUEBA DEL DEEP AGENT PLANNER")
    print("=" * 80)
    
    for query in test_queries:
        print(f"\n{'='*80}")
        print(f"QUERY: {query}")
        print(f"{'='*80}")
        
        should_activate = planner.should_activate_deep_agent(query)
        print(f"¿Activar DeepAgent?: {should_activate}")
        
        if should_activate:
            plan = planner.create_plan(query)
            print(f"\nTipo de consulta: {plan.query_type}")
            print(f"Parámetros extraídos: {plan.extracted_params}")
            print(f"Usar Neo4j: {plan.use_neo4j}")
            print(f"Usar Qdrant: {plan.use_qdrant}")
            print(f"\nPasos del plan:")
            for step in plan.steps:
                print(f"  {step}")
        else:
            print("  → Respuesta directa con búsqueda semántica en Qdrant")

def test_neo4j_connection():
    """Prueba la conexión y consultas básicas en Neo4j."""
    print("\n" + "=" * 80)
    print("PRUEBA DE CONEXIÓN NEO4J")
    print("=" * 80)
    
    try:
        neo4j_tool = get_neo4j_tool()
        
        # Probar búsqueda de producto
        print("\n1. Buscando producto por nombre...")
        product = neo4j_tool.find_product_by_name("pulsera")
        if product:
            print(f"   ✓ Producto encontrado: {product['name']} - USD {product['price']}")
        else:
            print("   ✗ No se encontró producto")
        
        # Probar productos similares
        print("\n2. Buscando productos similares...")
        similar = neo4j_tool.find_similar_products("pulsera", limit=3)
        if similar:
            print(f"   ✓ Encontrados {len(similar)} productos similares:")
            for p in similar[:3]:
                print(f"     - {p['name']} - USD {p['price']}")
        else:
            print("   ✗ No se encontraron productos similares")
        
        # Probar alternativas más baratas
        print("\n3. Buscando alternativas más baratas...")
        cheaper = neo4j_tool.find_cheaper_alternatives("pulsera", limit=3)
        if cheaper:
            print(f"   ✓ Encontradas {len(cheaper)} alternativas más baratas:")
            for p in cheaper[:3]:
                print(f"     - {p['name']} - USD {p['price']}")
        else:
            print("   ✗ No se encontraron alternativas")
        
        # Probar búsqueda por categoría
        print("\n4. Buscando por categoría...")
        by_category = neo4j_tool.find_by_category("pulsera", limit=3)
        if by_category:
            print(f"   ✓ Encontrados {len(by_category)} productos en categoría:")
            for p in by_category[:3]:
                print(f"     - {p['name']} - USD {p['price']}")
        else:
            print("   ✗ No se encontraron productos en categoría")
        
        print("\n✅ Conexión a Neo4j exitosa")
        neo4j_tool.close()
        
    except Exception as e:
        print(f"\n❌ Error conectando a Neo4j: {e}")

if __name__ == "__main__":
    # Prueba 1: Planificador
    test_planner()
    
    # Prueba 2: Conexión Neo4j
    test_neo4j_connection()
    
    print("\n" + "=" * 80)
    print("PRUEBAS COMPLETADAS")
    print("=" * 80)
