"""
Neo4j Tool - Ejecuta consultas Cypher para razonamiento simbólico
"""
import os
from typing import Dict, List, Optional
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()


class Neo4jTool:
    """Herramienta para ejecutar consultas Cypher en Neo4j."""
    
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))
    
    def close(self):
        """Cierra la conexión."""
        if self.driver:
            self.driver.close()
        # Reset singleton instance
        global _neo4j_tool_instance
        _neo4j_tool_instance = None
    
    def execute_cypher(self, query: str, parameters: Dict = None) -> List[Dict]:
        """Ejecuta una consulta Cypher y retorna resultados."""
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]
    
    def find_product_by_name(self, product_name: str) -> Optional[Dict]:
        """Busca un producto por nombre (coincidencia parcial)."""
        query = """
        MATCH (p:Producto)
        WHERE toLower(p.name) CONTAINS toLower($name)
        AND p.stock_status = 'instock'
        RETURN p.id as id, p.name as name, p.price as price, p.stock_status as stock_status
        LIMIT 1
        """
        results = self.execute_cypher(query, {"name": product_name})
        return results[0] if results else None
    
    def find_similar_products(self, product_name: str, limit: int = 5) -> List[Dict]:
        """Encuentra productos similares usando la relación SIMILAR_A."""
        query = """
        MATCH (p1:Producto)-[:SIMILAR_A]-(p2:Producto)
        WHERE toLower(p1.name) CONTAINS toLower($name)
        AND p2.stock_status = 'instock'
        RETURN DISTINCT p2.id as id, p2.name as name, p2.price as price, p2.stock_status as stock_status
        LIMIT $limit
        """
        return self.execute_cypher(query, {"name": product_name, "limit": limit})
    
    def find_cheaper_alternatives(self, product_name: str, limit: int = 5) -> List[Dict]:
        """Encuentra alternativas más baratas usando la relación MAS_BARATO_QUE."""
        # Primero buscar el producto de referencia
        reference = self.find_product_by_name(product_name)
        if not reference:
            return []
        
        query = """
        MATCH (p:Producto)
        WHERE p.price < $reference_price
        AND p.stock_status = 'instock'
        RETURN p.id as id, p.name as name, p.price as price, p.stock_status as stock_status
        ORDER BY p.price ASC
        LIMIT $limit
        """
        return self.execute_cypher(query, {"reference_price": reference['price'], "limit": limit})
    
    def compare_products(self, product1_name: str, product2_name: str) -> Dict:
        """Compara dos productos y retorna sus atributos."""
        p1 = self.find_product_by_name(product1_name)
        p2 = self.find_product_by_name(product2_name)
        
        if not p1 or not p2:
            return {
                "error": f"No se encontraron uno o ambos productos: {product1_name}, {product2_name}"
            }
        
        # Obtener categorías de ambos productos
        query = """
        MATCH (p:Producto {id: $product_id})-[:PERTENECE_A]->(c:Categoria)
        RETURN c.name as category
        """
        p1_cats = self.execute_cypher(query, {"product_id": p1['id']})
        p2_cats = self.execute_cypher(query, {"product_id": p2['id']})
        
        return {
            "product1": {
                "name": p1['name'],
                "price": p1['price'],
                "categories": [c['category'] for c in p1_cats],
                "stock_status": p1['stock_status']
            },
            "product2": {
                "name": p2['name'],
                "price": p2['price'],
                "categories": [c['category'] for c in p2_cats],
                "stock_status": p2['stock_status']
            },
            "price_difference": abs(p1['price'] - p2['price']),
            "cheaper": p1['name'] if p1['price'] < p2['price'] else p2['name']
        }
    
    def find_by_category(self, category: str, limit: int = 10) -> List[Dict]:
        """Encuentra productos por categoría."""
        query = """
        MATCH (p:Producto)-[:PERTENECE_A]->(c:Categoria)
        WHERE toLower(c.name) CONTAINS toLower($category)
        AND p.stock_status = 'instock'
        RETURN p.id as id, p.name as name, p.price as price, p.stock_status as stock_status
        ORDER BY p.price ASC
        LIMIT $limit
        """
        return self.execute_cypher(query, {"category": category, "limit": limit})
    
    def format_results(self, results: List[Dict], query_type: str = "general") -> str:
        """Formatea los resultados para presentación."""
        if not results:
            return "No se encontraron productos que cumplan los criterios."
        
        if isinstance(results, dict) and 'error' in results:
            return results['error']
        
        if query_type == "comparison" and isinstance(results, dict) and 'product1' in results:
            p1 = results['product1']
            p2 = results['product2']
            return (
                f"**Comparación de productos:**\n\n"
                f"**{p1['name']}**\n"
                f"- Precio: USD {p1['price']}\n"
                f"- Categorías: {', '.join(p1['categories'])}\n"
                f"- Stock: {p1['stock_status']}\n\n"
                f"**{p2['name']}**\n"
                f"- Precio: USD {p2['price']}\n"
                f"- Categorías: {', '.join(p2['categories'])}\n"
                f"- Stock: {p2['stock_status']}\n\n"
                f"**Diferencia de precio:** USD {results['price_difference']}\n"
                f"**Más económico:** {results['cheaper']}"
            )
        
        # Formato general para listas de productos
        formatted = []
        for i, product in enumerate(results[:10], 1):
            formatted.append(
                f"{i}. **{product['name']}** - USD {product['price']} "
                f"(Stock: {product.get('stock_status', 'instock')})"
            )
        
        return "\n".join(formatted)


# Instancia global del tool
_neo4j_tool_instance = None

def get_neo4j_tool() -> Neo4jTool:
    """Retorna instancia singleton del Neo4j tool."""
    global _neo4j_tool_instance
    if _neo4j_tool_instance is None:
        _neo4j_tool_instance = Neo4jTool()
    return _neo4j_tool_instance

def reset_neo4j_tool():
    """Cierra y resetea la instancia del Neo4j tool (útil para tests)."""
    global _neo4j_tool_instance
    if _neo4j_tool_instance is not None:
        try:
            _neo4j_tool_instance.close()
        except:
            pass
        _neo4j_tool_instance = None
