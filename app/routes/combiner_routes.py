# app/routes/combiner_routes.py
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse  # ✅ NUEVO
from pydantic import BaseModel
from typing import Optional
import base64
import os
import shutil
import time
import asyncio
from app.config import settings

from app.services.youtube_combiner_service import youtube_combiner
from app.services.base_extractor import SnapTubeError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/combiner", tags=["Combiner"])

class CombineRequest(BaseModel):
    url: str
    video_itag: Optional[int] = None
    audio_itag: Optional[int] = None
    quality: Optional[str] = "1080p"
    format_type: Optional[str] = "mp4"

@router.post("/youtube/combine")
async def combine_youtube_video_audio(request: CombineRequest):
    """
    🔥 ENDPOINT PRINCIPAL: Combina video + audio usando STREAMING
    """
    temp_dir = None
    try:
        logger.info(f"🎬 Combinación solicitada: {request.url}")
        
        # ✅ MAPEO DE CALIDAD A ITAGS
        quality_to_itag = {
            "144p": (160, 140),
            "240p": (133, 140),
            "360p": (134, 140), 
            "480p": (135, 140),
            "720p": (136, 140),
            "1080p": (137, 140),
            "1440p": (271, 140),  # VP9 1440p
            "2160p": (313, 140),  # VP9 4K
            "4k": (313, 140),
            "mp3": (None, 140),
            "audio": (None, 140)
        }
        
        if request.video_itag is not None or "audio_itag" in request.dict(exclude_unset=True):
            video_itag = request.video_itag
            audio_itag = request.audio_itag
        else:
            # Si el format_type es mp3, forzamos calidad de solo audio
            effective_quality = "mp3" if request.format_type == "mp3" else request.quality
            video_itag, audio_itag = quality_to_itag.get(effective_quality, (137, 140))

        # 🔥 SEGURIDAD TOTAL: Si el usuario quiere mp3 o audio, INVALIDAR cualquier itag de video
        if request.format_type in ["mp3", "audio"] or request.quality in ["mp3", "audio"]:
            logger.info("强制音频模式: 丢弃视频 iTAG.")
            video_itag = None
            if not audio_itag: 
                audio_itag = 140 # Default audio M4A

        logger.info(f"🎯 Itags Finales Procesados - Video: {video_itag}, Audio: {audio_itag}")
        
        # ✅ EJECUTAR COMBINACIÓN (O DESCARGA SIMPLE SI FALTA UNO)
        result = await youtube_combiner.download_and_combine(
            url=request.url,
            video_itag=video_itag,
            audio_itag=audio_itag,
            quality=request.quality,
            format_type=request.format_type
        )
        
        # ✅ VERIFICAR RESULTADO
        if result["status"] != "success":
            raise SnapTubeError("La combinación no fue exitosa")
        
        temp_dir = result.get("temp_dir")
        final_output = result.get("temp_path")
        
        # ✅ DETECTAR TIPO DE CONTENIDO FINAL
        is_audio_only = audio_itag and not video_itag
        is_video_only = video_itag and not audio_itag
        is_combined = video_itag and audio_itag

        if not video_itag and audio_itag:
            media_type = "audio/mpeg" if "mp3" in result.get("filename", "").lower() else "audio/mp4"
            ext = "mp3" if media_type == "audio/mpeg" else "m4a"
            filename = f"youtube_audio_{audio_itag}_{int(time.time())}.{ext}"
        elif video_itag and not audio_itag:
            media_type = "video/mp4"
            ext = request.format_type or "mp4"
            filename = f"youtube_video_{video_itag}_{int(asyncio.get_event_loop().time())}.{ext}"
        else:
            media_type = "video/mp4"
            ext = "mp4"
            filename = f"youtube_combined_{video_itag}_{audio_itag}_{int(time.time())}.{ext}"
        
        file_size = result.get("file_size", 0)
        logger.info(f"✅ Archivo listo para streaming: {file_size} bytes ({media_type})")
        
        # ✅ STREAMING RESPONSE - EVITA CARGAR EN MEMORIA
        def file_stream():
            try:
                with open(final_output, 'rb') as file:
                    while chunk := file.read(16384):  # 16KB chunks para mejor performance en streams
                        yield chunk
            finally:
                # Limpieza después del streaming
                if temp_dir and os.path.exists(temp_dir):
                    try:
                        shutil.rmtree(temp_dir)
                        logger.info(f"🧹 Directorio temporal limpiado: {temp_dir}")
                    except Exception as e:
                        logger.warning(f"⚠️ Error limpiando {temp_dir}: {e}")
        
        return StreamingResponse(
            file_stream(),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(file_size),
                "X-File-Size": str(file_size),
                "Access-Control-Expose-Headers": "Content-Disposition, Content-Length, X-File-Size"
            }
        )
        
    except SnapTubeError as e:
        logger.error(f"❌ Error SnapTube en combinación: {str(e)}")
        # Limpieza en caso de error
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado en combinación: {str(e)}")
        import traceback
        logger.error(f"📋 Traceback completo:\n{traceback.format_exc()}")
        # Limpieza en caso de error
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")