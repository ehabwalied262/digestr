import os
import glob
import re
import yt_dlp
from faster_whisper import WhisperModel
from rich.console import Console
from models import Transcript, VideoMeta
from utils.vocabularies import DOMAIN_VOCABS

console = Console()

class CaptionAwareTranscriber:
    def __init__(self):
        # We initialize a dedicated model for TikTok here
        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            os.environ["HF_TOKEN"] = hf_token
            
        console.print("[dim]  [~] Initializing TikTok 'Caption-Aware' engine...[/dim]")
        self.model = WhisperModel("small", device="cpu", compute_type="int8")

    def clean_vtt(self, vtt_content: str) -> str:
        """Strips timestamps, HTML tags, and duplicate scrolling lines from TikTok captions."""
        lines = vtt_content.split('\n')
        cleaned_lines = []
        last_line = ""
        
        for line in lines:
            if 'WEBVTT' in line or '-->' in line or line.startswith('Kind:') or line.startswith('Language:'):
                continue
            
            clean_line = re.sub(r'<[^>]+>', '', line).strip()
            
            if clean_line and clean_line != last_line:
                cleaned_lines.append(clean_line)
                last_line = clean_line
                
        return " ".join(cleaned_lines)

    def get_transcript(self, video_meta: VideoMeta, target_lang: str, domain: str) -> Transcript:
        audio_ext = f"audio_{video_meta.platform_id}"
        audio_file = f"{audio_ext}.mp3"

        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
            'outtmpl': audio_ext,
            'quiet': True,
            'no_warnings': True,
            # --- CAPTION SNATCHER SETTINGS ---
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'ar', 'de', 'all'] 
        }

        vocab_hint = DOMAIN_VOCABS.get(domain, "")

        try:
            console.print("    [dim]-> Hunting for native captions & extracting audio...[/dim]")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_meta.url])
            
            subtitle_files = glob.glob(f"{audio_ext}.*.vtt")
            
            if subtitle_files:
                sub_file = subtitle_files[0]
                console.print(f"    [bold green]-> Native Captions Snatched! Bypassing Whisper AI...[/bold green]")
                
                with open(sub_file, 'r', encoding='utf-8') as f:
                    raw_vtt = f.read()
                    
                clean_text = self.clean_vtt(raw_vtt)
                
                if clean_text.strip():
                    return Transcript(video_meta, clean_text.strip(), None, "native_caption", target_lang, None)
            
            console.print(f"    [yellow]-> No captions found. Spinning up AI Fallback ({target_lang})...[/yellow]")
            segments, _ = self.model.transcribe(
                audio_file, 
                language=None if target_lang == "auto" else target_lang,
                initial_prompt=vocab_hint if vocab_hint else None,
                beam_size=5
            )
            
            full_text = " ".join([s.text for s in segments])
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

