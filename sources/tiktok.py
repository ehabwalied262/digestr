# sources/tiktok.py
import os
import yt_dlp
from datetime import datetime
from models import ProfileStats, VideoMeta

class TikTokSource:
    def __init__(self):
        # We tell yt-dlp to look for the cookies file in the root Digestr folder
        self.cookie_file = "www.tiktok.com_cookies.txt"
        
        # Base options for yt-dlp to extract metadata silently without downloading the video
        self.ydl_opts = {
            'cookiefile': self.cookie_file,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True, # Only get metadata, don't download media
            'dump_single_json': True,
        }

    def get_profile_stats(self, username: str) -> ProfileStats:
        """Fetches basic profile info. TikTok makes total post count hard to get, 
        so we focus on followers and likes if available, or just verify the account exists."""
        
        # Ensure the username starts with @ for the URL
        if not username.startswith('@'):
            username = f"@{username}"
            
        url = f"https://www.tiktok.com/{username}"
        
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                # We use extract_info to grab the channel metadata
                info = ydl.extract_info(url, download=False)
                
                # yt-dlp returns a list of entries for a channel
                total_videos = len(info.get('entries', [])) 
                
                return ProfileStats(
                        username=username.replace("@", ""),
                        total_posts=total_videos,
                        platform="tiktok",
                        follower_count=info.get('follower_count', 0), # Grabs count if available, otherwise 0
                        bio=info.get('description', '') or "",        # Grabs bio if available, otherwise empty
                        scanned_at=datetime.now()
                        )
        except Exception as e:
            raise Exception(f"Failed to scan TikTok profile {username}: {e}")

    def get_recent_posts(self, username: str, limit: int = 5) -> list[VideoMeta]:
        """Fetches the 'limit' most recent posts from a TikTok creator."""
        
        if not username.startswith('@'):
            username = f"@{username}"
            
        url = f"https://www.tiktok.com/{username}"
        
        # We update the options to actually grab the playlist entries up to the limit
        opts = self.ydl_opts.copy()
        opts['playlistend'] = limit
        
        posts = []
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                entries = info.get('entries', [])
                
                for entry in entries:
                    if not entry:
                        continue
                        
                    # TikTok video IDs are the long string of numbers in the URL
                    video_id = entry.get('id')
                    video_url = entry.get('url') or f"https://www.tiktok.com/{username}/video/{video_id}"
                    
                    # yt-dlp usually returns timestamp as an integer
                    timestamp = entry.get('timestamp')
                    posted_date = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
                    
                    # Safely grab the duration and text
                    duration = entry.get('duration', 0)
                    post_caption = entry.get('title') or entry.get('description') or ""

                    posts.append(VideoMeta(
                        platform="tiktok",
                        platform_id=video_id,
                        creator_username=username.replace("@", ""),
                        url=video_url,
                        posted_at=posted_date,
                        language=None,
                        content_type="video",             # <--- ADDED
                        duration_seconds=duration,        # <--- ADDED
                        caption_text=post_caption         # <--- ADDED (Renamed from description)
                    ))
                    
            return posts
        except Exception as e:
            raise Exception(f"Failed to fetch TikTok posts for {username}: {e}")