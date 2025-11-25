"""
DeepAgent Planner - Multi-stage reasoning for complex product queries
"""
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class QueryPlan:
    """Representa un plan de ejecución para una consulta compleja."""
    steps: List[str]
    use_neo4j: bool
    use_qdrant: bool
    query_type: str  # 'simple', 'comparison', 'recommendation', 'complex'
    extracted_params: Dict[str, any]


class DeepAgentPlanner:
    """
    Planificador interno para queries complejas.
    Decide si activar razonamiento simbólico (Neo4j) o búsqueda semántica (Qdrant).
    """
    
    # Patrones que activan DeepAgent
    COMPARISON_PATTERNS = [
        r'compar[ae]r?\s+(.+?)\s+(?:vs|versus|con|y)\s+(.+)',
        r'diferencias?\s+entre\s+(.+?)\s+y\s+(.+)',
        r'(?:cuál|cual|que)\s+es\s+mejor\s+(.+?)\s+o\s+(.+)',
    ]
    
    SIMILARITY_PATTERNS = [
        r'similar(?:es)?\s+a(?:l)?\s+(.+)',
        r'parecido\s+a(?:l)?\s+(.+)',
        r'alternativas?\s+a(?:l)?\s+(.+)',
        r'como\s+(.+)\s+pero',
    ]
    
    PRICE_PATTERNS = [
        r'más\s+barato\s+que\s+(.+)',
        r'menos\s+caro\s+que\s+(.+)',
        r'económico\s+(?:que|a)\s+(.+)',
        r'mejor\s+precio\s+que\s+(.+)',
    ]
    
    RECOMMENDATION_PATTERNS = [
        r'mejor\s+para\s+(.+)',
        r'recomiend[ao]\s+para\s+(.+)',
        r'(?:lo|el)\s+mejor\s+para\s+(.+)',
        r'ideal\s+para\s+(.+)',
    ]
    
    def __init__(self, token_budget: int = 2000):
        self.token_budget = token_budget
    
    def should_activate_deep_agent(self, query: str) -> bool:
        """
        Determina si la consulta requiere DeepAgent basado en patrones de complejidad.
        
        PASO 1: Convertir query a minúsculas para matching case-insensitive
        PASO 2: Probar todos los patrones de activación (comparison, similarity, price, recommendation)
        PASO 3: Si algún patrón coincide, activar DeepAgent
        PASO 4: Retornar False para queries simples (solo búsqueda semántica)
        """
        query_lower = query.lower()
        
        # PASO 2: Verificar patrones de activación
        all_patterns = (
            self.COMPARISON_PATTERNS + 
            self.SIMILARITY_PATTERNS + 
            self.PRICE_PATTERNS + 
            self.RECOMMENDATION_PATTERNS
        )
        
        for pattern in all_patterns:
            if re.search(pattern, query_lower):
                return True
        
        return False
    
    def classify_query(self, query: str) -> str:
        """
        Clasifica el tipo de consulta basado en patrones específicos.
        
        PASO 1: Convertir query a minúsculas
        PASO 2: Probar patrones de comparación primero (más específicos)
        PASO 3: Probar patrones de similitud
        PASO 4: Probar patrones de precio
        PASO 5: Probar patrones de recomendación
        PASO 6: Retornar 'simple' si no coincide ningún patrón complejo
        """
        query_lower = query.lower()
        
        for pattern in self.COMPARISON_PATTERNS:
            if re.search(pattern, query_lower):
                return 'comparison'
        
        for pattern in self.SIMILARITY_PATTERNS:
            if re.search(pattern, query_lower):
                return 'similarity'
        
        for pattern in self.PRICE_PATTERNS:
            if re.search(pattern, query_lower):
                return 'price_comparison'
        
        for pattern in self.RECOMMENDATION_PATTERNS:
            if re.search(pattern, query_lower):
                return 'recommendation'
        
        return 'simple'
    
    def extract_parameters(self, query: str, query_type: str) -> Dict[str, any]:
        """
        Extrae parámetros relevantes de la consulta según el tipo.
        
        PASO 1: Inicializar diccionario de parámetros vacío
        PASO 2: Según query_type, usar patrones específicos para extraer info
        PASO 3: Para productos, limpiar artículos ("el", "la", etc.) del inicio
        PASO 4: Extraer talla si está presente (opcional)
        PASO 5: Extraer rango de precio si está presente (opcional)
        PASO 6: Retornar diccionario con parámetros extraídos
        """
        query_lower = query.lower()
        params = {}
        
        # PASO 2: Extraer nombres de productos
        if query_type == 'comparison':
            for pattern in self.COMPARISON_PATTERNS:
                match = re.search(pattern, query_lower)
                if match:
                    params['product1'] = match.group(1).strip()
                    params['product2'] = match.group(2).strip()
                    break
        
        elif query_type in ['similarity', 'price_comparison']:
            patterns = self.SIMILARITY_PATTERNS if query_type == 'similarity' else self.PRICE_PATTERNS
            for pattern in patterns:
                match = re.search(pattern, query_lower)
                if match:
                    product = match.group(1).strip()
                    # PASO 3: Limpiar artículos al inicio
                    product = re.sub(r'^(el|la|los|las|un|una|unos|unas)\s+', '', product, flags=re.IGNORECASE)
                    params['reference_product'] = product
                    break
        
        elif query_type == 'recommendation':
            for pattern in self.RECOMMENDATION_PATTERNS:
                match = re.search(pattern, query_lower)
                if match:
                    params['use_case'] = match.group(1).strip()
                    break
        
        # PASO 4: Extraer talla si está presente
        size_match = re.search(r'talla\s+(\d+(?:\.\d+)?)', query_lower)
        if size_match:
            params['size'] = size_match.group(1)
        
        # PASO 5: Extraer rango de precio
        price_match = re.search(r'(?:menor|menos|hasta)\s+(?:de\s+)?(?:USD\s+)?(\d+)', query_lower)
        if price_match:
            params['max_price'] = float(price_match.group(1))
        
        return params
    
    def create_plan(self, query: str) -> QueryPlan:
        """
        Crea un plan de ejecución para la consulta basado en su tipo.
        
        PASO 1: Clasificar la query usando classify_query()
        PASO 2: Extraer parámetros usando extract_parameters()
        PASO 3: Inicializar variables del plan (steps, use_neo4j, use_qdrant)
        PASO 4: Según query_type, definir steps específicos y herramientas a usar
        PASO 5: Para 'simple': solo Qdrant, sin Neo4j
        PASO 6: Para tipos complejos: incluir Neo4j y opcionalmente Qdrant
        PASO 7: Retornar QueryPlan con todos los detalles
        """
        query_type = self.classify_query(query)
        params = self.extract_parameters(query, query_type)
        
        steps = []
        use_neo4j = False
        use_qdrant = False
        
        if query_type == 'simple':
            # PASO 5: Consulta simple: solo búsqueda semántica en Qdrant
            steps = [
                "1. Buscar productos relevantes en Qdrant (filtro: stock disponible)",
                "2. Retornar top resultados"
            ]
            use_qdrant = True
        
        elif query_type == 'comparison':
            # PASO 6: Comparación: usar Neo4j para relaciones y Qdrant para detalles
            steps = [
                f"1. Buscar productos '{params.get('product1', '')}' y '{params.get('product2', '')}' en Neo4j",
                "2. Obtener atributos comparables (precio, categoría, características)",
                "3. Generar comparativa estructurada",
                "4. Enriquecer con información adicional de Qdrant si es necesario"
            ]
            use_neo4j = True
            use_qdrant = True
        
        elif query_type == 'similarity':
            # PASO 6: Similitud: usar relación SIMILAR_A en Neo4j
            steps = [
                f"1. Identificar producto de referencia: '{params.get('reference_product', '')}'",
                "2. Consultar Neo4j: productos con relación SIMILAR_A",
                "3. Filtrar por stock disponible",
                "4. Ordenar por relevancia (misma categoría, precio similar)"
            ]
            use_neo4j = True
        
        elif query_type == 'price_comparison':
            # PASO 6: Comparación de precio: usar relación MAS_BARATO_QUE en Neo4j
            steps = [
                f"1. Identificar producto de referencia: '{params.get('reference_product', '')}'",
                "2. Consultar Neo4j: productos con relación MAS_BARATO_QUE",
                "3. Filtrar por stock disponible y talla si aplica",
                "4. Retornar alternativas más económicas"
            ]
            use_neo4j = True
        
        elif query_type == 'recommendation':
            # PASO 6: Recomendación: combinar Neo4j (categoría/uso) y Qdrant (semántica)
            steps = [
                f"1. Analizar caso de uso: '{params.get('use_case', '')}'",
                "2. Buscar en Neo4j productos por categoría optimizada",
                "3. Complementar con búsqueda semántica en Qdrant",
                "4. Consolidar recomendaciones basadas en atributos"
            ]
            use_neo4j = True
            use_qdrant = True
        
        return QueryPlan(
            steps=steps,
            use_neo4j=use_neo4j,
            use_qdrant=use_qdrant,
            query_type=query_type,
            extracted_params=params
        )
    
    def combine_results(self, neo4j_results: List[Dict], qdrant_results: List[Dict]) -> List[Dict]:
        """
        Combina y deduplica resultados de Neo4j y Qdrant.
        
        PASO 1: Concatenar listas de resultados
        PASO 2: Crear set para tracking de IDs únicos
        PASO 3: Iterar y agregar solo productos con ID único
        PASO 4: Limitar a top 10 resultados
        PASO 5: Retornar lista deduplicada
        """
        combined = neo4j_results + qdrant_results
        seen = set()
        unique = []
        for r in combined:
            id = r.get('id')
            if id and id not in seen:
                seen.add(id)
                unique.append(r)
        return unique[:10]
    
    def format_results(self, results: List[Dict], query_type: str = "general") -> str:
        """
        Formatea los resultados para presentación al usuario.
        
        PASO 1: Si no hay resultados, retornar mensaje vacío
        PASO 2: Si es comparación, formatear tabla especial
        PASO 3: Para otros tipos, formatear lista numerada
        PASO 4: Incluir precio y stock en cada item
        PASO 5: Retornar string formateado
        """
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
        
        # PASO 3: Formato general para listas de productos
        formatted = []
        for i, product in enumerate(results[:10], 1):
            formatted.append(
                f"{i}. **{product['name']}** - USD {product['price']} "
                f"(Stock: {product.get('stock_status', 'instock')})"
            )
        
        return "\n".join(formatted)
    
    def execute_plan(self, plan: QueryPlan, neo4j_tool, qdrant_tool) -> str:
        """
        Ejecuta el plan utilizando las herramientas disponibles.
        
        PASO 1: Imprimir logs de ejecución del plan
        PASO 2: Ejecutar neo4j_tool si plan.use_neo4j (retorna list[dict])
        PASO 3: Ejecutar qdrant_tool si plan.use_qdrant (retorna list[dict])
        PASO 4: Combinar resultados usando combine_results()
        PASO 5: Formatear resultados usando format_results()
        PASO 6: Retornar respuesta final al usuario
        """
        print(f"[DEEP AGENT] Ejecutando plan de tipo: {plan.query_type}")
        for step in plan.steps:
            print(f"[DEEP AGENT] {step}")
        
        # PASO 2-3: Ejecutar herramientas según el plan
        neo4j_result = neo4j_tool(plan) if plan.use_neo4j and neo4j_tool else []
        qdrant_result = qdrant_tool(plan) if plan.use_qdrant and qdrant_tool else []
        
        # PASO 4: Combinar resultados
        combined = self.combine_results(neo4j_result, qdrant_result)
        
        # PASO 5: Formatear
        return self.format_results(combined, plan.query_type)
