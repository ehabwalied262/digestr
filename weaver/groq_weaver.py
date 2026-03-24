import os
import time
import sqlite3
from groq import Groq
from storage.db import Database
from dotenv import load_dotenv

load_dotenv()

class ContentWeaver:
    def __init__(self, db_path="storage/digestr.db"):
        self.db = Database(db_path)
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("❌ GROQ_API_KEY not found in environment.")
        self.client = Groq(api_key=api_key)

    def get_cluster_data(self, cluster_id):
        """Fetches the topic name and all associated transcripts for a cluster."""
        with self.db._get_connection() as conn:
            topic = conn.execute("SELECT topic_name FROM clusters WHERE id = ?", (cluster_id,)).fetchone()
            transcripts = conn.execute(
                "SELECT text_for_llm FROM processed_transcripts WHERE cluster_id = ?", 
                (cluster_id,)
            ).fetchall()
            
            return topic['topic_name'] if topic else "Unknown Topic", [t['text_for_llm'] for t in transcripts]

    def weave_topic(self, cluster_id):
        topic_name, transcripts = self.get_cluster_data(cluster_id)
        
        if not transcripts:
            print(f"⚠️ No transcripts found for Cluster {cluster_id}")
            return None

        print(f"🧵 Weaving {len(transcripts)} videos about '{topic_name}'...")
        
        # Combine transcripts with a separator
        full_context = "\n\n---\n\n".join(transcripts)
        
        # Token Management: If text is massive (>25k chars), we take the first 25k 
        # (Llama 3.3 70b handles 128k, but 25k is safer for speed and quality)
        context_window = full_context[:25000] 

        prompt = f"""
        You are a world-class scriptwriter and editor. I have a collection of video transcripts 
        on the topic: "{topic_name}".
        
        YOUR GOAL:
        Create a single, seamless, long-form narrative that combines all the unique insights 
        from these videos.
        
        CONSTRAINTS:
        1. STRUCTURE: Use clear, engaging subheadings.
        2. TONE: Maintain the creator's natural speaking style (keep the "voice" and "fillers" 
           where they add personality, but remove "um/uh").
        3. NO REPETITION: If the creator says the same fact in three videos, only include it once 
           in the most impactful way.
        4. SEQUENTIAL: Arrange the ideas so they flow logically from one to the next.
        5. FORMAT: Use clean Markdown.
        
        TRANSCRIPTS DATA:
        {context_window}
        """

        try:
            start_time = time.time()
            completion = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "system", "content": "You are a master content weaver."},
                          {"role": "user", "content": prompt}],
                temperature=0.6, # Balance between creative and factual
            )
            
            result = completion.choices[0].message.content
            duration = time.time() - start_time
            print(f"✅ Weaving complete in {duration:.2f} seconds.")
            return result
        except Exception as e:
            print(f"❌ Error during weaving: {e}")
            return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Weave all videos of a cluster into one long-form text.")
    parser.add_argument("cluster_id", type=int, help="ID of the cluster to weave")
    args = parser.parse_args()

    weaver = ContentWeaver()
    final_output = weaver.weave_topic(args.cluster_id)
    
    if final_output:
        # Save to a temporary file just to see the result
        os.makedirs("output", exist_ok=True)
        filename = f"output/cluster_{args.cluster_id}.md"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(final_output)
        print(f"🚀 Masterpiece saved to: {filename}")