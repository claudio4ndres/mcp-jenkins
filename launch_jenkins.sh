#!/bin/bash
# Guarda esto como: /Users/cfigueroa.externo/Documents/mcp-jenkins/launch_jenkins.sh

echo "🔧 Iniciando Jenkins MCP..." >&2

# Configurar variables de entorno para Jenkins
export JENKINS_URL="https://jenkins.coopeuch.cl"
export JENKINS_USERNAME="Cfigueroa"
export JENKINS_API_TOKEN="117aef1c3c97227805cb0e6e665faad309"

# Encontrar uv
UV_LOCATIONS=(
    "/Users/cfigueroa.externo/.cargo/bin/uv"
    "/Users/cfigueroa.externo/.local/bin/uv"
    "/usr/local/bin/uv"
    "/opt/homebrew/bin/uv"
)

UV_PATH=""
for location in "${UV_LOCATIONS[@]}"; do
    if [ -f "$location" ]; then
        UV_PATH="$location"
        echo "✅ uv encontrado en: $UV_PATH" >&2
        break
    fi
done

if [ -z "$UV_PATH" ]; then
    echo "❌ ERROR: uv no encontrado" >&2
    exit 1
fi

# Verificar variables de entorno
if [ -z "$JENKINS_URL" ] || [ -z "$JENKINS_USERNAME" ] || [ -z "$JENKINS_API_TOKEN" ]; then
    echo "❌ ERROR: Variables de entorno de Jenkins no configuradas" >&2
    echo "Configura: JENKINS_URL, JENKINS_USERNAME, JENKINS_API_TOKEN" >&2
    exit 1
fi

# Verificar que no sean valores por defecto
if [ "$JENKINS_URL" = "https://jenkins.tu-empresa.com" ] || [ "$JENKINS_USERNAME" = "tu-usuario" ] || [ "$JENKINS_API_TOKEN" = "tu-api-token-aqui" ]; then
    echo "❌ ERROR: Configura las variables reales de Jenkins" >&2
    echo "Edita este archivo y reemplaza los valores por defecto" >&2
    exit 1
fi

# Verificar conectividad VPN (opcional)
echo "🔍 Verificando conectividad con Jenkins..." >&2
if ! curl -s --connect-timeout 5 "$JENKINS_URL" > /dev/null 2>&1; then
    echo "⚠️  WARNING: No se puede conectar a Jenkins" >&2
    echo "💡 Asegúrate de estar conectado a la VPN" >&2
    echo "🔄 Intentando conectar de todas formas..." >&2
fi

# Cambiar al directorio del proyecto
cd "/Users/cfigueroa.externo/Documents/mcp-jenkins" || {
    echo "❌ ERROR: No se puede acceder al directorio mcp-jenkins" >&2
    exit 1
}

echo "📁 Directorio: $(pwd)" >&2
echo "🔗 Jenkins URL: $JENKINS_URL" >&2
echo "👤 Usuario: $JENKINS_USERNAME" >&2
echo "🚀 Ejecutando servidor..." >&2

# Ejecutar el servidor
exec "$UV_PATH" run python jenkins_mcp.py