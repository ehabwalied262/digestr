import sqlite3
import time
import os
from groq import Groq
from storage.db import Database
from dotenv import load_dotenv  # <--- Make sure this is here

# This line tells Python: "Find the .env file and load it into my environment"
load_dotenv()

class TopicNamer:
    def __init__(self, db_path="storage/digestr.db"):
        self.db = Database(db_path)
        # Make sure to set your GROQ_API_KEY in your environment variables
        api_key = os.environ.get("GROQ_API_KEY") 
        if not api_key:
            raise ValueError("❌ Please set GROQ_API_KEY in your environment variables.")
        self.client = Groq(api_key=api_key)

    def get_profile_id(self, username: str):
        username = username.replace("@", "")
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT id FROM profiles WHERE username = ?", (username,)).fetchone()
            return row['id'] if row else None

    def get_smart_title(self, sample_text: str):
        """Sends a sample of transcripts to Groq to generate a professional title."""
        try:
            prompt = f"""
            You are a professional content curator. I will provide you with a sample of transcripts from a group of videos by the same creator.
            Your task is to create a concise, catchy, and professional 3-4 word title that represents the core topic of these videos.
            
            Rules:
            1. Respond ONLY with the title.
            2. Do not use punctuation like quotes or periods.
            3. Make it professional (e.g., 'Space Exploration Wonders' instead of 'videos about stars').
            
            Transcripts Sample:
            {sample_text[:3000]} # Send first 3000 chars to stay safe with limits
            """
            
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile", # High quality model
                temperature=0.5,
            )
            return chat_completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"      ⚠️ Groq Error: {e}")
            return None

    def name_topics(self, username: str):
        username_clean = username.replace("@", "")
        print(f"--- Smart Topic Naming for: @{username_clean} ---")
        start_time = time.time()

        profile_id = self.get_profile_id(username)
        if not profile_id:
            print("❌ Error: Profile not found in database.")
            return

        with self.db._get_connection() as conn:
            clusters = conn.execute(
                "SELECT id, topic_name FROM clusters WHERE profile_id = ? AND topic_name != 'Miscellaneous (Noise)'",
                (profile_id,)
            ).fetchall()

            if not clusters:
                print("⚠️ No valid clusters found. Run the clusterer first.")
                return

            print(f"Consulting Groq for {len(clusters)} topics...")
            updated_count = 0

            for cluster in clusters:
                cluster_id = cluster['id']
                
                # Fetch a sample of transcripts for this cluster
                # We fetch several to give Groq context, but not all to save tokens
                rows = conn.execute(
                    "SELECT text_for_llm FROM processed_transcripts WHERE cluster_id = ? LIMIT 5",
                    (cluster_id,)
                ).fetchall()
                
                combined_sample = "\n---\n".join([r['text_for_llm'] for r in rows])
                
                if not combined_sample.strip():
                    continue

                # Get the professional title from Groq
                smart_title = self.get_smart_title(combined_sample)
                
                if smart_title:
                    conn.execute("UPDATE clusters SET topic_name = ? WHERE id = ?", (smart_title, cluster_id))
                    updated_count += 1
                    print(f"  ✨ Topic {cluster_id} is now: [{smart_title}]")
                    # Sleep briefly to avoid hitting Rate Limits if you have many topics
                    time.sleep(0.5) 
            
            conn.commit()

        elapsed = time.time() - start_time
        print(f"✅ Successfully renamed {updated_count} topics using Groq in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate professional topic names using Groq.")
    parser.add_argument("username", help="The creator's username (e.g., @jakexplains)")
    args = parser.parse_args()
    
    namer = TopicNamer()
    namer.name_topics(args.username)