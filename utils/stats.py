# utils/stats.py
import time
from datetime import timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

class StatsTracker:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.total_attempted = 0
        self.success_count = 0
        self.cache_hits = 0  # Videos skipped via DB check
        self.error_429_count = 0
        self.error_404_count = 0
        self.api_transcriptions = 0
        self.whisper_transcriptions = 0
        self.whisper_total_time = 0.0

    def start_run(self):
        self.start_time = time.time()

    def end_run(self):
        self.end_time = time.time()

    def log_whisper_run(self, duration: float):
        self.whisper_transcriptions += 1
        self.whisper_total_time += duration

    def generate_report(self, creator_name: str):
        if not self.start_time or not self.end_time:
            return
            
        total_duration = self.end_time - self.start_time
        success_rate = (self.success_count / self.total_attempted * 100) if self.total_attempted > 0 else 0

        # Create a beautiful Rich Table
        table = Table(title=f"📊 Intelligence Report: {creator_name}", title_style="bold magenta")

        table.add_column("Category", style="cyan")
        table.add_column("Metric", justify="right", style="green")
        table.add_column("Details", style="dim")

        table.add_row("Total Time", str(timedelta(seconds=int(total_duration))), "Wall clock duration")
        table.add_row("Success Rate", f"{success_rate:.1f}%", f"{self.success_count}/{self.total_attempted} processed")
        table.add_row("Cache Hits", str(self.cache_hits), "Videos skipped (Credits saved)")
        table.add_row("API 429 Errors", str(self.error_429_count), "Rate limit strikes encountered")
        table.add_row("API 404 Errors", str(self.error_404_count), "Missing transcript signals")
        table.add_row("Local AI (Whisper)", str(self.whisper_transcriptions), f"Total Whisper time: {self.whisper_total_time:.1f}s")
        table.add_row("Cloud AI (Supadata)", str(self.api_transcriptions), "Successful API retrievals")

        console.print("\n")
        console.print(Panel(table, expand=False, border_style="magenta"))