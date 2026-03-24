import sqlite3
import os
import numpy as np
import hdbscan
from sklearn.cluster import KMeans
from storage.db import Database

class TranscriptClusterer:
    def __init__(self, db_path="storage/digestr.db", embeddings_dir="analysis/embeddings"):
        self.db = Database(db_path)
        self.embeddings_dir = embeddings_dir

    def get_profile_id(self, username: str):
        """Helper to get the profile ID for database relations."""
        username = username.replace("@", "")
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT id FROM profiles WHERE username = ?", (username,)).fetchone()
            return row['id'] if row else None

    def cluster_creator(self, username: str):
        username_clean = username.replace("@", "")
        print(f"--- Running Clustering for: @{username_clean} ---")
        
        # 1. Load the mathematical brain map we made in Step 2
        npz_path = os.path.join(self.embeddings_dir, f"{username_clean}.npz")
        if not os.path.exists(npz_path):
            print(f"❌ Error: Embeddings file not found at {npz_path}. Run embedder first.")
            return

        data = np.load(npz_path)
        content_ids = data['content_ids']
        embeddings = data['embeddings']
        
        print(f"Loaded {len(embeddings)} vectors. Grouping them now...")

        # 2. Run HDBSCAN (Finds natural groups based on density)
        # min_cluster_size=5 means a topic must have at least 2 videos to be considered a real topic
        clusterer = hdbscan.HDBSCAN(min_cluster_size=2, min_samples=2, metric='euclidean')
        labels = clusterer.fit_predict(embeddings)
        
        # Check how many unique topics we found (ignoring -1 which is noise/miscellaneous)
        unique_labels = set(labels)
        num_clusters = len(unique_labels) - (1 if -1 in labels else 0)
        
        # Fallback to K-Means if HDBSCAN was too strict and found no clusters
        if num_clusters == 0:
            print("⚠️ HDBSCAN found 0 distinct topics. Falling back to K-Means (forcing 5 clusters)...")
            num_clusters = 5
            kmeans = KMeans(n_clusters=num_clusters, random_state=42, n_init="auto")
            labels = kmeans.fit_predict(embeddings)
            unique_labels = set(labels)

        print(f"✅ Discovered {num_clusters} distinct topics (plus miscellaneous noise).")

        # 3. Save the results back into the SQLite Database
        profile_id = self.get_profile_id(username)
        if not profile_id:
            print("❌ Error: Profile not found in database.")
            return

        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Clear old clusters for this creator if we are re-running
            cursor.execute("UPDATE processed_transcripts SET cluster_id = NULL WHERE content_id IN (SELECT id FROM content WHERE profile_id = ?)", (profile_id,))
            cursor.execute("DELETE FROM clusters WHERE profile_id = ?", (profile_id,))
            
            # Iterate through the discovered groups
            for label in unique_labels:
                # -1 is the label HDBSCAN gives to outlier videos
                topic_name = "Miscellaneous (Noise)" if label == -1 else f"Topic Group {label + 1}"
                
                # Find all video IDs that belong to this group
                indices = np.where(labels == label)[0]
                cluster_content_ids = content_ids[indices]
                video_count = len(cluster_content_ids)
                
                # Insert the new topic into the clusters table
                cursor.execute(
                    "INSERT INTO clusters (profile_id, topic_name, video_count) VALUES (?, ?, ?)",
                    (profile_id, topic_name, video_count)
                )
                cluster_id = cursor.lastrowid # Get the newly created cluster's DB ID
                
                # Update all those specific videos to point to this new topic
                # SQLite doesn't support massive array updates easily, so we loop (it's fast enough locally)
                for cid in cluster_content_ids:
                    cursor.execute("UPDATE processed_transcripts SET cluster_id = ? WHERE content_id = ?", (cluster_id, int(cid)))
            
            conn.commit()
            print("✅ Successfully saved all topics and updated video relationships in the database.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Cluster a creator's embeddings into topics.")
    parser.add_argument("username", help="The creator's username (e.g., @jakexplains)")
    args = parser.parse_args()

    clusterer = TranscriptClusterer()
    clusterer.cluster_creator(args.username)