#!/usr/bin/env python3
"""
Servidor MCP para Jenkins API
Permite interactuar con jobs, builds y pipelines de Jenkins
"""

import asyncio
import json
import sys
import os
import base64
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError as e:
    print(f"❌ Error: MCP no está instalado. Ejecuta: uv add mcp", file=sys.stderr)
    sys.exit(1)

@dataclass
class JenkinsJob:
    """Modelo de job de Jenkins"""
    name: str
    url: str
    color: str
    buildable: bool
    last_build: Optional[Dict]

@dataclass
class JenkinsBuild:
    """Modelo de build de Jenkins"""
    number: int
    url: str
    result: str
    building: bool
    duration: int
    timestamp: int

class JenkinsManager:
    """Gestor de API de Jenkins"""
    
    def __init__(self, jenkins_url: str, username: str, api_token: str):
        self.jenkins_url = jenkins_url.rstrip('/')
        self.username = username
        self.api_token = api_token
        
        # Crear autenticación básica
        auth_string = f"{username}:{api_token}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        self.headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/json"
        }
        
        # Configurar cliente con timeout extendido para VPN
        self.timeout = httpx.Timeout(30.0, connect=10.0)
    
    async def test_connection(self) -> Dict[str, Any]:
        """Probar conexión con Jenkins"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                response = await client.get(
                    f"{self.jenkins_url}/api/json",
                    headers=self.headers
                )
                response.raise_for_status()
                return response.json()
        except httpx.ConnectTimeout:
            raise Exception("Timeout de conexión - ¿Estás conectado a la VPN?")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise Exception("Error de autenticación - Verifica usuario y token")
            elif e.response.status_code == 403:
                raise Exception("Sin permisos - Verifica los permisos del usuario")
            else:
                raise Exception(f"Error HTTP {e.response.status_code}")
    
    async def get_jobs(self) -> List[JenkinsJob]:
        """Obtener lista de jobs"""
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(
                f"{self.jenkins_url}/api/json?tree=jobs[name,url,color,buildable,lastBuild[number,url,result,building]]",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            jobs = []
            for job_data in data.get("jobs", []):
                jobs.append(JenkinsJob(
                    name=job_data.get("name", ""),
                    url=job_data.get("url", ""),
                    color=job_data.get("color", ""),
                    buildable=job_data.get("buildable", False),
                    last_build=job_data.get("lastBuild")
                ))
            
            return jobs
    
    async def get_job_info(self, job_name: str) -> Dict[str, Any]:
        """Obtener información detallada de un job"""
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(
                f"{self.jenkins_url}/job/{job_name}/api/json",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_job_builds(self, job_name: str, limit: int = 10) -> List[JenkinsBuild]:
        """Obtener builds de un job"""
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(
                f"{self.jenkins_url}/job/{job_name}/api/json?tree=builds[number,url,result,building,duration,timestamp]{{0,{limit}}}",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            builds = []
            for build_data in data.get("builds", []):
                builds.append(JenkinsBuild(
                    number=build_data.get("number", 0),
                    url=build_data.get("url", ""),
                    result=build_data.get("result", "UNKNOWN"),
                    building=build_data.get("building", False),
                    duration=build_data.get("duration", 0),
                    timestamp=build_data.get("timestamp", 0)
                ))
            
            return builds
    
    async def get_build_info(self, job_name: str, build_number: int) -> Dict[str, Any]:
        """Obtener información de un build específico"""
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(
                f"{self.jenkins_url}/job/{job_name}/{build_number}/api/json",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_build_console(self, job_name: str, build_number: int, lines: int = 50) -> str:
        """Obtener logs de consola de un build"""
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(
                f"{self.jenkins_url}/job/{job_name}/{build_number}/consoleText",
                headers=self.headers
            )
            response.raise_for_status()
            
            # Obtener las últimas líneas
            console_output = response.text
            lines_list = console_output.split('\n')
            return '\n'.join(lines_list[-lines:])
    
    async def trigger_build(self, job_name: str, parameters: Dict[str, str] = None) -> bool:
        """Ejecutar un build"""
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            if parameters:
                # Build con parámetros
                response = await client.post(
                    f"{self.jenkins_url}/job/{job_name}/buildWithParameters",
                    headers=self.headers,
                    data=parameters
                )
            else:
                # Build simple
                response = await client.post(
                    f"{self.jenkins_url}/job/{job_name}/build",
                    headers=self.headers
                )
            
            return response.status_code in [200, 201]
    
    async def get_queue_info(self) -> List[Dict[str, Any]]:
        """Obtener información de la cola de builds"""
        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            response = await client.get(
                f"{self.jenkins_url}/queue/api/json",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            return data.get("items", [])

# Configuración desde variables de entorno
JENKINS_URL = os.getenv("JENKINS_URL")
JENKINS_USERNAME = os.getenv("JENKINS_USERNAME")
JENKINS_API_TOKEN = os.getenv("JENKINS_API_TOKEN")

if not all([JENKINS_URL, JENKINS_USERNAME, JENKINS_API_TOKEN]):
    print("❌ Error: Variables de entorno de Jenkins no configuradas", file=sys.stderr)
    print("Necesitas: JENKINS_URL, JENKINS_USERNAME, JENKINS_API_TOKEN", file=sys.stderr)
    sys.exit(1)

# Inicializar gestor de Jenkins
jenkins_manager = JenkinsManager(JENKINS_URL, JENKINS_USERNAME, JENKINS_API_TOKEN)
server = Server("jenkins")

@server.list_resources()
async def list_resources() -> List[types.Resource]:
    """Listar recursos disponibles de Jenkins"""
    return [
        types.Resource(
            uri="jenkins://jobs",
            name="Jobs de Jenkins",
            description="Lista de todos los jobs",
            mimeType="application/json",
        ),
        types.Resource(
            uri="jenkins://queue",
            name="Cola de Builds",
            description="Builds en cola de ejecución",
            mimeType="application/json",
        ),
        types.Resource(
            uri="jenkins://failed-jobs",
            name="Jobs Fallidos",
            description="Jobs con último build fallido",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def read_resource(uri: str) -> str:
    """Leer contenido de recursos de Jenkins"""
    try:
        if uri == "jenkins://jobs":
            jobs = await jenkins_manager.get_jobs()
            jobs_data = [
                {
                    "name": job.name,
                    "url": job.url,
                    "color": job.color,
                    "buildable": job.buildable,
                    "last_build": job.last_build
                }
                for job in jobs
            ]
            return json.dumps(jobs_data, indent=2, ensure_ascii=False)
        
        elif uri == "jenkins://queue":
            queue_items = await jenkins_manager.get_queue_info()
            return json.dumps(queue_items, indent=2, ensure_ascii=False)
        
        elif uri == "jenkins://failed-jobs":
            jobs = await jenkins_manager.get_jobs()
            failed_jobs = [
                {
                    "name": job.name,
                    "color": job.color,
                    "last_build": job.last_build
                }
                for job in jobs 
                if job.color in ["red", "red_anime"] or 
                   (job.last_build and job.last_build.get("result") == "FAILURE")
            ]
            return json.dumps(failed_jobs, indent=2, ensure_ascii=False)
        
        else:
            raise ValueError(f"Recurso no encontrado: {uri}")
    
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)

@server.list_tools()
async def list_tools() -> List[types.Tool]:
    """Listar herramientas disponibles de Jenkins"""
    return [
        types.Tool(
            name="get_jobs",
            description="Obtener lista de todos los jobs",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Filtrar jobs por nombre (opcional)"
                    }
                }
            },
        ),
        types.Tool(
            name="get_job_info",
            description="Obtener información detallada de un job",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Nombre del job"
                    }
                },
                "required": ["job_name"]
            },
        ),
        types.Tool(
            name="get_job_builds",
            description="Obtener builds recientes de un job",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Nombre del job"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Número de builds a mostrar (default: 10)"
                    }
                },
                "required": ["job_name"]
            },
        ),
        types.Tool(
            name="get_build_console",
            description="Obtener logs de consola de un build",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Nombre del job"
                    },
                    "build_number": {
                        "type": "integer",
                        "description": "Número del build"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Número de líneas a mostrar (default: 50)"
                    }
                },
                "required": ["job_name", "build_number"]
            },
        ),
        types.Tool(
            name="trigger_build",
            description="Ejecutar un build de un job",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Nombre del job a ejecutar"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Parámetros del build (opcional)"
                    }
                },
                "required": ["job_name"]
            },
        ),
        types.Tool(
            name="get_failed_jobs",
            description="Obtener jobs con builds fallidos",
            inputSchema={
                "type": "object",
                "properties": {}
            },
        ),
        types.Tool(
            name="test_connection",
            description="Probar conexión con Jenkins",
            inputSchema={
                "type": "object",
                "properties": {}
            },
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> List[types.TextContent]:
    """Ejecutar herramientas de Jenkins"""
    try:
        if name == "test_connection":
            connection_info = await jenkins_manager.test_connection()
            return [types.TextContent(
                type="text",
                text=f"✅ Conexión exitosa con Jenkins\n🏷️ Versión: {connection_info.get('version', 'N/A')}\n🔗 URL: {JENKINS_URL}"
            )]
        
        elif name == "get_jobs":
            filter_name = arguments.get("filter", "").lower()
            jobs = await jenkins_manager.get_jobs()
            
            if filter_name:
                jobs = [job for job in jobs if filter_name in job.name.lower()]
            
            if not jobs:
                return [types.TextContent(
                    type="text",
                    text="📋 No se encontraron jobs"
                )]
            
            result = f"📋 **Jobs de Jenkins:** ({len(jobs)} total)\n\n"
            
            for job in jobs:
                status_emoji = {
                    "blue": "✅",
                    "blue_anime": "🔄",
                    "red": "❌", 
                    "red_anime": "🔄❌",
                    "yellow": "⚠️",
                    "grey": "⚪",
                    "disabled": "⏸️"
                }.get(job.color, "❓")
                
                result += f"{status_emoji} **{job.name}**\n"
                result += f"   📊 Estado: {job.color}\n"
                result += f"   🔧 Ejecutable: {'Sí' if job.buildable else 'No'}\n"
                
                if job.last_build:
                    result += f"   🔢 Último build: #{job.last_build.get('number', 'N/A')}\n"
                    result += f"   📊 Resultado: {job.last_build.get('result', 'N/A')}\n"
                
                result += "\n"
            
            return [types.TextContent(type="text", text=result)]
        
        elif name == "get_job_info":
            job_name = arguments.get("job_name")
            if not job_name:
                return [types.TextContent(
                    type="text",
                    text="❌ Error: Se requiere job_name"
                )]
            
            job_info = await jenkins_manager.get_job_info(job_name)
            
            result = f"🔧 **Job: {job_name}**\n\n"
            result += f"📝 **Descripción:** {job_info.get('description', 'Sin descripción')}\n"
            result += f"📊 **Estado:** {job_info.get('color', 'N/A')}\n"
            result += f"🔧 **Ejecutable:** {'Sí' if job_info.get('buildable') else 'No'}\n"
            result += f"🔗 **URL:** {job_info.get('url', 'N/A')}\n\n"
            
            # Información del último build
            last_build = job_info.get('lastBuild')
            if last_build:
                result += f"🔢 **Último Build:** #{last_build.get('number')}\n"
                result += f"📊 **Resultado:** {last_build.get('result', 'N/A')}\n"
            
            # Builds recientes
            next_build = job_info.get('nextBuildNumber', 'N/A')
            result += f"⏭️ **Próximo Build:** #{next_build}\n"
            
            return [types.TextContent(type="text", text=result)]
        
        elif name == "get_job_builds":
            job_name = arguments.get("job_name")
            limit = arguments.get("limit", 10)
            
            if not job_name:
                return [types.TextContent(
                    type="text",
                    text="❌ Error: Se requiere job_name"
                )]
            
            builds = await jenkins_manager.get_job_builds(job_name, limit)
            
            if not builds:
                return [types.TextContent(
                    type="text",
                    text=f"📋 No hay builds para el job '{job_name}'"
                )]
            
            result = f"📋 **Builds del job '{job_name}':** ({len(builds)} builds)\n\n"
            
            for build in builds:
                status_emoji = {
                    "SUCCESS": "✅",
                    "FAILURE": "❌",
                    "UNSTABLE": "⚠️",
                    "ABORTED": "⏹️",
                    None: "🔄"
                }.get(build.result, "❓")
                
                result += f"{status_emoji} **Build #{build.number}**\n"
                result += f"   📊 Resultado: {build.result or 'En progreso'}\n"
                result += f"   🔄 Ejecutándose: {'Sí' if build.building else 'No'}\n"
                
                if build.duration > 0:
                    duration_min = build.duration // 60000
                    result += f"   ⏱️ Duración: {duration_min} min\n"
                
                # Timestamp
                if build.timestamp > 0:
                    timestamp = datetime.fromtimestamp(build.timestamp / 1000)
                    result += f"   📅 Fecha: {timestamp.strftime('%Y-%m-%d %H:%M')}\n"
                
                result += "\n"
            
            return [types.TextContent(type="text", text=result)]
        
        elif name == "get_build_console":
            job_name = arguments.get("job_name")
            build_number = arguments.get("build_number")
            lines = arguments.get("lines", 50)
            
            if not all([job_name, build_number]):
                return [types.TextContent(
                    type="text",
                    text="❌ Error: Se requieren job_name y build_number"
                )]
            
            console_output = await jenkins_manager.get_build_console(job_name, build_number, lines)
            
            result = f"📝 **Console logs - {job_name} #{build_number}** (últimas {lines} líneas)\n\n"
            result += f"```\n{console_output}\n```"
            
            return [types.TextContent(type="text", text=result)]
        
        elif name == "trigger_build":
            job_name = arguments.get("job_name")
            parameters = arguments.get("parameters", {})
            
            if not job_name:
                return [types.TextContent(
                    type="text",
                    text="❌ Error: Se requiere job_name"
                )]
            
            success = await jenkins_manager.trigger_build(job_name, parameters)
            
            if success:
                params_text = f" con parámetros: {parameters}" if parameters else ""
                return [types.TextContent(
                    type="text",
                    text=f"🚀 Build ejecutado exitosamente para '{job_name}'{params_text}"
                )]
            else:
                return [types.TextContent(
                    type="text",
                    text=f"❌ Error al ejecutar build para '{job_name}'"
                )]
        
        elif name == "get_failed_jobs":
            jobs = await jenkins_manager.get_jobs()
            failed_jobs = [
                job for job in jobs 
                if job.color in ["red", "red_anime"] or 
                   (job.last_build and job.last_build.get("result") == "FAILURE")
            ]
            
            if not failed_jobs:
                return [types.TextContent(
                    type="text",
                    text="✅ No hay jobs fallidos actualmente"
                )]
            
            result = f"❌ **Jobs Fallidos:** ({len(failed_jobs)} jobs)\n\n"
            
            for job in failed_jobs:
                result += f"❌ **{job.name}**\n"
                result += f"   📊 Estado: {job.color}\n"
                
                if job.last_build:
                    result += f"   🔢 Build: #{job.last_build.get('number')}\n"
                    result += f"   📊 Resultado: {job.last_build.get('result')}\n"
                
                result += "\n"
            
            return [types.TextContent(type="text", text=result)]
        
        else:
            return [types.TextContent(
                type="text",
                text=f"❌ Herramienta desconocida: {name}"
            )]
    
    except Exception as e:
        error_msg = str(e)
        if "Timeout" in error_msg:
            error_msg += "\n💡 Tip: ¿Estás conectado a la VPN?"
        
        return [types.TextContent(
            type="text",
            text=f"❌ Error: {error_msg}"
        )]

async def main():
    """Función principal"""
    print("🔧 Inicializando servidor MCP para Jenkins...", file=sys.stderr)
    
    try:
        # Probar conexión al inicio
        await jenkins_manager.test_connection()
        print("✅ Conexión con Jenkins establecida", file=sys.stderr)
        
        async with stdio_server() as (read_stream, write_stream):
            print("✅ Conexión establecida con Claude", file=sys.stderr)
            
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="jenkins",
                    server_version="1.0.0",
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={}
                    ),
                ),
            )
    except Exception as e:
        print(f"❌ Error del servidor: {e}", file=sys.stderr)
        if "VPN" in str(e) or "Timeout" in str(e):
            print("💡 Asegúrate de estar conectado a la VPN", file=sys.stderr)
        return 1
    
    return 0

if __name__ == "__main__":
    print("=" * 50, file=sys.stderr)
    print("🔧 MCP Jenkins Server", file=sys.stderr)
    print("🔌 Conecta Claude con Jenkins", file=sys.stderr)
    print("=" * 50, file=sys.stderr)
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n👋 Servidor detenido por el usuario", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 Error fatal: {e}", file=sys.stderr)
        sys.exit(1)