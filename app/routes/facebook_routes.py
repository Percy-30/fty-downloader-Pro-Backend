# app/routes/facebook_routes.py - VERSIÓN CON BODY
import logging
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
from app.services.facebook_service import FacebookExtractor

# Configurar logger
logger = logging.getLogger(__name__)

router = APIRouter()
facebook_extractor = FacebookExtractor()

# Modelo para el request body
class FacebookRequest(BaseModel):
    url: str

@router.post("/info")
async def get_facebook_info(request: FacebookRequest):
    """Endpoint para obtener información de videos de Facebook."""
    try:
        url = request.url
        logger.info(f"📥 Facebook info request: {url}")
        
        if not url or ("facebook.com" not in url and "fb.watch" not in url):
            raise HTTPException(status_code=400, detail="URL de Facebook inválida")
        
        result = await facebook_extractor.extract(url)
        
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result.get("message", "Error procesando video"))
            
        return result
        
    except Exception as e:
        logger.error(f"💥 Facebook info error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.post("/audio")
async def download_facebook_audio(request: FacebookRequest):
    """Endpoint para obtener información de audio de Facebook."""
    try:
        url = request.url
        logger.info(f"🎵 Facebook audio request: {url}")
        
        if not url or ("facebook.com" not in url and "fb.watch" not in url):
            raise HTTPException(status_code=400, detail="URL de Facebook inválida")
        
        result = await facebook_extractor.extract_audio_info(url)
        
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result.get("message", "Error procesando audio"))
            
        return result
        
    except Exception as e:
        logger.error(f"💥 Facebook audio error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")

@router.post("/video")
async def download_facebook_video(
    request: FacebookRequest,
    quality: str = "best"
):
    """Endpoint para obtener información de video de Facebook."""
    try:
        url = request.url
        logger.info(f"🎬 Facebook video request: {url}, quality: {quality}")
        
        if not url or ("facebook.com" not in url and "fb.watch" not in url):
            raise HTTPException(status_code=400, detail="URL de Facebook inválida")
        
        # Obtener información completa
        result = await facebook_extractor.extract(url)
        
        if result.get("status") != "success":
            raise HTTPException(status_code=400, detail=result.get("message", "Error procesando video"))
        
        # Filtrar por calidad si se especifica
        if quality != "best" and result.get("formats"):
            filtered_formats = [f for f in result["formats"] if quality.lower() in f.get("quality", "").lower()]
            if filtered_formats:
                result["formats"] = filtered_formats
                result["selected_quality"] = quality
        
        return result
        
    except Exception as e:
        logger.error(f"💥 Facebook video error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")