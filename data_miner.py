import os
import csv
import glob
from collections import defaultdict
from rich.console import Console

console = Console()

def mine_data():
    output_dir = "output"
    
    console.print(f"[cyan][*][/cyan] Scanning '{output_dir}' for transcripts...")
    
    # Search for all .txt files recursively
    search_pattern = os.path.join(output_dir, "**", "*.txt")
    txt_files = glob.glob(search_pattern, recursive=True)
    
    if not txt_files:
        console.print("[yellow][!] No text files found in the output directory.[/yellow]")
        return

    # Dictionary to group files by creator
    creator_files = defaultdict(list)

    # Group files by creator
    for file_path in txt_files:
        normalized_path = file_path.replace("\\", "/")
        parts = normalized_path.split("/")
        creator_name = next((part for part in parts if part.startswith("@")), "Unknown")
        creator_files[creator_name].append((file_path, parts[-1]))

    console.print(f"[cyan][*][/cyan] Found {len(txt_files)} files across {len(creator_files)} creators.")
    
    # Create a separate CSV for each creator
    os.makedirs("datasets", exist_ok=True) # فولدر جديد هيتجمع فيه الشيتات

    with console.status("[cyan]Building individual CSV datasets...[/cyan]"):
        for creator, files in creator_files.items():
            # Clean creator name for the filename
            safe_creator_name = creator.replace("@", "")
            csv_filename = f"datasets/dataset_{safe_creator_name}.csv"
            
            with open(csv_filename, mode='w', newline='', encoding='utf-8') as csv_file:
                fieldnames = ['Creator', 'Date', 'Video_ID', 'Transcript_Type', 'Content']
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                
                for file_path, filename in files:
                    file_parts = filename.replace(".txt", "").split("_")
                    
                    if len(file_parts) >= 3:
                        date_str = file_parts[0]
                        video_id = file_parts[1]
                        transcript_type = "_".join(file_parts[2:]) 
                    else:
                        date_str, video_id, transcript_type = "Unknown", "Unknown", "Unknown"
                        
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        
                    writer.writerow({
                        'Creator': creator,
                        'Date': date_str,
                        'Video_ID': video_id,
                        'Transcript_Type': transcript_type,
                        'Content': content
                    })
            
            console.print(f"[bold green]✅ Created:[/bold green] {csv_filename} ({len(files)} videos)")

    console.print(f"\n[bold magenta]🏁 Data Mining Complete![/bold magenta] Check the 'datasets' folder.")

if __name__ == "__main__":
    try:
        mine_data()
    except KeyboardInterrupt:
        console.print("\n[yellow][!] Stopped by user.[/yellow]")