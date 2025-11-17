# app/routes/combiner_routes.py
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import base64

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
    🔥 ENDPOINT PRINCIPAL: Combina video + audio usando el servicio simple
    """
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
            "1440p": (400, 140),
            "2160p": (401, 140),
            "4k": (401, 140)
        }
        
        # ✅ USAR ITAGS ESPECÍFICOS O MAPEAR DESDE CALIDAD
        if request.video_itag is not None and request.audio_itag is not None:
            video_itag = request.video_itag
            audio_itag = request.audio_itag
        else:
            video_itag, audio_itag = quality_to_itag.get(request.quality, (137, 140))

        logger.info(f"🎯 Itags - Video: {video_itag}, Audio: {audio_itag}")
        
        # ✅ EJECUTAR COMBINACIÓN
        result = await youtube_combiner.download_and_combine(
            url=request.url,
            video_itag=video_itag,
            audio_itag=audio_itag
        )
        
        # ✅ VERIFICAR Y PREPARAR RESPUESTA
        if result["status"] != "success":
            raise SnapTubeError("La combinación no fue exitosa")
            
        file_content = result.get("file_content")
        if not file_content:
            raise SnapTubeError("No se obtuvo contenido del archivo")
        
        file_size = len(file_content)
        logger.info(f"✅ Archivo listo para enviar: {file_size} bytes")
        
        # ✅ CONVERTIR A BASE64 DE FORMA SEGURA
        try:
            file_content_b64 = base64.b64encode(file_content).decode('utf-8')
            logger.info(f"✅ Base64 encoding exitoso: {len(file_content_b64)} caracteres")
        except Exception as e:
            logger.error(f"❌ Error en encoding base64: {str(e)}")
            raise SnapTubeError(f"Error procesando archivo: {str(e)}")
        
        # ✅ PREPARAR RESPUESTA FINAL
        response_data = {
            "status": "success",
            "file_content": file_content_b64,
            "filename": result["filename"],
            "file_size": file_size,
            "video_itag": video_itag,
            "audio_itag": audio_itag,
            "combined": True,
            "quality": request.quality,
            "method": "combiner_service"
        }
        
        logger.info(f"✅ Combinación completada exitosamente: {result['filename']} ({file_size} bytes)")
        return response_data
        
    except SnapTubeError as e:
        logger.error(f"❌ Error SnapTube en combinación: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado en combinación: {str(e)}")
        import traceback
        logger.error(f"📋 Traceback completo:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/youtube/formats/{url:path}")
async def get_available_formats(url: str):
    """
    Obtiene los itags disponibles para combinación
    """
    try:
        logger.info(f"🔍 Obteniendo formatos disponibles: {url}")
        
        result = await youtube_combiner.get_available_itags(url)
        return result
        
    except SnapTubeError as e:
        logger.error(f"❌ Error obteniendo formatos: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")