# app/routes/download_routes.py
import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from app.services.youtube_service import YouTubeExtractor
from app.services.tiktok_service import TikTokExtractor  
from app.services.facebook_service import FacebookExtractor
from app.services.base_extractor import SnapTubeError

logger = logging.getLogger(__name__)
router = APIRouter()

class DownloadRequest(BaseModel):
    url: str
    cookies: Optional[str] = None
    force_ytdlp: Optional[bool] = False

# Inicializar extractores
yt_extractor = YouTubeExtractor()
tk_extractor = TikTokExtractor()
fb_extractor = FacebookExtractor()

@router.post("/youtube/download")
async def download_youtube(request: DownloadRequest):
    """
    Endpoint para YouTube - Formato compatible con frontend
    """
    try:
        logger.info(f"🎬 Procesando YouTube: {request.url}")
        
        result = await yt_extractor.extract(
            url=request.url,
            cookies=request.cookies,
            force_ytdlp=request.force_ytdlp
        )
        
        # Asegurar formato compatible con frontend
        response = {
            "status": "success",
            "platform": "youtube",
            "title": result.get("title", "Video de YouTube"),
            "thumbnail": result.get("thumbnail", ""),
            "duration": result.get("duration", 0),
            "uploader": result.get("uploader", "Desconocido"),
            "view_count": result.get("view_count", 0),
            "method": result.get("method", "ytdlp"),
            "formats": result.get("formats", []),
            "channel": result.get("uploader", "Desconocido")
        }
        
        logger.info(f"✅ YouTube procesado exitosamente: {response['title']}")
        return response
        
    except SnapTubeError as e:
        logger.error(f"❌ Error YouTube: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado YouTube: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.post("/tiktok/download") 
async def download_tiktok(request: DownloadRequest):
    """
    Endpoint para TikTok - Formato compatible con frontend
    """
    try:
        logger.info(f"🎬 Procesando TikTok: {request.url}")
        
        result = await tk_extractor.extract(request.url)
        
        # Adaptar formato para frontend
        response = {
            "status": "success", 
            "platform": "tiktok",
            "title": result.get("title", "Video de TikTok"),
            "thumbnail": result.get("thumbnail", ""),
            "duration": result.get("duration", 0),
            "uploader": result.get("uploader", "TikTok User"),
            "view_count": result.get("view_count", 0),
            "method": result.get("method", "tiktok_api"),
            "formats": result.get("formats", []),
            "channel": result.get("author", "TikTok User")
        }
        
        logger.info(f"✅ TikTok procesado exitosamente: {response['title']}")
        return response
        
    except SnapTubeError as e:
        logger.error(f"❌ Error TikTok: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado TikTok: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.post("/facebook/download")
async def download_facebook(request: DownloadRequest):
    """
    Endpoint para Facebook - Formato compatible con frontend
    """
    try:
        logger.info(f"🎬 Procesando Facebook: {request.url}")
        
        result = await fb_extractor.extract(request.url)
        
        # Adaptar formato para frontend
        response = {
            "status": "success",
            "platform": "facebook", 
            "title": result.get("title", "Video de Facebook"),
            "thumbnail": result.get("thumbnail", ""),
            "duration": result.get("duration", 0),
            "uploader": result.get("uploader", "Facebook User"),
            "view_count": result.get("view_count", 0),
            "method": result.get("method", "facebook_api"),
            "formats": result.get("formats", []),
            "channel": result.get("author", "Facebook User")
        }
        
        logger.info(f"✅ Facebook procesado exitosamente: {response['title']}")
        return response
        
    except SnapTubeError as e:
        logger.error(f"❌ Error Facebook: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"💥 Error inesperado Facebook: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/health")
async def health_check():
    """Endpoint de salud"""
    return {
        "status": "healthy",
        "service": "FreeDownloaderPro API",
        "version": "1.0.0"
    }