# ====================================================================
# app/services/facebook_service.py - VERSIÓN ACTUALIZADA
# ====================================================================
import asyncio
import logging
import os
import re
import json
import tempfile
from typing import Dict, Any, Optional, List

import yt_dlp
import requests
from bs4 import BeautifulSoup

from app.services.base_extractor import BaseExtractor, SnapTubeError
from app.config import settings

logger = logging.getLogger(__name__)

# Headers predefinidos
FACEBOOK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
}

FACEBOOK_MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; SM-G960U) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/89.0.4389.72 Mobile Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}


class FacebookExtractor(BaseExtractor):
    """Extractor de videos de Facebook actualizado con lógica de yt-dlp directo."""

    @property
    def platform(self) -> str:
        return "facebook"

    def get_platform_headers(self, mobile: bool = False) -> Dict[str, str]:
        return FACEBOOK_MOBILE_HEADERS if mobile else FACEBOOK_HEADERS

    async def extract(
        self, url: str, mobile: bool = False, cookies: Optional[str] = None, **kwargs
    ) -> Dict[str, Any]:
        """Extrae información completa del video de Facebook usando yt-dlp (como en Node.js)."""
        self.validator.validate_url(url)
        
        try:
            logger.info(f"📥 Procesando Facebook URL: {url}")
            
            # Usar yt-dlp como método principal (igual que en Node.js)
            result = await self._extract_with_ytdlp(url, cookies)
            
            if result and result.get("status") == "success":
                logger.info("✅ Facebook extraction successful with yt-dlp")
                return result
            
            # Fallback a métodos manuales si yt-dlp falla
            logger.warning("yt-dlp falló, intentando métodos manuales...")
            return await self._extract_with_fallback(url, mobile, cookies)
            
        except Exception as e:
            logger.error(f"💥 Error en extracción Facebook: {str(e)}")
            raise SnapTubeError(f"Error procesando video de Facebook: {str(e)}")

    async def _extract_with_ytdlp(self, url: str, cookies: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Extrae usando yt-dlp igual que en la API Node.js anterior."""
        try:
            ydl_opts = {
                "dump_json": True,
                "quiet": True,
                "no_warnings": True,
                "no_check_certificates": True,
                "geo_bypass": True,
                "extract_flat": False,
                "http_headers": self.get_platform_headers(),
                "socket_timeout": settings.REQUEST_TIMEOUT,
            }

            # Manejar cookies si están disponibles
            temp_cookie_path = None
            if cookies:
                fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(cookies)
                ydl_opts["cookiefile"] = temp_cookie_path

            loop = asyncio.get_event_loop()
            
            def extract_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, extract_sync)
            
            if not info:
                return None

            # Procesar formatos igual que en Node.js
            formats = []
            if info.get("formats"):
                for format in info["formats"]:
                    if format.get("url") and format.get("protocol") in ["http", "https"]:
                        format_info = {
                            "quality": format.get("format_note") or "HD",
                            "format": format.get("ext") or "mp4",
                            "resolution": format.get("resolution") or "1920x1080",
                            "size": self._format_size(format.get("filesize")),
                            "url": format["url"],
                            "hasAudio": bool(format.get("audio_codec")),
                            "codec": format.get("vcodec"),
                            "hasVideo": bool(format.get("vcodec")),
                        }
                        formats.append(format_info)

            # Construir respuesta igual que en Node.js
            response = {
                "status": "success",
                "platform": "facebook",
                "title": info.get("title") or "Video de Facebook",
                "thumbnail": info.get("thumbnail") or "",
                "duration": info.get("duration") or 0,
                "width": info.get("width") or None,
                "height": info.get("height") or None,
                "method": "yt-dlp (Python)",
                "formats": formats,
                "original_url": url,
                "uploader": info.get("uploader") or "",
                "view_count": info.get("view_count") or 0,
                "description": info.get("description") or ""
            }

            return response

        except Exception as e:
            logger.warning(f"yt-dlp extraction failed: {str(e)}")
            return None
        finally:
            # Limpiar archivo temporal de cookies
            if temp_cookie_path and os.path.exists(temp_cookie_path):
                os.unlink(temp_cookie_path)

    async def _extract_with_fallback(self, url: str, mobile: bool = False, cookies: Optional[str] = None) -> Dict[str, Any]:
        """Métodos de fallback manuales."""
        methods = [
            self._extract_manual,
            self._extract_mobile_redirect
        ]

        last_error = None
        for method in methods:
            try:
                logger.info(f"Intentando fallback: {method.__name__}")
                result = await method(url, mobile)
                if result and result.get("video_url"):
                    # Asegurar que el resultado tenga el formato esperado
                    result["status"] = "success"
                    result["platform"] = "facebook"
                    result["method"] = f"fallback_{method.__name__}"
                    result["formats"] = [{
                        "quality": "HD",
                        "format": "mp4", 
                        "resolution": "1920x1080",
                        "size": "Desconocido",
                        "url": result["video_url"],
                        "hasAudio": True,
                        "hasVideo": True
                    }]
                    return result
            except Exception as e:
                last_error = e
                continue

        raise SnapTubeError(f"Todos los métodos fallaron. Último error: {last_error}")

    async def _extract_manual(self, url: str, mobile: bool = False) -> Optional[Dict[str, Any]]:
        """Fallback manual usando scraping de Facebook."""
        try:
            headers = self.get_platform_headers(mobile)
            session = requests.Session()
            response = session.get(url, headers=headers, timeout=settings.REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            video_url = (
                self._extract_from_meta_tags(soup)
                or self._extract_from_json_ld(soup)
                or self._extract_from_scripts(soup)
                or self._extract_from_video_tags(soup)
            )
            if not video_url:
                return None

            title = self._get_title(soup)
            thumbnail = self._get_thumbnail(soup)

            return {
                "title": title,
                "thumbnail": thumbnail,
                "video_url": video_url,
                "duration": 0,
                "width": None,
                "height": None,
            }

        except Exception as e:
            logger.warning(f"Scraping manual falló: {str(e)}")
            return None

    async def _extract_mobile_redirect(self, url: str, mobile: bool = True) -> Optional[Dict[str, Any]]:
        """Intento usando la versión móvil."""
        mobile_url = url.replace("www.facebook.com", "m.facebook.com")
        return await self._extract_manual(mobile_url, mobile=True)

    # ---------------- Métodos auxiliares ----------------
    def _format_size(self, size_bytes: Optional[int]) -> str:
        """Formatea el tamaño en bytes a MB."""
        if not size_bytes:
            return "Desconocido"
        return f"{(size_bytes / 1024 / 1024):.1f} MB"

    def _extract_from_meta_tags(self, soup) -> Optional[str]:
        meta_video = (soup.find("meta", property="og:video")
                      or soup.find("meta", property="og:video:url")
                      or soup.find("meta", property="og:video:secure_url"))
        if meta_video and meta_video.get("content"):
            return meta_video["content"]
        return None

    def _extract_from_json_ld(self, soup) -> Optional[str]:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    return data.get("contentUrl")
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("contentUrl"):
                            return item["contentUrl"]
            except json.JSONDecodeError:
                continue
        return None

    def _extract_from_scripts(self, soup) -> Optional[str]:
        patterns = [
            r'"browser_native_hd_url":"([^"]+)"',
            r'"browser_native_sd_url":"([^"]+)"',
            r'src:\\"([^"]+\.mp4[^\\]*)\\"',
            r'video_src":"([^"]+)"',
            r'"playable_url":"([^"]+)"',
            r'"playable_url_quality_hd":"([^"]+)"'
        ]
        for script in soup.find_all("script"):
            if not script.string:
                continue
            for pattern in patterns:
                matches = re.findall(pattern, script.string)
                if matches:
                    return matches[0].replace("\\/", "/")
        return None

    def _extract_from_video_tags(self, soup) -> Optional[str]:
        video_tag = soup.find("video")
        if video_tag:
            if video_tag.get("src"):
                return video_tag["src"]
            for source in video_tag.find_all("source"):
                if source.get("src"):
                    return source["src"]
        return None

    def _get_title(self, soup) -> str:
        title_tag = soup.find("meta", property="og:title") or soup.find("title")
        if title_tag:
            if hasattr(title_tag, "content"):
                return title_tag["content"]
            return title_tag.text.strip()
        return "Facebook Video"

    def _get_thumbnail(self, soup) -> str:
        thumb_tag = soup.find("meta", property="og:image")
        return thumb_tag["content"] if thumb_tag else ""

    # ---------------- Métodos de audio ----------------
    async def extract_audio_url(self, url: str, cookies: Optional[str] = None) -> str:
        """Extrae la URL de audio usando yt-dlp (igual que en Node.js)."""
        try:
            ydl_opts = {
                "extract_flat": False,
                "quiet": True,
                "no_warnings": True,
                "format": "bestaudio/best",
                "geo_bypass": True,
                "no_check_certificates": True,
                "http_headers": self.get_platform_headers(),
            }

            temp_cookie_path = None
            if cookies:
                fd, temp_cookie_path = tempfile.mkstemp(suffix=".txt")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(cookies)
                ydl_opts["cookiefile"] = temp_cookie_path

            loop = asyncio.get_event_loop()
            
            def extract_sync():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await loop.run_in_executor(None, extract_sync)

            # Buscar el mejor formato de audio
            audio_formats = [
                f for f in info.get("formats", [])
                if f.get("acodec") != "none" and f.get("vcodec") == "none" and f.get("url")
            ]
            
            if audio_formats:
                audio_formats.sort(key=lambda f: f.get("abr") or 0, reverse=True)
                return audio_formats[0]["url"]

            # Fallback: usar el formato que tenga audio
            for format in info.get("formats", []):
                if format.get("acodec") != "none" and format.get("url"):
                    return format["url"]

            raise SnapTubeError("No se encontró URL de audio")

        finally:
            if temp_cookie_path and os.path.exists(temp_cookie_path):
                os.unlink(temp_cookie_path)

    async def extract_audio_info(self, url: str, cookies: Optional[str] = None) -> Dict[str, Any]:
        """Extrae información completa para descarga de audio."""
        try:
            # Obtener información del video primero
            video_info = await self.extract(url, cookies=cookies)
            
            # Extraer URL de audio
            audio_url = await self.extract_audio_url(url, cookies=cookies)
            
            return {
                "status": "success",
                "platform": "facebook",
                "title": video_info.get("title", "Facebook Audio"),
                "thumbnail": video_info.get("thumbnail", ""),
                "duration": video_info.get("duration", 0),
                "audio_url": audio_url,
                "filename": f"facebook_audio_{video_info.get('uploader', 'unknown')}_{video_info.get('duration', 0)}.mp3",
                "method": "yt-dlp audio extraction"
            }
            
        except Exception as e:
            logger.error(f"Error en extracción de audio: {str(e)}")
            # Fallback: usar el video como fuente de audio
            video_info = await self.extract(url, cookies=cookies)
            return {
                "status": "success",
                "platform": "facebook", 
                "title": video_info.get("title", "Facebook Audio"),
                "thumbnail": video_info.get("thumbnail", ""),
                "duration": video_info.get("duration", 0),
                "audio_url": video_info.get("video_url"),  # Usar URL de video como fallback
                "filename": f"facebook_audio_fallback_{video_info.get('duration', 0)}.mp3",
                "method": "fallback video url",
                "warning": "Audio extraído del stream de video"
            }
    # ---------------- Procesamiento FFmpeg ----------------
    async def stream_audio_with_thumbnail(self, audio_url: str, thumbnail_url: str):
        """Genera un stream de FFmpeg fusionando audio y miniatura (M4A Rápido)."""
        import subprocess

        # Comando FFmpeg optimizado (copia audio, pega imagen, formato ipod/m4a)
        cmd = [
            'ffmpeg',
            '-i', audio_url,
            '-i', thumbnail_url,
            '-map', '0:0',
            '-map', '1:0',
            '-c', 'copy',
            '-disposition:v:1', 'attached_pic',
            '-f', 'ipod',  # Formato contenedor MP4/M4A friendly
            '-'  # Salida a stdout
        ]
        
        logger.info(f"🎵 Iniciando FFmpeg Merge: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Capturar errores pero no mezclar con output
            bufsize=10**7 # Buffer grande
        )
        
        # Generador para StreamingResponse
        def stream_generator():
            try:
                while True:
                    chunk = process.stdout.read(64 * 1024) # 64KB chunks
                    if not chunk:
                        break
                    yield chunk
            except Exception as e:
                logger.error(f"Error streaming ffmpeg: {e}")
                process.kill()
            finally:
                process.stdout.close()
                process.wait()
                
                # Check for errors if failed
                if process.returncode != 0:
                    error_out = process.stderr.read()
                    logger.error(f"FFmpeg Error Output: {error_out}")

        return stream_generator()