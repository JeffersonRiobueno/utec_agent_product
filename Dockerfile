# ==========================
# Dockerfile - ecom-whatsapp-bot (actualizado)
# ==========================
FROM python:3.11-slim

# Evitar prompts interactivos
ENV DEBIAN_FRONTEND=noninteractive

# Directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y build-essential curl git && rm -rf /var/lib/apt/lists/*

# Copiar requerimientos primero (para aprovechar caché)
COPY requirements.txt .

# Instalar dependencias Python actualizadas
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de la aplicación
COPY . .

# Variables de entorno por defecto (pueden sobrescribirse)
ENV PORT=8000
ENV HOST=0.0.0.0
ENV USE_REDIS=false
ENV MODEL_NAME=gpt-4o-mini

# Exponer puerto FastAPI
EXPOSE 8000

# Comando de inicio del servidor
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
