"""
Tests de Integración - Agente de Productos con DeepAgent + Neo4j + Qdrant
"""
import os
import sys
import json
from dotenv import load_dotenv

# Agregar path para imports locales
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

def test_imports():
    """Test 1: Verificar que todos los módulos se importan correctamente."""
    print("=" * 80)
    print("TEST 1: Verificando importaciones")
    print("=" * 80)
    
    try:
        from deep_agent.planner import DeepAgentPlanner
        from deep_agent.neo4j_tool import get_neo4j_tool
        from vector.vector import RETRIEVAL_TOOLS, deep_agent_search
        print("✅ Todas las importaciones exitosas")
        return True
    except Exception as e:
        print(f"❌ Error en importaciones: {e}")
        return False


def test_neo4j_connection():
    """Test 2: Verificar conexión a Neo4j y existencia de datos."""
    print("\n" + "=" * 80)
    print("TEST 2: Conexión a Neo4j")
    print("=" * 80)
    
    try:
        from deep_agent.neo4j_tool import get_neo4j_tool
        
        neo4j_tool = get_neo4j_tool()
        
        # Verificar que hay productos
        query = "MATCH (p:Producto) RETURN count(p) as total"
        result = neo4j_tool.execute_cypher(query)
        
        if result and result[0]['total'] > 0:
            print(f"✅ Neo4j conectado. Productos en BD: {result[0]['total']}")
            # No cerrar el driver aquí, se reutiliza en otros tests
            return True
        else:
            print("⚠️  Neo4j conectado pero sin productos. Ejecuta ingest_neo4j.py")
            return False
            
    except Exception as e:
        print(f"❌ Error conectando a Neo4j: {e}")
        print("   Verifica que Neo4j esté corriendo: docker compose ps")
        return False


def test_qdrant_connection():
    """Test 3: Verificar conexión a Qdrant y existencia de colección."""
    print("\n" + "=" * 80)
    print("TEST 3: Conexión a Qdrant")
    print("=" * 80)
    
    try:
        from qdrant_client import QdrantClient
        
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        client = QdrantClient(url=qdrant_url)
        
        # Verificar colección catalog_kb
        collections = client.get_collections().collections
        catalog_exists = any(c.name == "catalog_kb" for c in collections)
        
        if catalog_exists:
            collection_info = client.get_collection("catalog_kb")
            print(f"✅ Qdrant conectado. Vectores en catalog_kb: {collection_info.points_count}")
            return True
        else:
            print("⚠️  Qdrant conectado pero sin colección catalog_kb. Ejecuta ingest_catalog.py")
            return False
            
    except Exception as e:
        print(f"❌ Error conectando a Qdrant: {e}")
        print(f"   Verifica QDRANT_URL en .env: {os.getenv('QDRANT_URL')}")
        return False


def test_deep_agent_planner():
    """Test 4: Verificar clasificación de queries por el DeepAgentPlanner."""
    print("\n" + "=" * 80)
    print("TEST 4: DeepAgent Planner - Clasificación de Queries")
    print("=" * 80)
    
    from deep_agent.planner import DeepAgentPlanner
    
    planner = DeepAgentPlanner()
    
    test_cases = [
        ("pulseras de cuero", False, "simple"),
        ("similar al pulsera 9", True, "similarity"),
        ("comparar cuarzo rosa vs negra", True, "comparison"),
        ("más barato que el doble vuelta", True, "price_comparison"),
        ("lo mejor para regalo de papá", True, "recommendation"),
    ]
    
    passed = 0
    for query, should_activate, expected_type in test_cases:
        activates = planner.should_activate_deep_agent(query)
        query_type = planner.classify_query(query)
        
        if activates == should_activate and query_type == expected_type:
            print(f"✅ '{query}' → Activar: {activates}, Tipo: {query_type}")
            passed += 1
        else:
            print(f"❌ '{query}' → Esperado: {should_activate}/{expected_type}, Obtenido: {activates}/{query_type}")
    
    print(f"\nResultado: {passed}/{len(test_cases)} tests pasados")
    return passed == len(test_cases)


def test_neo4j_queries():
    """Test 5: Verificar queries específicas de Neo4j."""
    print("\n" + "=" * 80)
    print("TEST 5: Queries Neo4j - Operaciones Básicas")
    print("=" * 80)
    
    try:
        from deep_agent.neo4j_tool import get_neo4j_tool
        
        neo4j_tool = get_neo4j_tool()
        passed = 0
        total = 0
        
        # Test 5.1: Buscar producto por nombre
        print("\n5.1 Buscar producto por nombre (contiene 'pulsera'):")
        total += 1
        product = neo4j_tool.find_product_by_name("pulsera")
        if product:
            print(f"  ✅ Encontrado: {product['name']} - USD {product['price']}")
            passed += 1
        else:
            print("  ⚠️  No se encontró producto. Verifica datos en Neo4j.")
        
        # Test 5.2: Productos similares
        print("\n5.2 Buscar productos similares:")
        total += 1
        similar = neo4j_tool.find_similar_products("pulsera", limit=3)
        if similar and len(similar) > 0:
            print(f"  ✅ Encontrados {len(similar)} productos similares:")
            for p in similar[:2]:
                print(f"     - {p['name']} - USD {p['price']}")
            passed += 1
        else:
            print("  ⚠️  No se encontraron similares. Relaciones SIMILAR_A no creadas.")
        
        # Test 5.3: Alternativas más baratas
        print("\n5.3 Buscar alternativas más baratas:")
        total += 1
        cheaper = neo4j_tool.find_cheaper_alternatives("pulsera", limit=3)
        if cheaper and len(cheaper) > 0:
            print(f"  ✅ Encontradas {len(cheaper)} alternativas más baratas:")
            for p in cheaper[:2]:
                print(f"     - {p['name']} - USD {p['price']}")
            passed += 1
        else:
            print("  ⚠️  No se encontraron alternativas más baratas.")
        
        # Test 5.4: Búsqueda por categoría
        print("\n5.4 Buscar por categoría:")
        total += 1
        by_category = neo4j_tool.find_by_category("Para hombres", limit=3)
        if by_category and len(by_category) > 0:
            print(f"  ✅ Encontrados {len(by_category)} productos en categoría:")
            for p in by_category[:2]:
                print(f"     - {p['name']} - USD {p['price']}")
            passed += 1
        else:
            print("  ⚠️  No se encontraron productos en categoría.")
        
        neo4j_tool.close()
        print(f"\nResultado: {passed}/{total} tests pasados")
        return passed == total
        
    except Exception as e:
        print(f"❌ Error en queries Neo4j: {e}")
        return False


def test_qdrant_search():
    """Test 6: Verificar búsqueda semántica en Qdrant."""
    print("\n" + "=" * 80)
    print("TEST 6: Búsqueda Semántica en Qdrant")
    print("=" * 80)
    
    try:
        from vector.vector import get_products_rag
        
        query = "pulseras de cuero"
        print(f"\nQuery: '{query}'")
        
        result = get_products_rag(query)
        
        if result and "No se encontraron" not in result:
            print(f"✅ Búsqueda exitosa. Primeros 200 chars de resultado:")
            print(f"   {result[:200]}...")
            return True
        else:
            print("⚠️  Búsqueda no retornó resultados. Verifica ingesta en Qdrant.")
            return False
            
    except Exception as e:
        print(f"❌ Error en búsqueda Qdrant: {e}")
        return False


def test_deep_agent_integration():
    """Test 7: Verificar integración completa del DeepAgent."""
    print("\n" + "=" * 80)
    print("TEST 7: Integración DeepAgent - Query Compleja")
    print("=" * 80)
    
    try:
        from vector.vector import deep_agent_search
        
        # Test con query que debe activar DeepAgent
        query = "similar a la pulsera"
        print(f"\nQuery compleja: '{query}'")
        
        result = deep_agent_search(query)
        
        if result and "No se encontraron" not in result:
            print(f"✅ DeepAgent ejecutado exitosamente. Primeros 200 chars:")
            print(f"   {result[:200]}...")
            return True
        else:
            print("⚠️  DeepAgent no retornó resultados válidos.")
            print(f"   Resultado: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Error en DeepAgent: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_endpoint():
    """Test 8: Verificar endpoint de FastAPI (si está corriendo)."""
    print("\n" + "=" * 80)
    print("TEST 8: API FastAPI - Endpoint /products_agent_search")
    print("=" * 80)
    
    try:
        import requests
        
        url = "http://localhost:8000/products_agent_search"
        payload = {
            "text": "pulseras de cuero",
            "provider": "openai",
            "model": "gpt-4o-mini"
        }
        
        print(f"\nPOST {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ API responde correctamente (200 OK)")
            print(f"   Resultado: {data.get('result', '')[:150]}...")
            return True
        else:
            print(f"⚠️  API respondió con status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️  API no está corriendo. Ejecuta: docker compose up -d")
        return False
    except Exception as e:
        print(f"❌ Error llamando API: {e}")
        return False


def test_neo4j_data_validation():
    """Test 9: Validar datos en Neo4j - imprimir resumen completo."""
    print("\n" + "=" * 80)
    print("TEST 9: Validación de Datos en Neo4j")
    print("=" * 80)
    
    try:
        from deep_agent.neo4j_tool import get_neo4j_tool
        
        neo4j_tool = get_neo4j_tool()
        
        print("\n📊 RESUMEN DE DATOS EN NEO4J:")
        print("-" * 50)
        
        # Contar nodos
        query_nodes = "MATCH (n) RETURN labels(n) as labels, count(*) as count"
        nodes = neo4j_tool.execute_cypher(query_nodes)
        print("NODOS:")
        for node in nodes:
            print(f"  - {node['labels']}: {node['count']}")
        
        # Contar relaciones
        query_rels = "MATCH ()-[r]->() RETURN type(r) as type, count(*) as count"
        rels = neo4j_tool.execute_cypher(query_rels)
        print("\nRELACIONES:")
        for rel in rels:
            print(f"  - {rel['type']}: {rel['count']}")
        
        # Mostrar algunas categorías
        query_cats = "MATCH (c:Categoria) RETURN c.name as name ORDER BY name LIMIT 10"
        cats = neo4j_tool.execute_cypher(query_cats)
        print("\nCATEGORÍAS (primeras 10):")
        for cat in cats:
            print(f"  - {cat['name']}")
        
        # Mostrar algunos productos con categorías
        query_prods = """
        MATCH (p:Producto)-[:PERTENECE_A]->(c:Categoria)
        RETURN p.name as product, collect(c.name) as categories, p.price as price, p.stock_status as stock
        ORDER BY p.price DESC LIMIT 5
        """
        prods = neo4j_tool.execute_cypher(query_prods)
        print("\nPRODUCTOS CON CATEGORÍAS (top 5 por precio):")
        for prod in prods:
            print(f"  - {prod['product']} (USD {prod['price']}) - Stock: {prod['stock']}")
            print(f"    Categorías: {', '.join(prod['categories'])}")
        
        # Verificar relaciones SIMILAR_A
        query_similar = "MATCH (p1)-[:SIMILAR_A]->(p2) RETURN p1.name, p2.name LIMIT 3"
        similars = neo4j_tool.execute_cypher(query_similar)
        print("\nRELACIONES SIMILAR_A (ejemplos):")
        if similars:
            for sim in similars:
                print(f"  - {sim['p1.name']} → SIMILAR_A → {sim['p2.name']}")
        else:
            print("  - Ninguna relación SIMILAR_A encontrada")
        
        # Verificar relaciones MAS_BARATO_QUE
        query_cheaper = "MATCH (p1)-[:MAS_BARATO_QUE]->(p2) RETURN p1.name, p2.name LIMIT 3"
        cheapers = neo4j_tool.execute_cypher(query_cheaper)
        print("\nRELACIONES MAS_BARATO_QUE (ejemplos):")
        if cheapers:
            for ch in cheapers:
                print(f"  - {ch['p1.name']} → MAS_BARATO_QUE → {ch['p2.name']}")
        else:
            print("  - Ninguna relación MAS_BARATO_QUE encontrada")
        
        print("\n✅ Validación completada. Revisa el resumen arriba.")
        return True
        
    except Exception as e:
        print(f"❌ Error validando datos en Neo4j: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Ejecuta todos los tests y genera reporte."""
    print("\n" + "=" * 80)
    print("🧪 SUITE DE TESTS - AGENTE DE PRODUCTOS CON DEEPAGENT")
    print("=" * 80)
    
    results = {
        "Importaciones": test_imports(),
        "Conexión Neo4j": test_neo4j_connection(),
        "Conexión Qdrant": test_qdrant_connection(),
        "DeepAgent Planner": test_deep_agent_planner(),
        "Queries Neo4j": test_neo4j_queries(),
        "Búsqueda Qdrant": test_qdrant_search(),
        "Integración DeepAgent": test_deep_agent_integration(),
        "API Endpoint": test_api_endpoint(),
        "Neo4j Data Validation": test_neo4j_data_validation(),
    }
    
    # Cleanup: cerrar conexión Neo4j al final
    try:
        from deep_agent.neo4j_tool import reset_neo4j_tool
        reset_neo4j_tool()
    except:
        pass
    
    # Reporte final
    print("\n" + "=" * 80)
    print("📊 REPORTE FINAL")
    print("=" * 80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print("\n" + "=" * 80)
    print(f"Total: {passed}/{total} tests pasados ({int(passed/total*100)}%)")
    print("=" * 80)
    
    if passed == total:
        print("\n🎉 ¡Todos los tests pasaron! El sistema está completamente funcional.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) fallaron. Revisa los mensajes arriba.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
