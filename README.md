# 🧵 Digestr: AI-Powered Semantic Content Synthesis

**Digestr** is an end-to-end data engineering pipeline and web application designed to transform high-entropy social media content into structured, long-form educational assets. By leveraging local machine learning and Large Language Models (LLMs), Digestr bypasses chronological noise to discover the underlying "Knowledge Map" of any content creator.

---

## 🚀 The Problem
Social media platforms (TikTok, Instagram) are "stream-based." Valuable educational content is often fragmented across hundreds of short-form videos, making it nearly impossible for users to study a specific topic holistically without manual curation.

## 💡 The Solution
Digestr automates the entire curation lifecycle:
1.  **Mining:** Extracts raw transcripts and metadata from creator profiles.
2.  **Processing:** Cleans and dual-tokenizes text for both human readability and mathematical vectorization.
3.  **Discovery:** Uses unsupervised machine learning (**HDBSCAN**) to find natural topic clusters without human labeling.
4.  **Synthesis:** Employs **Llama-3.3-70B** via Groq to weave fragmented transcripts into cohesive, professional articles.

---

## 🛠️ Technical Architecture



### 1. Data Pipeline & Storage
* **Engine:** Custom Python-based orchestrator managing asynchronous data flows.
* **Storage:** **SQLite** with a relational schema optimized for content-creator-topic mapping.
* **Mining:** Native caption extraction with an AI-fallback audio-to-text engine.

### 2. Machine Learning & NLP
* **Vectorization:** Local execution of `SentenceTransformers` (`all-MiniLM-L6-v2`) to map transcripts into a 384-dimensional hyperspace.
* **Clustering:** Implementation of **HDBSCAN** (Hierarchical Density-Based Spatial Clustering of Applications with Noise) to identify dense topical clusters while filtering "noise" content.
* **NLP Cleaning:** Custom regex-based and NLTK-driven cleaning to remove social media artifacts (timestamps, filler words) before processing.

### 3. Generative AI (LLM) Integration
* **Semantic Naming:** Uses **Groq (Llama-3.3-70B)** to analyze cluster centroids and generate professional, context-aware titles.
* **Content Weaving:** A sophisticated prompting architecture that handles de-duplication, logical sequencing, and "voice preservation" to turn multiple transcripts into a single Markdown masterpiece.

### 4. Frontend (UX/UI)
* **Framework:** **Streamlit**.
* **Design Philosophy:** "Dark & Sleek" aesthetic inspired by Spotify and Discord, featuring a "Google-snap" search interaction and a reactive, session-state-managed toolbar.

---

## 📂 Project Structure
```text
Digestr/
├── analysis/
│   ├── cleaner.py       # Dual-stream text normalization
│   ├── embedder.py      # Local vector generation (SentenceTransformers)
│   ├── clusterer.py     # HDBSCAN clustering logic
│   └── topic_namer.py   # LLM-based semantic labeling
├── weaver/
│   └── groq_weaver.py   # Synthesis engine for long-form content
├── storage/
│   ├── db.py            # SQLite abstraction layer
│   └── digestr.db       # Relational database
├── datasets/            # Raw CSV exports
├── .streamlit/
│   └── config.toml      # Custom Dark/Sleek theme configuration
└── app.py               # Streamlit UI & Pipeline Orchestrator
```

---

## ⚡ Key Engineering Achievements
* **Reduced API Costs:** By performing Clustering and Embedding locally, the system reduces LLM token usage by **~90%**, only using the API for high-value synthesis.
* **Semantic Accuracy:** Successfully grouped complex topics (e.g., "Neuroscience of Empathy" vs "Emotional Trauma") using mathematical density rather than simple keyword matching.
* **Optimized UX:** Built a non-blocking UI that manages complex AI states and prevents redundant processing through smart caching and session management.

---