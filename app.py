import streamlit as st
import time
import os
from storage.db import Database
from analysis.cleaner import TranscriptCleaner
from analysis.embedder import TranscriptEmbedder
from analysis.clusterer import TranscriptClusterer
from analysis.topic_namer import TopicNamer
from weaver.groq_weaver import ContentWeaver

# --- Page Configuration ---
st.set_page_config(page_title="Digestr", page_icon="🧵", layout="wide")

# --- Initialize Memory (Session State) ---
if "data_ready" not in st.session_state:
    st.session_state.data_ready = False
if "current_user" not in st.session_state:
    st.session_state.current_user = ""
if "woven_articles" not in st.session_state:
    st.session_state.woven_articles = {} 

# --- Custom CSS for the "Discord/Spotify" Vibe ---
st.markdown("""
    <style>
    /* Hides the radio button circles */
    div[role="radiogroup"] > label > div:first-of-type {
        display: none;
    }
    /* Styles the toolbar tabs */
    div[role="radiogroup"] > label {
        background-color: #1E1E1E; /* Matches secondary background */
        padding: 10px 20px;
        border-radius: 8px;
        border: 1px solid #2A2A2A;
        margin-right: 10px;
        transition: all 0.2s ease-in-out;
    }
    /* The Neon Hover Effect */
    div[role="radiogroup"] > label:hover {
        border-color: #00E5FF; /* Electric Blue border */
        box-shadow: 0 0 12px rgba(0, 229, 255, 0.2); /* Subtle neon glow */
        cursor: pointer;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# STATE 1: THE HERO SCREEN (CENTERED)
# ==========================================
if not st.session_state.data_ready:
    # Push content down to the center
    for _ in range(10): st.write("")
    
    st.markdown("<h1 style='text-align: center; font-size: 5rem; font-weight: 800;'>🧵 Digestr</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; font-size: 1.2rem; color: #888888; margin-bottom: 2rem;'>Transform raw TikTok chaos into structured knowledge.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Creator Username", placeholder="e.g. @jakexplains", label_visibility="collapsed")
        
        b_col1, b_col2, b_col3 = st.columns([1, 1, 1])
        with b_col2:
            process_btn = st.button("Generate Digest", use_container_width=True, type="primary")

    if process_btn and username:
        st.session_state.current_user = username
        clean_username = username.replace("@", "")
        csv_path = f"datasets/dataset_{clean_username}.csv"
        
        if not os.path.exists(csv_path):
            st.error(f"Dataset not found: {csv_path}. Run the data miner first.")
        else:
            with st.status("🚀 Initializing AI Data Pipeline...", expanded=True) as status:
                st.write("🧹 Cleaning and formatting transcripts...")
                TranscriptCleaner().process_creator(username, csv_path)
                
                st.write("🧠 Generating semantic embeddings...")
                TranscriptEmbedder().generate_embeddings(username)
                
                st.write("🗂️ Clustering content into natural topics...")
                TranscriptClusterer().cluster_creator(username)
                
                st.write("🏷️ Extracting professional titles with Groq...")
                TopicNamer().name_topics(username)
                
                status.update(label="✅ Analysis Complete!", state="complete", expanded=False)
            
            st.session_state.woven_articles = {} 
            st.session_state.data_ready = True
            st.rerun()

# ==========================================
# STATE 2: THE RESULTS SCREEN (SNAPPED)
# ==========================================
if st.session_state.data_ready:
    # --- Top Nav Bar ---
    nav_col1, nav_col2, nav_col3 = st.columns([2, 3, 1])
    with nav_col1:
        # Changed the accent color here to Electric Blue (#00E5FF)
        st.markdown(f"### 🧵 Digestr : <span style='color:#00E5FF;'>{st.session_state.current_user}</span>", unsafe_allow_html=True)
    with nav_col3:
        if st.button("Start Over", use_container_width=True):
            st.session_state.data_ready = False
            st.session_state.current_user = ""
            st.session_state.woven_articles = {}
            st.rerun()
            
    st.divider()

    # --- Fetch Topics ---
    clean_username = st.session_state.current_user.replace("@", "")
    db = Database()
    with db._get_connection() as conn:
        profile = conn.execute("SELECT id FROM profiles WHERE username = ?", (clean_username,)).fetchone()
        if not profile:
            st.error("Profile data lost. Please restart.")
            st.stop()
            
        clusters = conn.execute(
            "SELECT id, topic_name, video_count FROM clusters WHERE profile_id = ? AND topic_name != 'Miscellaneous (Noise)'", 
            (profile['id'],)
        ).fetchall()

    if not clusters:
        st.info("The AI couldn't find distinct topics for this creator.")
    else:
        # --- THE TOOLBAR ---
        st.markdown("##### 📚 Discover Topics")
        
        toolbar_options = [f"{c['topic_name']} ({c['video_count']})" for c in clusters]
        selected_tab = st.radio("Select a topic to discover:", toolbar_options, horizontal=True, label_visibility="collapsed")
        
        st.write("\n") 

        # --- AUTO-WEAVE LOGIC ---
        if selected_tab:
            selected_cluster = next(c for c in clusters if f"{c['topic_name']} ({c['video_count']})" == selected_tab)
            cluster_id = selected_cluster['id']
            
            if cluster_id not in st.session_state.woven_articles:
                with st.spinner(f"✨ Analyzing and Weaving '{selected_cluster['topic_name']}'..."):
                    weaver = ContentWeaver()
                    article_text = weaver.weave_topic(cluster_id)
                    st.session_state.woven_articles[cluster_id] = article_text
            
            article_content = st.session_state.woven_articles.get(cluster_id)
            
            if article_content:
                with st.container(border=True):
                    st.markdown(article_content)
                    
                    st.divider()
                    st.download_button(
                        label="⬇️ Download Markdown",
                        data=article_content,
                        file_name=f"{selected_cluster['topic_name'].replace(' ', '_')}.md",
                        mime="text/markdown"
                    )