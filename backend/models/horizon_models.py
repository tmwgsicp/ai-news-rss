"""
Horizon 数据模型（简化版，仅用于本项目）
"""

from enum import Enum
from datetime import datetime
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, HttpUrl


class SourceType(str, Enum):
    """内容来源类型"""
    RSS = "rss"
    HACKERNEWS = "hackernews"
    REDDIT = "reddit"
    GITHUB = "github"
    ARXIV = "arxiv"


class ContentItem(BaseModel):
    """内容条目"""
    id: str
    source_type: SourceType
    title: str  # 当前标题（AI分析后会变为中文翻译）
    url: HttpUrl
    content: Optional[str] = None
    author: Optional[str] = None
    published_at: datetime
    metadata: Dict[str, Any] = {}
    
    # 原始标题（用于去重，避免翻译失真）
    original_title: Optional[str] = None
    
    # AI 分析结果
    ai_score: Optional[float] = None
    ai_reason: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_tags: Optional[List[str]] = None
    topics: Optional[List[str]] = None  # AI 分类结果


class HackerNewsConfig(BaseModel):
    """HackerNews 配置"""
    enabled: bool = True
    fetch_top_stories: int = 40
    min_score: int = 100


class RedditSubredditConfig(BaseModel):
    """Reddit subreddit 配置"""
    subreddit: str
    enabled: bool = True
    sort: str = "hot"
    time_filter: str = "day"
    fetch_limit: int = 20
    min_score: int = 50


class RedditUserConfig(BaseModel):
    """Reddit 用户配置"""
    username: str
    enabled: bool = True
    fetch_limit: int = 20


class RedditConfig(BaseModel):
    """Reddit 配置"""
    enabled: bool = True
    subreddits: List[RedditSubredditConfig] = []
    users: List[str] = []
    fetch_comments: int = 3


class RSSSourceConfig(BaseModel):
    """RSS 源配置"""
    name: str
    url: str
    enabled: bool = True
    category: str = ""
    fetch_limit: Optional[int] = None  # 限制抓取条数
    description: Optional[str] = None
