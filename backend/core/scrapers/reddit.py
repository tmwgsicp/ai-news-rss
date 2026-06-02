"""Reddit scraper implementation using OAuth API."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional
import httpx

from .base import BaseScraper
from models.horizon_models import ContentItem, SourceType

logger = logging.getLogger(__name__)


class RedditScraper(BaseScraper):
    """Scraper for Reddit posts using official OAuth API."""

    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        """Initialize Reddit scraper with OAuth credentials.
        
        Args:
            config: Configuration dict with:
                - enabled: bool
                - subreddits: List[dict] with name, min_score, fetch_limit
                - comment_limit: int
            http_client: Shared async HTTP client
        """
        super().__init__(config, http_client)
        self.client_id = os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.access_token = None
        self.token_expires_at = 0

    async def fetch(self, since: datetime) -> List[ContentItem]:
        """Fetch Reddit posts from configured subreddits.
        
        Args:
            since: Only fetch items after this time
            
        Returns:
            List[ContentItem]: Reddit posts
        """
        if not self.config.get("enabled", True):
            return []

        if not self.client_id or not self.client_secret:
            logger.warning("Reddit API credentials not configured")
            return []

        # 获取访问令牌
        if not await self._ensure_access_token():
            logger.error("Failed to obtain Reddit access token")
            return []

        subreddits = self.config.get("subreddits", [])
        if not subreddits:
            return []

        tasks = []
        for subreddit in subreddits:
            if subreddit.get("enabled", True):
                tasks.append(self._fetch_subreddit(subreddit, since))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        items = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Error fetching Reddit subreddit: {result}")
            elif isinstance(result, list):
                items.extend(result)
        
        return items

    async def _ensure_access_token(self) -> bool:
        """Ensure we have a valid access token."""
        now = datetime.now(timezone.utc).timestamp()
        
        # 如果令牌未过期，直接返回
        if self.access_token and now < self.token_expires_at:
            return True

        # 使用 client credentials 获取新令牌
        url = "https://www.reddit.com/api/v1/access_token"
        
        auth = (self.client_id, self.client_secret)
        data = {
            "grant_type": "client_credentials",
            "device_id": "ainewsrss_v1"
        }
        headers = {
            "User-Agent": "ainewsrss/1.0 by waytomaster"
        }

        try:
            response = await self.client.post(
                url,
                auth=auth,
                data=data,
                headers=headers
            )
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires_at = now + expires_in - 60  # 提前1分钟刷新
            
            logger.info(f"Obtained Reddit access token, expires in {expires_in}s")
            return True
            
        except httpx.HTTPError as e:
            logger.error(f"Failed to get Reddit access token: {e}")
            return False

    async def _fetch_subreddit(
        self,
        subreddit_config: dict,
        since: datetime
    ) -> List[ContentItem]:
        """Fetch posts from a specific subreddit."""
        name = subreddit_config.get("name")
        min_score = subreddit_config.get("min_score", 50)
        fetch_limit = subreddit_config.get("fetch_limit", 15)
        comment_limit = subreddit_config.get("comment_limit", self.config.get("comment_limit", 3))

        # 使用 OAuth API
        url = f"https://oauth.reddit.com/r/{name}/hot"
        
        params = {
            "limit": min(fetch_limit, 100),
            "t": "day",  # 今日热门
            "raw_json": 1
        }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "ainewsrss/1.0 by waytomaster"
        }

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            posts = data.get("data", {}).get("children", [])
            
            items = []
            for post_wrapper in posts:
                if post_wrapper.get("kind") != "t3":
                    continue
                    
                post = post_wrapper.get("data", {})
                
                # 检查评分
                score = post.get("score", 0)
                if score < min_score:
                    continue
                
                # 检查时间
                created_utc = post.get("created_utc", 0)
                created = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if created < since:
                    continue
                
                # 如果需要评论，获取评论
                comments_text = ""
                post_id = post.get("id")
                if comment_limit > 0 and post_id:
                    comments_text = await self._fetch_comments(name, post_id, comment_limit)
                
                # 解析为 ContentItem
                item = self._parse_post(post, comments_text, name)
                if item:
                    items.append(item)
            
            logger.info(f"Fetched {len(items)} posts from r/{name}")
            return items
            
        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch r/{name}: {e}")
            return []

    async def _fetch_comments(
        self,
        subreddit: str,
        post_id: str,
        limit: int
    ) -> str:
        """Fetch top comments for a post."""
        url = f"https://oauth.reddit.com/r/{subreddit}/comments/{post_id}"
        
        params = {
            "limit": limit,
            "depth": 1,
            "sort": "top",
            "raw_json": 1
        }
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "ainewsrss/1.0 by waytomaster"
        }

        try:
            response = await self.client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if not isinstance(data, list) or len(data) < 2:
                return ""
            
            comments = []
            for child in data[1].get("data", {}).get("children", []):
                if child.get("kind") != "t1":
                    continue
                
                comment = child.get("data", {})
                body = comment.get("body", "")
                author = comment.get("author", "unknown")
                score = comment.get("score", 0)
                
                if body and not comment.get("distinguished") == "moderator":
                    comments.append(f"[{author} ({score} pts)]: {body[:500]}")
            
            if comments:
                return "\n--- Top Comments ---\n" + "\n\n".join(comments[:limit])
            return ""
            
        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch comments for {post_id}: {e}")
            return ""

    def _parse_post(
        self,
        post: dict,
        comments_text: str,
        subreddit: str
    ) -> Optional[ContentItem]:
        """Parse Reddit post into ContentItem."""
        try:
            post_id = post.get("id")
            title = post.get("title", "")
            is_self = post.get("is_self", False)
            
            # 构建 URL
            permalink = post.get("permalink", "")
            discussion_url = f"https://www.reddit.com{permalink}"
            
            # 对于 self post 使用讨论链接，对于链接 post 使用外部链接
            if is_self:
                url = discussion_url
            else:
                url = post.get("url", discussion_url)
            
            author = post.get("author", "unknown")
            created_utc = post.get("created_utc", 0)
            created = datetime.fromtimestamp(created_utc, tz=timezone.utc)
            
            # 构建内容
            content_parts = []
            
            # Self post 的正文
            selftext = post.get("selftext", "")
            if selftext:
                if len(selftext) > 1500:
                    selftext = selftext[:1497] + "..."
                content_parts.append(selftext)
            
            # 评论
            if comments_text:
                content_parts.append(comments_text)
            
            content = "\n\n".join(content_parts)
            
            return ContentItem(
                id=self._generate_id("reddit", subreddit, post_id),
                source_type=SourceType.REDDIT,
                title=title,
                url=url,
                content=content,
                author=author,
                published_at=created,
                metadata={
                    "score": post.get("score", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                    "num_comments": post.get("num_comments", 0),
                    "subreddit": subreddit,
                    "is_self": is_self,
                    "flair": post.get("link_flair_text"),
                    "discussion_url": discussion_url,
                }
            )
            
        except Exception as e:
            logger.warning(f"Error parsing Reddit post: {e}")
            return None
