import subprocess
import os
import yt_dlp

# ==============================
# CONFIGURACIÓN
# ==============================
url = "https://www.youtube.com/watch?v=JwsgCnBLL4A&list=RDnlXqp3FVrq8&index=7"  # ← tu enlace YouTube

output_video = "video.mp4"
output_audio = "audio.m4a"
output_final = "final_video.mp4"

# Itags (usa los del JSON que me pasaste)
VIDEO_ITAG = 401   # 2160p MP4
AUDIO_ITAG = 140   # M4A medium
# ==============================


def download_format(itag, output_name):
    """Descarga un formato específico usando yt-dlp"""
    print(f"⬇️ Descargando itag {itag} → {output_name}")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", str(itag),
        "-o", output_name,
        url
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Descarga completada: {output_name}")


def merge_video_audio(video_path, audio_path, output_path):
    """Une video + audio usando ffmpeg"""
    print(f"🎞️ Uniendo {video_path} + {audio_path} → {output_path}")
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    subprocess.run(cmd, check=True)
    print(f"✅ Archivo final creado: {output_path}")


if __name__ == "__main__":
    try:
        # Descargar video y audio
        download_format(VIDEO_ITAG, output_video)
        download_format(AUDIO_ITAG, output_audio)

        # Unirlos
        merge_video_audio(output_video, output_audio, output_final)

        # (Opcional) Limpiar archivos temporales
        os.remove(output_video)
        os.remove(output_audio)

        print("\n🎉 ¡Proceso completo! Archivo final:")
        print(os.path.abspath(output_final))

    except subprocess.CalledProcessError as e:
        print("❌ Error durante el proceso:", e)
