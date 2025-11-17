# debug_combiner.py
import asyncio
import logging
import sys
import os

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SnapTubeError(Exception):
    pass

class YouTubeCombinerService:
    def __init__(self):
        import tempfile
        self.temp_dir = tempfile.mkdtemp(prefix="yt_combiner_debug_")
        logger.info(f"📁 Directorio temporal creado: {self.temp_dir}")

    async def download_and_combine(self, url: str, video_itag: int = 137, audio_itag: int = 140):
        try:
            logger.info(f"🎬 DEBUG Iniciando combinación: {url}")
            logger.info(f"🎯 DEBUG Itags - Video: {video_itag}, Audio: {audio_itag}")

            # Nombres de archivos temporales
            temp_video = os.path.join(self.temp_dir, "video_temp.mp4")
            temp_audio = os.path.join(self.temp_dir, "audio_temp.m4a")
            final_output = os.path.join(self.temp_dir, "final_output.mp4")

            # Paso 1: Descargar video
            logger.info("⬇️ DEBUG Descargando video...")
            await self._download_format(url, video_itag, temp_video, "video")
            
            # Paso 2: Descargar audio  
            logger.info("⬇️ DEBUG Descargando audio...")
            await self._download_format(url, audio_itag, temp_audio, "audio")
            
            # Paso 3: Combinar con ffmpeg
            logger.info("🎞️ DEBUG Combinando con ffmpeg...")
            await self._merge_video_audio(temp_video, temp_audio, final_output)

            # Verificar resultado
            if not os.path.exists(final_output):
                raise SnapTubeError("No se pudo crear el archivo combinado")

            file_size = os.path.getsize(final_output)
            logger.info(f"✅ DEBUG Combinación exitosa: {file_size} bytes")

            return {"status": "success", "file_size": file_size}

        except Exception as e:
            logger.error(f"❌ DEBUG Error en combinación: {str(e)}")
            logger.error(f"📋 DEBUG Tipo de error: {type(e).__name__}")
            import traceback
            logger.error(f"🔍 DEBUG Traceback completo:\n{traceback.format_exc()}")
            self._cleanup_temp_files()
            raise SnapTubeError(f"Error combinando video y audio: {str(e)}")

    async def _download_format(self, url: str, itag: int, output_path: str, format_type: str):
        logger.info(f"⬇️ DEBUG Descargando {format_type} (itag {itag})...")
        
        try:
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "-f", str(itag),
                "-o", output_path,
                "--no-simulate",
                "--socket-timeout", "30",
                "--retries", "2",
                url
            ]
            
            logger.info(f"🔧 DEBUG Comando: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120.0)
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Error desconocido"
                logger.error(f"❌ DEBUG Error en subprocess: {error_msg}")
                raise SnapTubeError(f"Error descargando {format_type}: {error_msg}")
                
            if not os.path.exists(output_path):
                raise SnapTubeError(f"Archivo {format_type} no se creó: {output_path}")
                
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ DEBUG {format_type.capitalize()} descargado: {file_size} bytes")

        except asyncio.TimeoutError:
            logger.error("⏰ DEBUG Timeout en la descarga")
            raise SnapTubeError(f"Timeout descargando {format_type}")
        except Exception as e:
            logger.error(f"❌ DEBUG Error descargando {format_type}: {str(e)}")
            raise

    async def _merge_video_audio(self, video_path: str, audio_path: str, output_path: str):
        logger.info(f"🎞️ DEBUG Combinando {video_path} + {audio_path}")
        
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
            
            logger.info(f"🔧 DEBUG Comando ffmpeg: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Error desconocido"
                logger.error(f"❌ DEBUG Error en ffmpeg: {error_msg}")
                raise SnapTubeError(f"Error combinando: {error_msg}")
                
            logger.info("✅ DEBUG Combinación ffmpeg completada")

        except Exception as e:
            logger.error(f"❌ DEBUG Error en ffmpeg: {str(e)}")
            raise

    def _cleanup_temp_files(self):
        try:
            import shutil
            if os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                logger.info(f"🧹 DEBUG Directorio temporal limpiado: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"⚠️ DEBUG Error limpiando temporales: {e}")

async def main():
    """Prueba el combiner con la misma URL que falla"""
    test_url = "https://www.youtube.com/watch?v=JwsgCnBLL4A"
    
    service = YouTubeCombinerService()
    
    try:
        print("🚀 INICIANDO PRUEBA DE DEBUG...")
        result = await service.download_and_combine(
            url=test_url,
            video_itag=137,
            audio_itag=140
        )
        print(f"🎉 PRUEBA EXITOSA: {result}")
        
    except Exception as e:
        print(f"💥 PRUEBA FALLIDA: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        service._cleanup_temp_files()

if __name__ == "__main__":
    # Verificar dependencias
    print("🔍 Verificando dependencias...")
    try:
        import subprocess
        result_ytdlp = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
        result_ffmpeg = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        print(f"✅ yt-dlp: {result_ytdlp.stdout.strip()}")
        print(f"✅ ffmpeg disponible")
    except Exception as e:
        print(f"❌ Error con dependencias: {e}")
    
    asyncio.run(main())