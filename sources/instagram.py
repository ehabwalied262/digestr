import os
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright
from sources.base import Source
from models import VideoMeta, ProfileStats

# IMPORT YOUR NEW HUMAN BEHAVIOR SCRIPT
from sources.human_behavior import simulate_human_reading, human_scroll, random_sleep

class InstagramSource(Source):
    def __init__(self):
        self.session_id = os.getenv("IG_SESSION_ID")
        if not self.session_id:
            raise ValueError("IG_SESSION_ID not set in .env")

    def _get_browser_context(self, p):
        # We can keep headless=True, but setting it to False lets you watch the "ghost" human work
        browser = p.chromium.launch(headless=False) 
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        
        context.add_cookies([{
            "name": "sessionid",
            "value": self.session_id,
            "domain": ".instagram.com",
            "path": "/"
        }])
        return browser, context

    def get_profile_stats(self, username: str) -> ProfileStats:
        with sync_playwright() as p:
            browser, context = self._get_browser_context(p)
            page = context.new_page()
            
            clean_username = username.replace("@", "")
            page.goto(f"https://www.instagram.com/{clean_username}/", wait_until="domcontentloaded")
            
            # --- HUMAN BEHAVIOR INJECTION ---
            simulate_human_reading(page)
            
            meta_desc = page.locator('meta[name="description"]').get_attribute("content") or ""
            followers, posts = 0, 0
            
            if meta_desc:
                f_match = re.search(r'([\d\.,MK]+)\s+Followers', meta_desc, re.IGNORECASE)
                p_match = re.search(r'([\d\.,MK]+)\s+Posts', meta_desc, re.IGNORECASE)
                
                def parse_number(num_str):
                    if not num_str: return 0
                    num_str = num_str.replace(',', '').upper()
                    if 'M' in num_str: return int(float(num_str.replace('M', '')) * 1000000)
                    if 'K' in num_str: return int(float(num_str.replace('K', '')) * 1000)
                    return int(num_str)

                followers = parse_number(f_match.group(1)) if f_match else 0
                posts = parse_number(p_match.group(1)) if p_match else 0

            browser.close()
            return ProfileStats(
                username=clean_username, platform="instagram",
                total_posts=posts, follower_count=followers,
                bio="", scanned_at=datetime.utcnow()
            )

    def get_recent_posts(self, username: str, limit: int) -> list[VideoMeta]:
        with sync_playwright() as p:
            browser, context = self._get_browser_context(p)
            page = context.new_page()
            clean_username = username.replace("@", "")
            
            print(f"[*] Navigating to {clean_username}'s reels...")
            
            # 1. Change networkidle to domcontentloaded
            page.goto(f"https://www.instagram.com/{clean_username}/reels/", wait_until="domcontentloaded")
            
            # 1. Wait for EITHER a reel or a standard post
            try:
                page.wait_for_selector("a[href*='/reel/'], a[href*='/p/']", timeout=15000)
            except Exception:
                print(f"[!] Warning: Posts took too long to load.")
            
            simulate_human_reading(page)
            
            extracted_shortcodes = set()
            posts = []
            scroll_attempts = 0
            
            while len(posts) < limit and scroll_attempts < 5:
                # 2. Grab ALL post and reel links
                post_links = page.locator("a[href*='/reel/'], a[href*='/p/']").all()
                for link in post_links:
                    href = link.get_attribute("href")
                    if not href: continue
                    
                    # 3. Extract the shortcode whether it's a /p/ or a /reel/
                    match = re.search(r'/(?:reel|p)/([^/?]+)', href)
                    if match:
                        shortcode = match.group(1)
                        if shortcode not in extracted_shortcodes:
                            extracted_shortcodes.add(shortcode)
                            posts.append(VideoMeta(
                                platform="instagram", platform_id=shortcode,
                                url=f"https://www.instagram.com{href}",
                                creator_username=clean_username, posted_at=datetime.utcnow(),
                                content_type="reel" if "/reel/" in href else "photo/carousel", 
                                language="en", duration_seconds=0, caption_text=""
                            ))
                            if len(posts) >= limit: break
                
                print(f"[*] Scrolled... found {len(posts)} unique reels so far.")
                
                # --- HUMAN BEHAVIOR INJECTION ---
                human_scroll(page)
                random_sleep(2.0, 4.0) 
                
                scroll_attempts += 1

            browser.close()
            return posts

    def get_posts_since(self, username: str, since: datetime) -> list[VideoMeta]:
        return self.get_recent_posts(username, limit=30)

    def get_single_post(self, url: str) -> VideoMeta:
        match = re.search(r'/(?:p|reel|reels)/([^/?#&]+)', url)
        return VideoMeta(
            platform="instagram", platform_id=match.group(1) if match else "unknown",
            url=url, creator_username="unknown", posted_at=datetime.utcnow(),
            content_type="reel", language="en"
        )