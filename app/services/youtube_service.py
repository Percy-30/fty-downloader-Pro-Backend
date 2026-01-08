import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse, parse_qs, urlunparse

import yt_dlp
import aiohttp
import aiofiles
import base64

from app.services.base_extractor import BaseExtractor, SnapTubeError
from app.config import settings

logger = logging.getLogger(__name__)

class YouTubeExtractor(BaseExtractor):
    """Extractor de YouTube que COMBINA automáticamente video + audio"""

    def __init__(self, cookies_file: Optional[str] = None):
        self._cookies_file = cookies_file
        self._temp_dir = tempfile.mkdtemp(prefix="snaptube_")
        super().__init__()

    @property
    def platform(self) -> str:
        return "youtube"

    def get_platform_headers(self) -> Dict[str, str]:
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9,es;q=0.8',
            'Referer': 'https://www.youtube.com/',
        }

    def _clean_url(self, url: str) -> str:
        """Limpia la URL igual que tu JS"""
        try:
            index = url.find('&')
            if index != -1:
                return url[:index]
            return url
        except Exception:
            return url

    def _ensure_cookies(self) -> Optional[str]:
        """Manejo robusto de cookies"""
        if not self._cookies_file:
            return None
            
        try:
            if os.path.exists(self._cookies_file):
                file_size = os.path.getsize(self._cookies_file)
                if file_size > 100:
                    logger.info(f"🍪 Cookies cargadas ({file_size} bytes)")
                    return self._cookies_file
                else:
                    logger.warning("⚠️ Archivo de cookies vacío o muy pequeño")
            return None
        except Exception as e:
            logger.warning(f"⚠️ Error verificando cookies: {e}")
            return None

    async def extract(self, url: str, cookies: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Extrae información y detecta formatos combinables"""
        try:
            self.validator.validate_url(url)
            url = self._clean_url(url)
            
            logger.info(f"🎬 Iniciando extracción YouTube: {url}")

            ydl_opts = {
                "dumpjson": True,
                "quiet": True,
                "no_check_certificate": True,
                "geo_bypass": True,
                "noplaylist": True,
                "extract_flat": False,
                "format": "best",
                "socket_timeout": 30,
                "retries": 3,
                "skip_unavailable_fragments": True,
                "http_headers": self.get_platform_headers(),
                "remote_components": ["ejs:github"],
                "extractor_args": {
                    "youtube": {
                        "player_client": ["tv", "android", "web"],
                        "skip": ["dash", "hls"]
                    }
                },
                "cachedir": "/app/cache/yt_dlp",
            }

            cookies_file_path = self._ensure_cookies()
            if cookies_file_path:
                ydl_opts["cookiefile"] = cookies_file_path

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: ydl.extract_info(url, download=False)
                    )

                if not info:
                    raise SnapTubeError("No se pudo extraer información del video")

                logger.info(f"✅ Extracción exitosa. Formatos encontrados: {len(info.get('formats', []))}")
                return self._build_optimized_response(info)

            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                logger.error(f"❌ Error yt-dlp: {error_msg}")
                
                if "Requested format is not available" in error_msg:
                    logger.warning("🔄 Intentando con formato simple...")
                    return await self._extract_with_simple_format(url)
                
                raise SnapTubeError(f"Error de YouTube: {error_msg}")

        except Exception as e:
            logger.error(f"💥 Error en extract: {e}", exc_info=True)
            raise SnapTubeError(f"Error interno: {e}")

    def _build_optimized_response(self, info: Dict) -> Dict[str, Any]:
        """Construye respuesta OPTIMIZADA que DETECTA formatos combinables"""
        
        # Clasificar formatos en categorías
        combined_formats = []    # Video + Audio juntos
        video_only_formats = []  # Solo video
        audio_only_formats = []  # Solo audio
        
        for f in info.get('formats', []):
            if not (f.get('url') and f.get('protocol') in ('http', 'https')):
                continue
                
            format_info = {
                'itag': f.get('format_id'),
                'quality': f.get('format_note', 'unknown') or f.get('format_id', 'unknown'),
                'format': f.get('ext', 'mp4'),
                'resolution': self._get_resolution_display(f),
                'size': self._get_size_display(f),
                'url': f['url'],
                'hasAudio': f.get('acodec') != 'none',
                'hasVideo': f.get('vcodec') != 'none',
                'fps': f.get('fps'),
                'height': f.get('height'),
                'width': f.get('width'),
                'vcodec': f.get('vcodec', ''),
                'acodec': f.get('acodec', '')
            }
            
            # Clasificar en categorías
            if format_info['hasVideo'] and format_info['hasAudio']:
                combined_formats.append(format_info)
            elif format_info['hasVideo']:
                video_only_formats.append(format_info)
            elif format_info['hasAudio']:
                audio_only_formats.append(format_info)
        
        # 🎯 ENCONTRAR MEJOR AUDIO para combinaciones
        best_audio = None
        if audio_only_formats:
            # Ordenar audio por calidad (bitrate más alto primero)
            audio_only_formats.sort(key=lambda x: self._get_audio_bitrate(x), reverse=True)
            best_audio = audio_only_formats[0]
            logger.info(f"🔊 Mejor audio encontrado: {best_audio['quality']} - {best_audio['size']}")

        # 🆕 AGREGAR RECOMENDACIÓN DE AUDIO a formatos video_only
        if best_audio:
            for video_format in video_only_formats:
                # Solo agregar a formatos HD (720p+)
                if video_format.get('height', 0) >= 720:
                    video_format['recommended_audio'] = {
                        'url': best_audio['url'],
                        'quality': best_audio['quality'],
                        'size': best_audio['size'],
                        'format': best_audio['format']
                    }
                    logger.info(f"🔗 Audio recomendado para {video_format['quality']}: {best_audio['quality']}")

        # ORDENAMIENTO INTELIGENTE:
        # 1. Primero formatos COMBINADOS (video+audio)
        # 2. Luego video solo (para casos donde el frontend pueda combinar)
        # 3. Finalmente audio solo
        
        # Ordenar combined por calidad (mayor altura primero)
        combined_formats.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
        
        # Ordenar video_only por calidad
        video_only_formats.sort(key=lambda x: x.get('height', 0) or 0, reverse=True)
        
        # Ordenar audio_only por bitrate
        audio_only_formats.sort(key=lambda x: self._get_audio_bitrate(x), reverse=True)
        
        # Combinar en orden de prioridad
        formats = combined_formats + video_only_formats + audio_only_formats
        
        # Si no hay formatos pero hay URL directa
        if not formats and info.get('url'):
            formats.append({
                'quality': 'Calidad por defecto',
                'format': info.get('ext', 'mp4'),
                'resolution': 'HD',
                'size': 'Desconocido',
                'url': info['url'],
                'hasAudio': True,
                'hasVideo': True,
                'height': 720,
                'width': 1280
            })

        response = {
            'status': 'success',
            'platform': 'youtube',
            'title': info.get('title', 'Video de YouTube'),
            'thumbnail': info.get('thumbnail', ''),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Desconocido'),
            'view_count': info.get('view_count', 0),
            'method': 'yt-dlp (Optimizado)',
            'formats': formats,
            'channel': info.get('uploader', 'Desconocido'),
            'video_url': info.get('url', ''),
            'statistics': {
                'total_formats': len(formats),
                'combined_formats': len(combined_formats),
                'video_only_formats': len(video_only_formats),
                'audio_only_formats': len(audio_only_formats),
                'max_quality': self._get_max_quality(formats),
                'has_recommended_audio': best_audio is not None,
                'combinable_formats': len([f for f in video_only_formats if f.get('recommended_audio')])
            }
        }
        
        # Log detallado de lo que se encontró
        self._log_format_statistics(response['statistics'], formats)
        
        return response

    def _get_audio_bitrate(self, format_info: Dict) -> int:
        """Extrae el bitrate de audio para ordenamiento"""
        quality = format_info.get('quality', '').lower()
        if '320' in quality or 'high' in quality:
            return 320
        elif '256' in quality:
            return 256
        elif '192' in quality or 'medium' in quality:
            return 192
        elif '128' in quality or 'low' in quality:
            return 128
        return 0

    def _get_max_quality(self, formats: List[Dict]) -> str:
        """Obtiene la máxima calidad disponible"""
        video_heights = [f.get('height', 0) for f in formats if f.get('hasVideo')]
        if video_heights:
            max_height = max(video_heights)
            return f"{max_height}p"
        return "Audio Only"

    def _log_format_statistics(self, stats: Dict, formats: List[Dict]):
        """Log detallado de formatos encontrados"""
        logger.info(f"📊 ESTADÍSTICAS DE FORMATOS:")
        logger.info(f"   • Total: {stats['total_formats']}")
        logger.info(f"   • Combinados (video+audio): {stats['combined_formats']}")
        logger.info(f"   • Solo video: {stats['video_only_formats']}")
        logger.info(f"   • Solo audio: {stats['audio_only_formats']}")
        logger.info(f"   • Máxima calidad: {stats['max_quality']}")
        logger.info(f"   • Formatos combinables: {stats['combinable_formats']}")
        
        # Mostrar formatos combinables
        combinable_videos = [f for f in formats if f.get('hasVideo') and not f.get('hasAudio') and f.get('recommended_audio')]
        if combinable_videos:
            logger.info("🎯 FORMATOS COMBINABLES (frontend):")
            for fmt in combinable_videos[:3]:
                logger.info(f"     - {fmt['quality']} + {fmt['recommended_audio']['quality']}")

    def _get_resolution_display(self, format_info: Dict) -> str:
        """Obtiene la resolución en formato legible"""
        width = format_info.get('width')
        height = format_info.get('height')
        if width and height:
            return f"{width}x{height}"
        
        format_note = format_info.get('format_note', '')
        if format_note:
            return format_note
            
        # Intentar deducir de la calidad
        quality = format_info.get('quality', '').lower()
        if '1080' in quality or 'full hd' in quality:
            return "1920x1080"
        elif '720' in quality or 'hd' in quality:
            return "1280x720"
        elif '480' in quality:
            return "854x480"
        elif '360' in quality:
            return "640x360"
        elif '240' in quality:
            return "426x240"
        elif '144' in quality:
            return "256x144"
            
        return 'HD'

    def _get_size_display(self, format_info: Dict) -> str:
        """Obtiene el tamaño en formato legible"""
        filesize = format_info.get('filesize')
        if filesize:
            size_mb = filesize / (1024 * 1024)
            if size_mb < 1:
                return f"{size_mb * 1024:.1f} KB"
            return f"{size_mb:.1f} MB"
        return 'Desconocido'

    async def _extract_with_simple_format(self, url: str) -> Dict[str, Any]:
        """Extraer con formato simple como fallback"""
        try:
            ydl_opts = {
                "dumpjson": True,
                "quiet": True,
                "no_check_certificate": True,
                "geo_bypass": True,
                "noplaylist": True,
                "format": "best",
                "http_headers": self.get_platform_headers(),
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(url, download=False)
                )

            if not info:
                raise SnapTubeError("No se pudo extraer información incluso con formato simple")

            return self._build_optimized_response(info)

        except Exception as e:
            logger.error(f"❌ Falló incluso con formato simple: {e}")
            raise SnapTubeError(f"No hay formatos disponibles: {e}")

    # 🔥 NUEVO MÉTODO PARA COMBINAR AUTOMÁTICAMENTE
    async def download_and_combine(self, url: str, quality: str = "1080p", format_type: str = "mp4") -> Dict[str, Any]:
        """
        🔥 DESCARGA Y COMBINA AUTOMÁTICAMENTE video + audio
        """
        try:
            logger.info(f"🎬 Iniciando descarga combinada: {url} - Calidad: {quality}")
            
            # Configuración para combinar video + audio
            ydl_opts = {
                "format": f"bestvideo[height<={quality[:-1]}]+bestaudio/best",
                "outtmpl": os.path.join(self._temp_dir, "%(title)s_%(id)s_%(height)sp.%(ext)s"),
                "merge_output_format": format_type,
                "quiet": False,  # Cambiado a False para ver logs de ffmpeg
                "no_warnings": False,
                "no_check_certificate": True,
                "geo_bypass": True,
                "http_headers": self.get_platform_headers(),
                "postprocessors": [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': format_type,
                }],
            }

            cookies_file_path = self._ensure_cookies()
            if cookies_file_path:
                ydl_opts["cookiefile"] = cookies_file_path

            logger.info("🔄 Iniciando descarga y combinación con yt-dlp...")
            
            # Descargar y combinar
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(url, download=True)
                )

            # Encontrar el archivo descargado
            downloaded_file = None
            for file in os.listdir(self._temp_dir):
                if file.endswith(f".{format_type}"):
                    downloaded_file = os.path.join(self._temp_dir, file)
                    break

            if not downloaded_file or not os.path.exists(downloaded_file):
                raise SnapTubeError("No se pudo encontrar el archivo combinado después de la descarga")

            file_size = os.path.getsize(downloaded_file)
            
            logger.info(f"✅ Descarga combinada exitosa: {file_size} bytes - Archivo: {downloaded_file}")

            # Leer el archivo como base64 para enviar
            async with aiofiles.open(downloaded_file, 'rb') as f:
                file_content = await f.read()

            # Codificar en base64 para enviar en JSON
            file_content_b64 = base64.b64encode(file_content).decode('utf-8')

            return {
                "status": "success",
                "platform": "youtube",
                "title": info.get('title', 'Video de YouTube'),
                "file_size": file_size,
                "file_content": file_content_b64,
                "filename": os.path.basename(downloaded_file),
                "quality": quality,
                "format": format_type,
                "combined": True,  # Indicar que ya está combinado
                "download_url": f"/api/download/file/{os.path.basename(downloaded_file)}"
            }

        except yt_dlp.utils.DownloadError as e:
            logger.error(f"❌ Error yt-dlp en descarga combinada: {str(e)}")
            raise SnapTubeError(f"Error al descargar: {str(e)}")
        except Exception as e:
            logger.error(f"💥 Error inesperado en descarga combinada: {str(e)}", exc_info=True)
            raise SnapTubeError(f"Error al combinar video y audio: {str(e)}")

    # Método alternativo para streaming directo
    async def download_combined_stream(self, url: str, quality: str = "1080p") -> Dict[str, Any]:
        """
        Descarga combinada optimizada para streaming
        """
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4', dir=self._temp_dir)
            temp_path = temp_file.name
            temp_file.close()

            ydl_opts = {
                "format": f"bestvideo[height<={quality[:-1]}]+bestaudio/best",
                "outtmpl": temp_path,
                "merge_output_format": "mp4",
                "quiet": True,
                "no_check_certificate": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(url, download=True)
                )

            if not os.path.exists(temp_path):
                raise SnapTubeError("No se pudo crear el archivo combinado")

            file_size = os.path.getsize(temp_path)
            
            return {
                "status": "success", 
                "file_path": temp_path,
                "file_size": file_size,
                "title": info.get('title', 'Video'),
                "filename": f"{info.get('title', 'video')}_{quality}.mp4"
            }

        except Exception as e:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise SnapTubeError(f"Error en descarga stream: {str(e)}")

    def cleanup(self):
        """Limpia archivos temporales"""
        try:
            import shutil
            if os.path.exists(self._temp_dir):
                shutil.rmtree(self._temp_dir)
                logger.info(f"🧹 Directorio temporal limpiado: {self._temp_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Error limpiando temporales: {e}")

# Inicializar extractor
youtube_extractor = YouTubeExtractor()