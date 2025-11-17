# test_youtube_combiner.py
import asyncio
import logging
import sys
import os

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Mock de SnapTubeError si no existe
class SnapTubeError(Exception):
    pass

# Tu servicio (copiado directamente)
class YouTubeCombinerService:
    """
    Servicio especializado para combinar video + audio de YouTube
    usando yt-dlp + ffmpeg directamente
    """

    def __init__(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp(prefix="yt_combiner_")
        logger.info(f"📁 Directorio temporal creado: {self.temp_dir}")

    async def download_and_combine(
        self, 
        url: str, 
        video_itag: int = 401,  # 2160p MP4 por defecto
        audio_itag: int = 140,  # M4A medium por defecto
        output_filename: str = None
    ):
        """
        Descarga y combina video + audio automáticamente
        """
        try:
            logger.info(f"🎬 Iniciando combinación: {url}")
            logger.info(f"🎯 Itags - Video: {video_itag}, Audio: {audio_itag}")

            # Nombres de archivos temporales
            temp_video = os.path.join(self.temp_dir, "video_temp.mp4")
            temp_audio = os.path.join(self.temp_dir, "audio_temp.m4a")
            
            if not output_filename:
                output_filename = f"youtube_combined_{video_itag}_{audio_itag}.mp4"
            
            final_output = os.path.join(self.temp_dir, output_filename)

            # Paso 1: Descargar video
            await self._download_format(url, video_itag, temp_video, "video")
            
            # Paso 2: Descargar audio  
            await self._download_format(url, audio_itag, temp_audio, "audio")
            
            # Paso 3: Combinar con ffmpeg
            await self._merge_video_audio(temp_video, temp_audio, final_output)

            # Verificar que el archivo final existe
            if not os.path.exists(final_output):
                raise SnapTubeError("No se pudo crear el archivo combinado")

            file_size = os.path.getsize(final_output)
            logger.info(f"✅ Combinación exitosa: {file_size} bytes")

            return {
                "status": "success",
                "filename": output_filename,
                "file_size": file_size,
                "video_itag": video_itag,
                "audio_itag": audio_itag,
                "temp_path": final_output
            }

        except Exception as e:
            logger.error(f"❌ Error en combinación: {str(e)}")
            self._cleanup_temp_files()
            raise SnapTubeError(f"Error combinando video y audio: {str(e)}")

    async def _download_format(self, url: str, itag: int, output_path: str, format_type: str):
        """Descarga un formato específico usando yt-dlp"""
        logger.info(f"⬇️ Descargando {format_type} (itag {itag}) → {output_path}")
        
        try:
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "-f", str(itag),
                "-o", output_path,
                "--no-simulate",
                url
            ]
            
            # Ejecutar en subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Error desconocido"
                logger.error(f"❌ Error en subprocess: {error_msg}")
                raise SnapTubeError(f"Error descargando {format_type}: {error_msg}")
                
            if not os.path.exists(output_path):
                raise SnapTubeError(f"Archivo {format_type} no se creó: {output_path}")
                
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ {format_type.capitalize()} descargado: {file_size} bytes")

        except Exception as e:
            logger.error(f"❌ Error descargando {format_type}: {str(e)}")
            raise

    async def _merge_video_audio(self, video_path: str, audio_path: str, output_path: str):
        """Combina video + audio usando ffmpeg"""
        logger.info(f"🎞️ Combinando {video_path} + {audio_path} → {output_path}")
        
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
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Error desconocido"
                logger.error(f"❌ Error en ffmpeg: {error_msg}")
                raise SnapTubeError(f"Error combinando: {error_msg}")
                
            logger.info("✅ Combinación ffmpeg completada")

        except Exception as e:
            logger.error(f"❌ Error en ffmpeg: {str(e)}")
            raise

    def _cleanup_temp_files(self):
        """Limpia archivos temporales"""
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"🧹 Directorio temporal limpiado: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"⚠️ Error limpiando temporales: {e}")

# Función de prueba principal
async def main():
    """Prueba el servicio con un video de YouTube"""
    
    # URL de prueba (usa una corta)
    test_url = "https://www.youtube.com/watch?v=JwsgCnBLL4A"
    
    # Itags más compatibles (1080p)
    video_itag = 137  # 1080p video
    audio_itag = 140  # Audio m4a
    
    service = YouTubeCombinerService()
    
    try:
        logger.info("🚀 Iniciando prueba del YouTubeCombinerService...")
        
        result = await service.download_and_combine(
            url=test_url,
            video_itag=video_itag,
            audio_itag=audio_itag,
            output_filename="test_video_1080p.mp4"
        )
        
        logger.info(f"🎉 ¡PRUEBA EXITOSA!")
        logger.info(f"📊 Resultado: {result}")
        
        # Mostrar archivo resultante
        if os.path.exists(result["temp_path"]):
            file_size_mb = result["file_size"] / (1024 * 1024)
            logger.info(f"💾 Archivo creado: {result['temp_path']} ({file_size_mb:.2f} MB)")
        
    except Exception as e:
        logger.error(f"💥 PRUEBA FALLIDA: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Limpiar
        service._cleanup_temp_files()

if __name__ == "__main__":
    # Verificar dependencias primero
    print("🔍 Verificando dependencias...")
    try:
        import subprocess
        subprocess.run(["yt-dlp", "--version"], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True)
        print("✅ Dependencias verificadas")
    except subprocess.CalledProcessError:
        print("❌ Error: yt-dlp o ffmpeg no están instalados")
        sys.exit(1)
    
    # Ejecutar prueba
    asyncio.run(main())