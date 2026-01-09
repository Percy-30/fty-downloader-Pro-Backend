# app/routes/combiner_routes.py
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse  # ✅ NUEVO
from pydantic import BaseModel
from typing import Optional
import base64
import os
import shutil

from app.services.youtube_combiner_service import youtube_combiner
from app.services.base_extractor import SnapTubeError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/combiner", tags=["Combiner"])

class CombineRequest(BaseModel):
    url: str
    video_itag: Optional[int] = None
    audio_itag: Optional[int] = None
    quality: Optional[str] = "1080p"

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
            "4k": (313, 140)
        }
        
        # ✅ USAR ITAGS ESPECÍFICOS SI SE PROVEEN (INCLUSO SI SON NONE)
        # Si el frontend envía itags, los respetamos. Si no envía ninguno, usamos el mapa.
        if request.video_itag is not None or request.audio_itag is not None:
            video_itag = request.video_itag
            audio_itag = request.audio_itag
        else:
            video_itag, audio_itag = quality_to_itag.get(request.quality, (137, 140))

        logger.info(f"🎯 Itags Finales - Video: {video_itag}, Audio: {audio_itag}")
        
        # ✅ EJECUTAR COMBINACIÓN (O DESCARGA SIMPLE SI FALTA UNO)
        result = await youtube_combiner.download_and_combine(
            url=request.url,
            video_itag=video_itag,
            audio_itag=audio_itag
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

        if is_audio_only:
            media_type = "audio/mpeg" if "audio" in result.get("filename", "").lower() else "audio/mp4"
            ext = "mp3" if "audio/mpeg" in media_type else "m4a"
        else:
            media_type = "video/mp4"
            ext = "mp4"

        # Re-construir filename si es necesario para asegurar extensión correcta
        base_filename = result.get("filename", f"youtube_{request.quality}_{video_itag or audio_itag}")
        if not base_filename.endswith(f".{ext}"):
            base_filename = base_filename.rsplit('.', 1)[0] + f".{ext}"
        
        filename = base_filename.replace('"', '').replace("'", "")
        
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
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Content-Length": str(file_size),
                "X-File-Size": str(file_size),
                "X-Video-Itag": str(video_itag or ""),
                "X-Audio-Itag": str(audio_itag or ""),
                "X-Is-Audio": "true" if is_audio_only else "false",
                "X-Is-Video": "false" if is_audio_only else "true",
                "Access-Control-Expose-Headers": "Content-Disposition, Content-Length, X-File-Size, X-Video-Itag, X-Audio-Itag, X-Is-Audio, X-Is-Video"
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