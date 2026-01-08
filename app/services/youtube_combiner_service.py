# app/services/youtube_combiner_service.py
import subprocess
import os
import tempfile
import logging
import asyncio
from typing import Dict, Any, Optional
import shutil
import sys

logger = logging.getLogger(__name__)

class SnapTubeError(Exception):
    pass

class YouTubeCombinerService:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="yt_combiner_")
        logger.info(f"📁 Directorio temporal creado: {self.temp_dir}")

    async def download_and_combine(
        self, 
        url: str, 
        video_itag: int = 137,
        audio_itag: int = 140,
        output_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Descarga y combina video + audio automáticamente (OPTIMIZADO PARA STREAMING)
        """
        try:
            logger.info(f"🎬 Iniciando combinación: {url}")
            logger.info(f"🎯 Itags - Video: {video_itag}, Audio: {audio_itag}")

            # Nombres de archivos temporales
            temp_video = os.path.join(self.temp_dir, "video_temp.mp4")
            temp_audio = os.path.join(self.temp_dir, "audio_temp.m4a")
            
            if not output_filename:
                output_filename = f"youtube_combined_{video_itag}_{audio_itag}.mp4"
            
            final_output = os.path.join(self.temp_dir, output_filename)

            # ✅ SOLUCIÓN PARA WINDOWS: Usar asyncio.to_thread para subprocess
            # Paso 1: Descargar video
            logger.info("⬇️ Descargando video...")
            await self._download_format_threaded(url, video_itag, temp_video, "video")
            
            # Paso 2: Descargar audio  
            logger.info("⬇️ Descargando audio...")
            await self._download_format_threaded(url, audio_itag, temp_audio, "audio")
            
            # Paso 3: Combinar con ffmpeg
            logger.info("🎞️ Combinando con ffmpeg...")
            await self._merge_video_audio_threaded(temp_video, temp_audio, final_output)

            # Verificar que el archivo final existe
            if not os.path.exists(final_output):
                raise SnapTubeError("No se pudo crear el archivo combinado")

            file_size = os.path.getsize(final_output)
            logger.info(f"✅ Combinación exitosa: {file_size} bytes")

            # ✅ OPTIMIZACIÓN PARA STREAMING: NO leer el archivo completo
            return {
                "status": "success",
                "filename": output_filename,
                "file_size": file_size,
                "video_itag": video_itag,
                "audio_itag": audio_itag,
                "temp_path": final_output,
                "temp_dir": self.temp_dir,  # ✅ NUEVO: Para limpieza controlada
                "combined": True
            }

        except Exception as e:
            logger.error(f"❌ Error en combinación: {str(e)}")
            self._cleanup_temp_files()
            raise SnapTubeError(f"Error combinando video y audio: {str(e)}")

    async def _download_format_threaded(self, url: str, itag: int, output_path: str, format_type: str):
        """Descarga un formato específico usando yt-dlp (threaded para Windows)"""
        logger.info(f"⬇️ Descargando {format_type} (itag {itag})")
        
        try:
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "-f", str(itag),
                "-o", output_path,
                "--socket-timeout", "30",
                "--retries", "2",
                "--remote-components", "ejs:github",
                "--extractor-args", "youtube:player-client=ios,tv,web;skip=dash,hls",
                "--cache-dir", "/app/cache/yt_dlp",
                url
            ]
            
            logger.info(f"🔧 Ejecutando comando: {' '.join(cmd)}")
            
            # ✅ SOLUCIÓN: Usar asyncio.to_thread para evitar problemas de subprocess en Windows
            result = await asyncio.to_thread(
                self._run_subprocess_sync, cmd, format_type
            )
            
            if not os.path.exists(output_path):
                raise SnapTubeError(f"Archivo {format_type} no se creó: {output_path}")
                
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ {format_type.capitalize()} descargado: {file_size} bytes")

        except Exception as e:
            logger.error(f"❌ Error descargando {format_type}: {str(e)}")
            raise

    async def _merge_video_audio_threaded(self, video_path: str, audio_path: str, output_path: str):
        """Combina video + audio usando ffmpeg (threaded para Windows)"""
        logger.info(f"🎞️ Combinando video + audio")
        
        try:
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                "-y",
                output_path
            ]
            
            logger.info(f"🔧 Ejecutando ffmpeg...")
            
            # ✅ SOLUCIÓN: Usar asyncio.to_thread para ffmpeg también
            await asyncio.to_thread(
                self._run_subprocess_sync, cmd, "ffmpeg"
            )
                
            logger.info("✅ Combinación ffmpeg completada")

        except Exception as e:
            logger.error(f"❌ Error en ffmpeg: {str(e)}")
            raise

    def _run_subprocess_sync(self, cmd: list, process_name: str):
        """Ejecuta subprocess de forma síncrona (para usar con asyncio.to_thread)"""
        try:
            logger.info(f"🔄 Ejecutando {process_name} de forma síncrona...")
            
            # Ejecutar el comando de forma síncrona
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutos timeout
                check=True
            )
            
            logger.info(f"✅ {process_name} ejecutado exitosamente")
            return result
            
        except subprocess.TimeoutExpired:
            logger.error(f"⏰ Timeout en {process_name}")
            raise SnapTubeError(f"Timeout ejecutando {process_name}")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else "Error desconocido"
            logger.error(f"❌ Error en {process_name} (code {e.returncode}): {error_msg}")
            raise SnapTubeError(f"Error ejecutando {process_name}: {error_msg}")
        except Exception as e:
            logger.error(f"❌ Error inesperado en {process_name}: {str(e)}")
            raise

    def _cleanup_temp_files(self):
        """Limpia archivos temporales"""
        try:
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"🧹 Directorio temporal limpiado: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Error limpiando temporales: {e}")

    async def get_available_itags(self, url: str) -> Dict[str, Any]:
        """
        Obtiene los itags disponibles para un video de YouTube
        """
        try:
            logger.info(f"🔍 Obteniendo itags disponibles para: {url}")
            
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--list-formats",
                url
            ]
            
            result = await asyncio.to_thread(
                self._run_subprocess_sync, cmd, "list_formats"
            )
            
            # Procesar la salida para extraer itags
            formats = self._parse_formats_output(result.stdout)
            
            return {
                "status": "success",
                "url": url,
                "formats": formats,
                "total_formats": len(formats)
            }
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo itags: {str(e)}")
            raise SnapTubeError(f"Error obteniendo formatos disponibles: {str(e)}")

    def _parse_formats_output(self, output: str) -> list:
        """
        Parsea la salida de yt-dlp --list-formats para extraer información de formatos
        """
        formats = []
        lines = output.split('\n')
        
        # Buscar la línea que inicia la tabla de formatos
        start_parsing = False
        
        for line in lines:
            if "format code" in line and "extension" in line:
                start_parsing = True
                continue
                
            if start_parsing and line.strip():
                # Parsear línea de formato
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        format_info = {
                            "itag": parts[0],
                            "extension": parts[1],
                            "resolution": parts[2] if len(parts) > 2 else "",
                            "note": " ".join(parts[3:]) if len(parts) > 3 else ""
                        }
                        formats.append(format_info)
                    except Exception as e:
                        logger.warning(f"⚠️ Error parseando línea de formato: {line}")
                        continue
        
        logger.info(f"📊 Formatos parseados: {len(formats)}")
        return formats

    async def extract_info(self, url: str) -> Dict[str, Any]:
        """
        Extrae información básica del video usando yt-dlp
        """
        try:
            logger.info(f"🔍 Extrayendo información de: {url}")
            
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "--dump-json",
                url
            ]
            
            result = await asyncio.to_thread(
                self._run_subprocess_sync, cmd, "extract_info"
            )
            
            import json
            video_info = json.loads(result.stdout)
            
            logger.info(f"✅ Información extraída: {video_info.get('title', 'Unknown')}")
            return video_info
            
        except Exception as e:
            logger.error(f"❌ Error extrayendo información: {str(e)}")
            raise SnapTubeError(f"Error extrayendo información del video: {str(e)}")

    def estimate_combined_size(self, video_info: Dict[str, Any], video_itag: int, audio_itag: int) -> int:
        """
        Estima el tamaño combinado del video + audio
        """
        try:
            # Buscar información del formato de video
            video_format = None
            audio_format = None
            
            formats = video_info.get('formats', [])
            for fmt in formats:
                if fmt.get('format_id') == str(video_itag):
                    video_format = fmt
                if fmt.get('format_id') == str(audio_itag):
                    audio_format = fmt
            
            video_size = video_format.get('filesize') or video_format.get('filesize_approx', 0)
            audio_size = audio_format.get('filesize') or audio_format.get('filesize_approx', 0)
            
            # Estimación conservadora (video + audio + overhead)
            estimated_size = (video_size or 0) + (audio_size or 0) + (1024 * 1024)  # +1MB overhead
            
            logger.info(f"📊 Tamaño estimado: {estimated_size // 1024 // 1024}MB")
            return estimated_size
            
        except Exception as e:
            logger.warning(f"⚠️ Error estimando tamaño: {str(e)}")
            return 100 * 1024 * 1024  # Fallback: 100MB

    def __del__(self):
        """Destructor para limpieza automática"""
        self._cleanup_temp_files()

# Instancia global del servicio
youtube_combiner = YouTubeCombinerService()