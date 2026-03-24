import sys
import os
import time
# Add the project root to Python's path so it can find db.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import sqlite3
import re
import nltk
from nltk.corpus import stopwords
from storage.db import Database

# Download required NLTK resources
nltk.download('stopwords', quiet=True)
stop_words = set(stopwords.words('english'))

# Words that convey tone but add noise to mathematical clustering
social_media_fillers = {
    'like', 'you know', 'basically', 'kind of', 'literally', 
    'um', 'uh', 'so', 'just', 'well', 'actually', 'anyway'
}

class TranscriptCleaner:
    def __init__(self, db_path="storage/digestr.db"):
        self.db = Database(db_path)

    def clean_for_llm(self, text):
        """Removes technical noise but keeps natural speech patterns and fillers."""
        if not text: return ""
        # Remove timestamps if any (e.g., 00:01)
        text = re.sub(r'\d{1,2}:\d{2}', '', text)
        # Remove bracketed artifacts like [Music] or [Laughter]
        text = re.sub(r'\[.*?\]', '', text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def clean_for_math(self, text):
        """Aggressive cleaning for vectorization: removes stopwords and fillers."""
        text = text.lower()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        
        words = text.split()
        # Remove both standard English stopwords and social media filler words
        filtered_words = [
            w for w in words 
            if w not in stop_words and w not in social_media_fillers
        ]
        return ' '.join(filtered_words)

    def process_creator(self, username: str, csv_path: str):
        """Reads a creator's CSV and populates the processed_transcripts table."""
        print(f"--- Processing Creator: {username} ---")
        start_time = time.time() # Start the stopwatch
        
        df = pd.read_csv(csv_path)
        df = df.dropna(subset=['Content'])
        
        processed_count = 0
        for _, row in df.iterrows():
            platform_id = str(row['Video_ID'])
            content_id = self.db.get_content_id_by_platform_id(platform_id)
            
            if content_id:
                raw_text = row['Content']
                
                # Version 1: Preserves the 'Voice' for Groq
                llm_text = self.clean_for_llm(raw_text)
                
                # Version 2: Optimized for Mathematical Clustering
                math_text = self.clean_for_math(llm_text)
                
                # Minimum length check for quality
                if len(math_text.split()) > 5:
                    self.db.save_processed_transcript(content_id, llm_text, math_text)
                    processed_count += 1
                    
        end_time = time.time() # Stop the stopwatch
        elapsed = end_time - start_time
        
        # Format the output beautifully
        if elapsed > 60:
            minutes = int(elapsed // 60)
            seconds = elapsed % 60
            time_str = f"{minutes} minutes and {seconds:.2f} seconds"
        else:
            time_str = f"{elapsed:.2f} seconds"
            
        print(f"✅ Successfully processed and stored {processed_count} transcripts in {time_str}.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Clean and process transcripts for a creator.")
    parser.add_argument("username", help="The creator's username (e.g., @jakexplains)")
    parser.add_argument("csv_path", help="Path to the CSV dataset (e.g., dataset_jakexplains.csv)")
    args = parser.parse_args()

    cleaner = TranscriptCleaner()
    cleaner.process_creator(args.username, args.csv_path)