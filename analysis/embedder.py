import sys
import os
# Add the project root to Python's path so it can find db.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import numpy as np
from sentence_transformers import SentenceTransformer

class TranscriptEmbedder:
    def __init__(self, db_path="storage/digestr.db", output_dir="analysis/embeddings"):
        self.db_path = db_path
        self.output_dir = output_dir
        
        # Ensure the output directory exists
        os.makedirs(self.output_dir, exist_ok=True)
        
        print("Loading SentenceTransformer model (this might take a minute the first time)...")
        # all-MiniLM-L6-v2 is the perfect balance of speed and semantic accuracy
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ Model loaded successfully.")

    def generate_embeddings(self, username: str):
        """Fetches mathematical text from the DB and generates vector embeddings."""
        username = username.replace("@", "")
        print(f"--- Generating Embeddings for: @{username} ---")
        
        # Connect to DB and fetch transcripts
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = """
            SELECT pt.content_id, pt.text_for_math 
            FROM processed_transcripts pt
            JOIN content c ON pt.content_id = c.id
            JOIN profiles p ON c.profile_id = p.id
            WHERE p.username = ? AND pt.text_for_math IS NOT NULL AND pt.text_for_math != ''
        """
        
        rows = cursor.execute(query, (username,)).fetchall()
        conn.close()
        
        if not rows:
            print(f"⚠️ No processed transcripts found for @{username}. Did you run the cleaner?")
            return
        
        # Separate IDs and Texts to maintain a 1:1 mapped index
        content_ids = np.array([row['content_id'] for row in rows])
        texts = [row['text_for_math'] for row in rows]
        
        print(f"Found {len(texts)} transcripts. Encoding into vectors...")
        
        # Generate embeddings (This runs entirely locally on your CPU/GPU)
        embeddings = self.model.encode(texts, show_progress_bar=True)
        
        # Save both IDs and Embeddings together in a compressed format
        output_file = os.path.join(self.output_dir, f"{username}.npz")
        np.savez(output_file, content_ids=content_ids, embeddings=embeddings)
        
        print(f"✅ Successfully saved embeddings to {output_file}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate vector embeddings for a creator's transcripts.")
    parser.add_argument("username", help="The creator's username (e.g., @jakexplains)")
    args = parser.parse_args()

    embedder = TranscriptEmbedder()
    embedder.generate_embeddings(args.username)