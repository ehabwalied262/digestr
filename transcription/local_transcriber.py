import os
import yt_dlp
from faster_whisper import WhisperModel
from rich.console import Console
from models import Transcript, VideoMeta
from utils.vocabularies import DOMAIN_VOCABS # Import your new dictionary

console = Console()

class TranscriptionError(Exception):
    pass

class LocalTranscriber:
    def __init__(self):
        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            os.environ["HF_TOKEN"] = hf_token
            
        console.print("[dim]  [~] Initializing Whisper 'small' engine...[/dim]")
        self.model = WhisperModel("small", device="cpu", compute_type="int8")

    def get_transcript(self, video_meta: VideoMeta, target_lang: str, domain: str) -> Transcript:
        audio_ext = f"audio_{video_meta.platform_id}"
        audio_file = f"{audio_ext}.mp3"

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'outtmpl': audio_ext,
            'quiet': True,
            'no_warnings': True
        }

        # Fetch the correct dictionary based on the user's choice
        vocab_hint = DOMAIN_VOCABS.get(domain, "")

        try:
            console.print("    [dim]-> Extracting audio via yt-dlp...[/dim]")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_meta.url])
            
            console.print(f"    [dim]-> Transcribing (Lang: {target_lang} | Domain: {domain})...[/dim]")
            segments, _ = self.model.transcribe(
                audio_file, 
                language=None if target_lang == "auto" else target_lang,
                initial_prompt=vocab_hint if vocab_hint else None, # Inject the dictionary here!
                beam_size=5
            )
            
            full_text = " ".join([s.text for s in segments])
            if not full_text.strip():
                raise TranscriptionError("Whisper returned empty text.")
                
            return Transcript(video_meta, full_text.strip(), None, "local_whisper_small", target_lang, None)
            
        finally:
            # Sweeper: Find ANY file starting with this exact video ID and delete it
            # This catches .mp3, .vtt, .m4a, and extensionless raw files left by crashes
            for stray_file in glob.glob(f"{audio_ext}*"):
                try:
                    if os.path.exists(stray_file):
                        os.remove(stray_file)
                except Exception as e:
                    console.print(f"[dim][!] Could not clean up {stray_file}: {e}[/dim]")
