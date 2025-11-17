# app/routes/youtube_routes.py (NUEVO ARCHIVO)
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.youtube_service import YouTubeExtractor
from app.services.base_extractor import SnapTubeError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/youtube", tags=["YouTube"])

class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = "1080p"
    format_type: Optional[str] = "mp4"

# Inicializar extractor
yt_extractor = YouTubeExtractor()

@router.post("/extract")
async def extract_youtube_info(request: DownloadRequest):
    """
    Extrae información del video de YouTube
    """
    try:
        logger.info(f"🎬 Extrayendo información YouTube: {request.url}")
        
        result = await yt_extractor.extract(url=request.url)
        
        logger.info(f"✅ YouTube extraído exitosamente: {result['title']}")
        return result
        
    except SnapTubeError as e:
        logger.error(f"❌ Error YouTube: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado YouTube: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.post("/download")
async def download_youtube_combined(request: DownloadRequest):
    """
    🔥 NUEVO ENDPOINT: Descarga y combina video + audio automáticamente
    """
    try:
        logger.info(f"🎬 Descarga combinada YouTube: {request.url} - Calidad: {request.quality}")
        
        result = await yt_extractor.download_and_combine(
            url=request.url,
            quality=request.quality,
            format_type=request.format_type
        )
        
        logger.info(f"✅ Descarga combinada exitosa: {result['file_size']}")
        return result
        
    except SnapTubeError as e:
        logger.error(f"❌ Error en descarga combinada: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado en descarga: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/audio")
async def get_youtube_audio(url: str):
    """
    Extrae solo el audio de YouTube
    """
    try:
        logger.info(f"🎵 Extrayendo audio YouTube: {url}")
        
        result = await yt_extractor.extract_audio_url(url)
        
        logger.info("✅ Audio extraído exitosamente")
        return result
        
    except SnapTubeError as e:
        logger.error(f"❌ Error extrayendo audio: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado en audio: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")