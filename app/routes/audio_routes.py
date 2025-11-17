# app/routes/audio_routes.py
import logging
from fastapi import APIRouter, HTTPException, Query
from app.utils.validators import URLValidator
from app.services.youtube_service import YouTubeExtractor
from app.services.base_extractor import SnapTubeError

logger = logging.getLogger(__name__)
router = APIRouter()

validator = URLValidator()
yt_extractor = YouTubeExtractor()

@router.get("/audio")
async def get_audio_url(url: str = Query(..., description="URL del video")):
    """
    Extrae URL de audio - Compatible con frontend
    """
    try:
        platform = validator.detect_platform(url)
        logger.info(f"🔍 Plataforma detectada para audio: {platform}")

        if platform == "youtube":
            result = await yt_extractor.extract_audio_url(url)
            return {
                "status": "success",
                "audio_url": result["audio_url"],
                "metadata": result["metadata"]
            }
        else:
            # Para otras plataformas, usar el extractor normal y buscar formatos de audio
            raise HTTPException(status_code=400, detail="Extracción de audio solo disponible para YouTube por ahora")

    except SnapTubeError as e:
        logger.error(f"❌ Error extrayendo audio: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Error inesperado en audio: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")