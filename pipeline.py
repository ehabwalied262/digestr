import os
import time
import subprocess
import sys
import argparse
import logging
from dotenv import load_dotenv
from storage.db import Database # Ensure this is imported
from rich.console import Console
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt, Confirm

load_dotenv()

from storage.db import db
from sources.instagram import InstagramSource
from sources.tiktok import TikTokSource
from transcription.local_transcriber import LocalTranscriber
from transcription.caption_aware_transcriber import CaptionAwareTranscriber
from summarizer.groq_extractor import extractor as groq_client

console = Console()

os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename='logs/pipeline_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- LAZY LOADING TRANSCRIBERS ---
_ig_client = None
_tiktok_client = None

def get_transcriber(platform):
    """Only loads the AI model into memory when it is actually needed."""
    global _ig_client, _tiktok_client
    if platform == "tiktok":
        if _tiktok_client is None:
            _tiktok_client = CaptionAwareTranscriber()
        return _tiktok_client
    else:
        if _ig_client is None:
            _ig_client = LocalTranscriber()
        return _ig_client
# ---------------------------------

def detect_platform(url: str) -> str:
    if "instagram.com" in url:
        return "instagram"
    elif "tiktok.com" in url:
        return "tiktok"
    else:
        raise ValueError(f"Unrecognized platform URL: {url}")

def process_video(video_meta, target_lang: str, domain: str, want_summaries: bool):
    try:
        if db.is_processed(video_meta.platform_id):
            console.print(f"[dim][-] Skipping {video_meta.platform_id}: Already in database.[/dim]")
            return

        # 1. Transcribe (Using Lazy Loaded Engine)
        transcriber = get_transcriber(video_meta.platform)
        with console.status(f"[cyan][*][/cyan] Processing [bold]{video_meta.platform_id}[/bold]..."):
            transcript = transcriber.get_transcript(video_meta, target_lang, domain)
        
        if not transcript or not transcript.text:
            console.print(f"[yellow][!][/yellow] No usable transcript for {video_meta.platform_id}.")
            return

        # 2. Save Raw File
        date_str = video_meta.posted_at.strftime('%Y-%m-%d')
        transcript_dir = f"output/@{video_meta.creator_username}/transcripts"
        os.makedirs(transcript_dir, exist_ok=True)
        
        raw_path = os.path.join(transcript_dir, f"{date_str}_{video_meta.platform_id}_raw.txt")
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(transcript.text)

        # 3. Handle Summary Toggle
        if not want_summaries:
            # Skip Groq completely, just save the transcript to DB
            db.mark_processed(video_meta, raw_path, transcript.source)
            console.print(f"[bold green][✓] Saved Transcript Only:[/bold green] {raw_path}")
            return

        # 4. Clean Transcript & Summarize
        console.print(f"    [dim]-> AI Cleaning & Code-Switching Fix...[/dim]")
        cleaned_text = groq_client.clean_transcript(transcript.text, target_lang)

        clean_path = os.path.join(transcript_dir, f"{date_str}_{video_meta.platform_id}_clean.txt")
        with open(clean_path, "w", encoding="utf-8") as f:
            f.write(cleaned_text)

        console.print(f"[cyan][*][/cyan] Extracting hard data via Groq...")
        summary = groq_client.summarize(transcript, cleaned_text)

        os.makedirs(os.path.dirname(summary.file_path), exist_ok=True)
        with open(summary.file_path, "w", encoding="utf-8") as f:
            f.write(summary.markdown)

        db.mark_processed(video_meta, summary.file_path, transcript.source)
        console.print(f"[bold green][✓] Success:[/bold green] {summary.file_path}")

    except Exception as e:
        console.print(f"[bold red][X] Error processing {video_meta.platform_id}:[/bold red] {e}")
        logging.exception(f"Failed to process {video_meta.platform_id}")

def add_creator_flow(username: str, platform: str):
    source = InstagramSource() if platform == "instagram" else TikTokSource()
    username_clean = username.replace("@", "")
    
    console.print(f"\n[cyan][*][/cyan] Scanning [bold]@{username_clean}[/bold] on {platform}...")
    profile_info = source.get_profile_stats(username_clean) 
    
    panel_text = (
        f"[bold blue]@{profile_info.username}[/bold blue]\n"
        f"[yellow]{profile_info.total_posts}[/yellow] posts total\n\n"
        f"Scanned: [dim]{profile_info.scanned_at.strftime('%b %d, %Y %I:%M%p')}[/dim]"
    )
    console.print(Panel(panel_text, title="[bold cyan]Creator Registry[/bold cyan]", border_style="cyan", expand=False))

    db.add_profile(profile_info.username, platform)
    
    # --- SMART MENUS ---
    if platform == "tiktok":
        target_lang = "auto"
        domain = "general"
    else:
        console.print("\n[bold]Select Primary Language:[/bold]")
        target_lang = Prompt.ask("Language", choices=["ar", "en", "de", "auto"], default="auto")

        console.print("\n[bold]Select Content Domain (for AI vocabulary hint):[/bold]")
        domain = Prompt.ask("Domain", choices=["tech", "medical", "political", "general"], default="general")
    
    # --- SUMMARY TOGGLE ---
    want_summaries = Confirm.ask("\nDo you want to generate AI summaries for these videos?", default=True)

    console.print("\n[bold]What would you like to process?[/bold]")
    console.print("[cyan]1.[/cyan] Latest 5 posts")
    console.print("[cyan]2.[/cyan] Latest 20 posts")
    console.print("[cyan]3.[/cyan] Latest 50 posts")
    console.print("[cyan]4.[/cyan] Latest 100 posts")
    console.print(f"[magenta]5.[/magenta] ALL posts ({profile_info.total_posts} detected - Processed in chunks)")
    
    choice = IntPrompt.ask("\nSelect an option", choices=["1", "2", "3", "4", "5"])
    
    if choice == 5:
        # If the platform API is hiding the true total, default to a massive number to grab everything
        limit = profile_info.total_posts if profile_info.total_posts > 0 else 10000 
    else:
        limit_map = {1: 5, 2: 20, 3: 50, 4: 100}
        limit = limit_map[choice]
    
    console.print(f"[cyan][*][/cyan] Fetching metadata for up to [yellow]{limit}[/yellow] posts... (This may take a moment)")
    posts = source.get_recent_posts(profile_info.username, limit)
    
    start_time = time.time()
    
    # --- NEW: CHUNKED PROCESSING LOGIC ---
    chunk_size = 100
    total_videos = len(posts)
    
    if total_videos == 0:
        console.print("[yellow][!] No posts found to process.[/yellow]")
        return

    for i in range(0, total_videos, chunk_size):
        chunk = posts[i:i + chunk_size]
        current_batch = (i // chunk_size) + 1
        total_batches = (total_videos + chunk_size - 1) // chunk_size
        
        console.print(f"\n[bold magenta]📦 Starting Batch {current_batch}/{total_batches} ({len(chunk)} videos)[/bold magenta]")
        console.print("[dim]" + "-"*45 + "[/dim]")
        
        for p in chunk:
            process_video(p, target_lang, domain, want_summaries) 
            
        # Give the system a brief 5-second cooldown between massive chunks
        if current_batch < total_batches:
            console.print(f"\n[dim][~] Batch {current_batch} complete. 5-second cooldown before the next chunk...[/dim]")
            time.sleep(5)
    # -------------------------------------
        
    total_time = time.time() - start_time
    console.print(f"\n[bold magenta]🏁 Run Complete[/bold magenta]")
    console.print(f"Total time: [yellow]{total_time:.1f} seconds[/yellow] for {total_videos} videos.")

def run_step(command, description):
    """Helper to run terminal commands and show progress."""
    print(f"\n[*] {description}...")
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        print(f"❌ Error during: {description}")
        sys.exit(1)

def display_toolbar_results(username):
    """Displays the discovered topics in a 'Toolbar' style summary."""
    print("\n" + "="*50)
    print(f"       DIGESTR TOOLBAR: {username}")
    print("="*50)
    
    local_db = Database()
    clean_username = username.replace("@", "")
    
    with local_db._get_connection() as conn:
        profile = conn.execute("SELECT id FROM profiles WHERE username = ?", (clean_username,)).fetchone()
        if profile:
            clusters = conn.execute(
                "SELECT id, topic_name, video_count FROM clusters WHERE profile_id = ? AND topic_name != 'Miscellaneous (Noise)'", 
                (profile['id'],)
            ).fetchall()
            
            if not clusters:
                print("⚠️ No distinct topics found yet.")
            for cluster in clusters:
                print(f"▶️ [Topic ID: {cluster['id']}] {cluster['topic_name']} ({cluster['video_count']} videos)")
                print("-" * 50)
        else:
            print("❌ Profile not found in database.")

def main():
    parser = argparse.ArgumentParser(description="Digestr Pipeline")
    parser.add_argument("target", nargs="?", help="URL or username")
    parser.add_argument("--add", action="store_true", help="Add new creator")
    parser.add_argument("--platform", choices=["instagram", "tiktok"], default="instagram")

    args = parser.parse_args()

    if args.add and args.target:
        username = args.target
        
        # 1. Your existing download/transcription flow
        add_creator_flow(username, args.platform)
        
        # 2. THE NEW AUTOMATED CHAIN STARTS HERE
        print("\n" + "="*50)
        print(f"🚀 Starting AI Analysis Pipeline for {username}")
        print("="*50)

        clean_username = username.replace("@", "")
        csv_file = f"datasets/dataset_{clean_username}.csv"

        # Step A: Export DB to CSV
        # Make sure data_miner.py accepts --username like this
        run_step(f"python data_miner.py --username \"{username}\"", "Exporting CSV Dataset")

        # Step B: Cleaner
        run_step(f"python -m analysis.cleaner \"{username}\" \"{csv_file}\"", "Cleaning Transcripts")

        # Step C: Embedder
        run_step(f"python -m analysis.embedder \"{username}\"", "Generating Embeddings")

        # Step D: Clusterer
        run_step(f"python -m analysis.clusterer \"{username}\"", "Clustering Topics")

        # Step E: Topic Namer
        run_step(f"python -m analysis.topic_namer \"{username}\"", "Naming Topics with Groq")

        # Step F: Show Results Toolbar
        display_toolbar_results(username)

    elif args.target:
        platform = detect_platform(args.target)
        source = InstagramSource() if platform == "instagram" else TikTokSource()
        video_meta = source.get_single_post(args.target)
        db.add_profile(video_meta.creator_username, platform)
        
        # Single post defaults
        want_summaries = True 
        process_video(video_meta, "auto", "general", want_summaries)
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Assuming you have a rich console object defined somewhere above
        print("\n[!] Stopped by user.")
    except Exception as e:
        print(f"\n[FATAL] {e}")
        logging.exception("Fatal crash")