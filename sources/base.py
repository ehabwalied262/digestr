from abc import ABC, abstractmethod
from datetime import datetime
from models import VideoMeta, ProfileStats

class Source(ABC):
    @abstractmethod
    def get_profile_stats(self, username: str) -> ProfileStats:
        """Fetch total post count and basic profile info."""
        pass

    @abstractmethod
    def get_recent_posts(self, username: str, limit: int) -> list[VideoMeta]:
        """Fetch the N most recent posts, newest first."""
        pass

    @abstractmethod
    def get_posts_since(self, username: str, since: datetime) -> list[VideoMeta]:
        """Fetch posts newer than the given timestamp, newest first."""
        pass

    @abstractmethod
    def get_single_post(self, url: str) -> VideoMeta:
        """Extract metadata from a single post URL."""
        pass