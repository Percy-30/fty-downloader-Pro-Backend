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

from app.config import settings
import time

class SnapTubeError(Exception):
    pass

class YouTubeCombinerService:
    def __init__(self):
        # Directorio base para todos los temporales del combinador
        self.base_temp_dir = tempfile.gettempdir()
        logger.info("⚙️ YouTubeCombinerService inicializado")

    async def download_single(
        self,
        url: str,
        itag: int,
        output_filename: Optional[str] = None,
        strip_audio: bool = False,
        strip_video: bool = False
    ) -> Dict[str, Any]:
        """
        Descarga un solo formato (video o audio) de forma segura (PROXIED)
        """
        temp_dir = tempfile.mkdtemp(prefix="yt_single_", dir=self.base_temp_dir)
        try:
            logger.info(f"📥 Descarga simple solicitada: {url} (itag {itag})")
            
            if not output_filename:
                output_filename = f"youtube_single_{itag}_{int(asyncio.get_event_loop().time())}.mp4"
            
            output_path = os.path.join(temp_dir, output_filename)
            
            # Paso único: Descargar formato
            await self._download_format_threaded(url, itag, output_path, "single", temp_dir, strip_audio=strip_audio, strip_video=strip_video)
            
            if not os.path.exists(output_path):
                raise SnapTubeError("No se pudo descargar el archivo")
                
            file_size = os.path.getsize(output_path)
            
            return {
                "status": "success",
                "filename": output_filename,
                "file_size": file_size,
                "temp_path": output_path,
                "temp_dir": temp_dir,
                "combined": False
            }
        except Exception as e:
            logger.error(f"❌ Error en descarga simple: {str(e)}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise SnapTubeError(f"Error descargando formato: {str(e)}")

    async def download_and_combine(
        self, 
        url: str, 
        video_itag: Optional[int] = None,
        audio_itag: Optional[int] = None,
        quality: str = "1080p",
        format_type: str = "mp4",
        output_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Descarga y combina video + audio automáticamente (OPTIMIZADO PARA STREAMING)
        Si solo se provee un itag, funciona como descarga simple.
        """
        if video_itag is None and audio_itag is None:
            # Fallback a 1080p por defecto si no hay itags en absoluto
            video_itag, audio_itag = 137, 140

        temp_dir = tempfile.mkdtemp(prefix="yt_proc_", dir=self.base_temp_dir)
        try:
            logger.info(f"🎬 Iniciando proceso YouTube: {url}")
            logger.info(f"🎯 Parámetros - Video itag: {video_itag}, Audio itag: {audio_itag}, Formato: {format_type}")

            # Nombres de archivos temporales base
            temp_video = os.path.join(temp_dir, "video_temp.mp4")
            temp_audio_raw = os.path.join(temp_dir, f"audio_raw_{audio_itag}.m4a")
            
            # ✅ ESCENARIO 1: SOLO AUDIO
            if not video_itag and audio_itag:
                logger.info(f"⬇️ Descargando SOLO AUDIO (itag {audio_itag})...")
                await self._download_format_threaded(url, audio_itag, temp_audio_raw, "audio", temp_dir)
                
                if format_type.lower() == "mp3":
                    final_audio = os.path.join(temp_dir, f"audio_final_{audio_itag}_{int(time.time())}.mp3")
                    await self._convert_to_mp3_threaded(temp_audio_raw, final_audio)
                    if os.path.exists(temp_audio_raw): os.remove(temp_audio_raw)
                    target_path = final_audio
                else:
                    target_path = temp_audio_raw
                
                file_size = os.path.getsize(target_path)
                return {
                    "status": "success",
                    "temp_path": target_path,
                    "temp_dir": temp_dir,
                    "file_size": file_size,
                    "filename": os.path.basename(target_path),
                    "combined": False
                }

            # ✅ ESCENARIO 2: SOLO VIDEO
            if video_itag and not audio_itag:
                logger.info(f"⬇️ Descargando SOLO VIDEO (itag {video_itag})...")
                await self._download_format_threaded(url, video_itag, temp_video, "video", temp_dir, strip_audio=True)
                file_size = os.path.getsize(temp_video)
                return {
                    "status": "success",
                    "temp_path": temp_video,
                    "temp_dir": temp_dir,
                    "file_size": file_size,
                    "filename": os.path.basename(temp_video),
                    "combined": False
                }

            # ✅ ESCENARIO 3: COMBINACIÓN (VIDEO + AUDIO)
            logger.info("⬇️ Descargando video y audio para combinación...")
            if not output_filename:
                output_filename = f"youtube_combined_{video_itag}_{audio_itag}.mp4"
            final_output = os.path.join(temp_dir, output_filename)

            # Descargar ambos
            await self._download_format_threaded(url, video_itag, temp_video, "video", temp_dir)
            await self._download_format_threaded(url, audio_itag, temp_audio_raw, "audio", temp_dir)
            
            # Combinar
            logger.info("🎞️ Combinando con ffmpeg...")
            await self._merge_video_audio_threaded(temp_video, temp_audio_raw, final_output)
            
            # Limpieza inmediata de partes
            if os.path.exists(temp_video): os.remove(temp_video)
            if os.path.exists(temp_audio_raw): os.remove(temp_audio_raw)
            
            file_size = os.path.getsize(final_output)
            return {
                "status": "success",
                "temp_path": final_output,
                "temp_dir": temp_dir,
                "file_size": file_size,
                "filename": output_filename,
                "combined": True
            }
            
            # Paso 3: Combinar con ffmpeg
            logger.info("🎞️ Combinando con ffmpeg...")
            await self._merge_video_audio_threaded(temp_video, temp_audio, final_output)

            # ✅ LIMPIEZA INMEDIATA: Borrar partes separadas una vez unido
            try:
                if os.path.exists(temp_video):
                    os.remove(temp_video)
                if os.path.exists(temp_audio):
                    os.remove(temp_audio)
                logger.info("🧹 Partes temporales (video/audio) eliminadas tras combinación")
            except Exception as e:
                logger.warning(f"⚠️ No se pudieron borrar las partes temporales: {e}")

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
                "temp_dir": temp_dir,
                "combined": True
            }

        except Exception as e:
            logger.error(f"❌ Error en combinación: {str(e)}")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            raise SnapTubeError(f"Error combinando video y audio: {str(e)}")

    async def _download_format_threaded(self, url: str, itag: int, output_path: str, format_type: str, temp_dir_path: str, strip_audio: bool = False, strip_video: bool = False):
        """Descarga un formato específico usando yt-dlp con fixup de FFmpeg post-descarga (NUCLEAR VERSION)"""
        logger.info(f"⬇️ Descargando {format_type} (itag {itag}) - NUCLEAR FIX ACTIVADO")
        
        try:
            # Archivo de descarga inicial (siempre procesado después)
            download_path = output_path + ".raw"

            # Step 1: Descarga con yt-dlp con ROTACIÓN DE CLIENTES
            # Probamos diferentes clientes si uno falla o devuelve basura
            clients_to_try = [
                "tv",       # El más robusto contra SABR y Tokens
                "ios",      # Frecuente pero requiere tokens
                "android",  # Fallback móvil
                "mweb",     # Fallback web móvil
                "web"       # Último recurso
            ]
            
            success = False
            last_error = "Desconocido"
            
            for client in clients_to_try:
                logger.info(f"🔄 Intentando descargar {format_type} (itag {itag}) con cliente: {client}")
                
                # Limpiar rastro de intentos previos
                if os.path.exists(download_path):
                    os.remove(download_path)

                current_cmd = [
                    "yt-dlp",
                    "--no-playlist",
                    "-o", download_path,
                    "--socket-timeout", "30",
                    "--retries", "3",
                    "--no-check-certificate",
                    "--extractor-args", f"youtube:player-client={client}",
                    "--remote-components", "ejs:github",  # ✅ CRÍTICO: Para resolver JS challenges
                    "--cache-dir", "/app/cache/yt_dlp",   # ✅ COMPARTIR CACHÉ
                    "--no-part",
                    "-f", str(itag)
                ]
                
                # Agregar cookies si existen (convertir Path a string de forma segura)
                cookies_path = str(settings.YOUTUBE_COOKIES_PATH) if hasattr(settings, 'YOUTUBE_COOKIES_PATH') else "/app/cookies/cookies.txt"
                if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
                    current_cmd.extend(["--cookiefile", cookies_path])
                
                current_cmd.append(url)
                
                try:
                    await asyncio.to_thread(self._run_subprocess_sync, current_cmd, f"{format_type}_{client}")
                    
                    if os.path.exists(download_path):
                        file_size_raw = os.path.getsize(download_path)
                        # Verificación de tamaño según el tipo de formato
                        min_size = 50000 if format_type == "video" else 10000 # 50KB vídeo, 10KB audio
                        if file_size_raw > min_size: 
                            success = True
                            logger.info(f"✅ Descarga exitosa con cliente {client} ({file_size_raw} bytes)")
                            break
                        else:
                            logger.warning(f"⚠️ Archivo demasiado pequeño ({file_size_raw} bytes) con cliente {client}. Descartando.")
                            os.remove(download_path)
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"⚠️ Error descarga con cliente {client}: {last_error}")
                    if os.path.exists(download_path):
                        try: os.remove(download_path)
                        except: pass

            if not success:
                # 🚨 FALLBACK EXTREMO: Si falló el itag específico, intentamos descarga genérica
                logger.warning(f"🚨 Fallaron itags específicos ({itag}) con todos los clientes. Intentando descarga genérica...")
                fallback_cmd = [
                    "yt-dlp", "--no-playlist", 
                    "-o", download_path,
                    "--no-check-certificate",
                    "--remote-components", "ejs:github",
                    "-f", "bestaudio/best" if format_type == "audio" else "bestvideo/best",
                    url
                ]
                if os.path.exists(cookies_path) and os.path.getsize(cookies_path) > 100:
                    fallback_cmd.extend(["--cookiefile", cookies_path])
                
                try:
                    await asyncio.to_thread(self._run_subprocess_sync, fallback_cmd, f"{format_type}_fallback")
                    if os.path.exists(download_path) and os.path.getsize(download_path) > 5000:
                        success = True
                        logger.info(f"✨ Fallback exitoso para {format_type}")
                except Exception as e:
                    logger.error(f"❌ Falló incluso el fallback: {e}")
                    raise SnapTubeError(f"No se pudo descargar {format_type} ni con fallback. Último error: {last_error}")

            if not success:
                raise SnapTubeError(f"No se pudo descargar {format_type} con ningún método. Último error: {last_error}")

            # Step 2: Fixup con FFmpeg para asegurar que el archivo sea reproducible (Re-muxing forzado)
            file_size_raw = os.path.getsize(download_path)
            logger.info(f"🎞️ Procesando integridad de {format_type} con FFmpeg...")
            
            ffmpeg_cmd = ["ffmpeg", "-i", download_path, "-y"]
            
            if format_type == "audio":
                ffmpeg_cmd.append("-vn") # Sin video
                if output_path.lower().endswith(".mp3"):
                    # Re-encode MP3 a 192k fijo, 44100Hz, estéreo, compatible con todo
                    ffmpeg_cmd.extend(["-codec:a", "libmp3lame", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-id3v2_version", "3"])
                else:
                    # Re-encode M4A a AAC 192k fijo para máxima compatibilidad móvil
                    ffmpeg_cmd.extend(["-codec:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2", "-movflags", "+faststart"])
            else:
                # Video: Copiar video, asegurar audio compatible y banderas de streaming
                ffmpeg_cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"])
                if strip_audio:
                    ffmpeg_cmd.append("-an")
            
            ffmpeg_cmd.append(output_path)
            
            await asyncio.to_thread(self._run_subprocess_sync, ffmpeg_cmd, f"ffmpeg_fix_{format_type}")
            
            # Limpiar archivo temporal crudo
            if os.path.exists(download_path):
                os.remove(download_path)
            
            if not os.path.exists(output_path):
                raise SnapTubeError(f"Error: FFmpeg no pudo procesar el archivo final de {format_type}")
                
            file_size_final = os.path.getsize(output_path)
            logger.info(f"✅ {format_type.capitalize()} listo para el usuario: {file_size_final} bytes")
            
            # Limpiar archivo raw temporal
            if os.path.exists(download_path):
                os.remove(download_path)
            
            if not os.path.exists(output_path):
                raise SnapTubeError(f"Error: FFmpeg no pudo generar el archivo final {format_type}")
                
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ {format_type.capitalize()} verificado y listo: {file_size} bytes")

        except Exception as e:
            logger.error(f"❌ Error procesando {format_type}: {str(e)}")
            if os.path.exists(download_path):
                try: os.remove(download_path)
                except: pass
            raise

    async def _convert_to_mp3_threaded(self, input_path: str, output_path: str):
        """Convierte audio a MP3 usando ffmpeg (threaded para Windows)"""
        logger.info(f"🎵 Convirtiendo a MP3: {input_path} -> {output_path}")
        
        try:
            cmd = [
                "ffmpeg",
                "-i", input_path,
                "-vn",
                "-ar", "44100",
                "-ac", "2",
                "-b:a", "192k",
                "-y",
                output_path
            ]
            
            await asyncio.to_thread(
                self._run_subprocess_sync, cmd, "ffmpeg_mp3"
            )
            logger.info("✅ Conversión a MP3 completada")
        except Exception as e:
            logger.error(f"❌ Error convirtiendo a MP3: {str(e)}")
            raise SnapTubeError(f"Error en conversión MP3: {str(e)}")

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
        """Limpia archivos temporales antiguos (opcional, ya se limpian en las rutas)"""
        pass

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