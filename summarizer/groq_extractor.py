import os
import re
import yaml
from groq import Groq
from models import Transcript, SummaryMeta

class SummarizerError(Exception):
    pass

class GroqExtractor:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is missing from .env file.")
        
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.3-70b-versatile"

        # The aggressive extraction prompt we built earlier
        self.system_instruction = """You are a Technical Intelligence Officer. Your job is to extract HARD DATA from social media transcripts. 
BANNED WORDS: "importance", "success", "journey", "emphasizes", "highlights", "motivational", "encourages". If you use these, you fail.

You MUST respond in this exact format:

---
topics: ["Topic 1"]
target_audience: "Who is this for?"
tools_mentioned: ["Tool 1", "Tool 2"]
key_claims:
  - "Claim 1: Specific resource name + what it provides"
action_item: "The exact next step"
sentiment: "positive"
---

## The Raw Signal
[Write 2-3 blunt, factual sentences. Name the specific platforms and tools. Do not use fluff.]

## Hard Assets
- **The Platform:** Name and specific features.
- **The Deliverable:** What exactly is the creator giving away or showing?
- **The Context:** What career or goal is this for?

## Full Transcript
{transcript_text}"""

    # --- NEW: THE AI CLEANER PASS ---
    def clean_transcript(self, raw_text: str, language: str) -> str:
            editor_prompt = f"""You are a Senior Technical Editor and expert {language}/English linguist. Your job is to transform a messy, conversational voice-to-text transcript into a highly structured, authoritative, and compressed technical brief.

    CRITICAL RULES:
    1. Structuring: Group the ideas into logical, hierarchical sections (e.g., Foundations, Core Fields, Advanced Skills, Tools & Systems) using Markdown bullet points. DO NOT output a single wall of text.
    2. Deduplication: Completely remove all repetitive conversational filler (e.g., "The second job started", "Another thing is", "She said"). Merge repeated concepts.
    3. Compression: Distill the core technical value. Limit your response to 120-150 words maximum. Be brutally concise.
    4. Authority Rewrite: Rewrite the text to sound like it was written by an expert Senior Engineer. Fix unnatural phrasing, "half-human" literal translations, and weak verbs. 
    5. Code-Switching: Translate phonetic English tech words spoken in {language} (like "ديتا ساتس" or "كاقي") back to proper English ("datasets", "Kaggle").

    Output ONLY the structured, cleaned notes. No introductions, no pleasantries."""

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": editor_prompt},
                        {"role": "user", "content": f"Distill and structure this raw transcript:\n\n{raw_text}"}
                    ],
                    temperature=0.2, # Slightly higher than 0.1 to allow for the "Authority Rewrite"
                    max_tokens=1024
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                raise SummarizerError(f"Groq cleaning failed: {e}")

    def summarize(self, transcript: Transcript, cleaned_text: str) -> SummaryMeta:
        # Notice we inject 'cleaned_text' into the prompt, not the raw text
        prompt = self.system_instruction.replace("{transcript_text}", cleaned_text)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1024
            )
            
            raw_output = response.choices[0].message.content
            
            # --- YAML Parsing Logic (Kept exactly the same) ---
            yaml_match = re.search(r'---\n(.*?)\n---', raw_output, re.DOTALL)
            if not yaml_match:
                raise SummarizerError("Could not find YAML frontmatter in Groq response.")
            
            yaml_content = yaml_match.group(1)
            parsed_data = yaml.safe_load(yaml_content) or {}
            body_content = raw_output[yaml_match.end():].strip()

            final_frontmatter = {
                "source": transcript.video_meta.creator_username,
                "platform": transcript.video_meta.platform,
                "url": transcript.video_meta.url,
                "date": transcript.video_meta.posted_at.strftime("%Y-%m-%d"),
                "language": transcript.video_meta.language,
                "transcript_source": transcript.source,
                "topics": parsed_data.get("topics", []),
                "target_audience": parsed_data.get("target_audience", "General"),
                "tools_mentioned": parsed_data.get("tools_mentioned", []),
                "key_claims": parsed_data.get("key_claims", []),
                "action_item": parsed_data.get("action_item", ""),
                "sentiment": parsed_data.get("sentiment", "neutral")
            }

            final_markdown = "---\n" + yaml.dump(
                final_frontmatter, sort_keys=False, allow_unicode=True, default_style='"'
            ) + "---\n\n" + body_content

            filename = f"{transcript.video_meta.posted_at.strftime('%Y-%m-%d')}_{transcript.video_meta.platform_id}.md"
            file_path = os.path.join("output", f"@{transcript.video_meta.creator_username}", filename)

            return SummaryMeta(file_path=file_path, markdown=final_markdown)

        except Exception as e:
            raise SummarizerError(f"Summarization failed: {e}")

extractor = GroqExtractor()