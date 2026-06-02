"""GitHub Trending scraper using unofficial trending API."""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper
from models.horizon_models import ContentItem, SourceType

logger = logging.getLogger(__name__)


class GitHubTrendingScraper(BaseScraper):
    """Scraper for GitHub trending repositories."""
    
    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        """Initialize GitHub Trending scraper.
        
        Args:
            config: Configuration dict with:
                - enabled: bool
                - topics: List[str] (for filtering, optional)
                - languages: List[str] (e.g. ["python", "typescript", ""])
                - fetch_limit: int
                - since: str ("daily", "weekly", "monthly")
            http_client: Shared async HTTP client
        """
        super().__init__(config, http_client)
        self.base_url = "https://github.com/trending"
        
    async def fetch(self, since: datetime) -> List[ContentItem]:
        """Fetch GitHub Trending repositories.
        
        Args:
            since: Only fetch items after this time
            
        Returns:
            List[ContentItem]: Trending repositories
        """
        if not self.config.get("enabled", True):
            return []
        
        languages = self.config.get("languages", ["python", "typescript", "javascript", ""])
        fetch_limit = self.config.get("fetch_limit", 15)
        since_param = self.config.get("since", "daily")
        
        all_items = []
        for lang in languages:
            try:
                items = await self._fetch_trending_by_language(lang, since_param, fetch_limit)
                all_items.extend(items)
            except Exception as e:
                logger.warning(f"Error fetching GitHub Trending for {lang or 'all'}: {e}")
        
        # 去重（可能不同语言有相同的仓库）
        seen_urls = set()
        unique_items = []
        for item in all_items:
            if str(item.url) not in seen_urls:
                seen_urls.add(str(item.url))
                unique_items.append(item)
        
        logger.info(f"Fetched {len(unique_items)} repositories from GitHub Trending")
        return unique_items[:fetch_limit]
    
    async def _fetch_trending_by_language(
        self,
        language: str,
        since: str,
        limit: int
    ) -> List[ContentItem]:
        """Fetch trending repositories for a specific language.
        
        Args:
            language: Programming language (empty string for all languages)
            since: "daily", "weekly", or "monthly"
            limit: Maximum number of repositories to fetch
            
        Returns:
            List[ContentItem]: Repository items
        """
        # 构建 URL
        if language:
            url = f"{self.base_url}/{language}"
        else:
            url = self.base_url
        
        params = {"since": since}
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        
        try:
            response = await self.client.get(url, params=params, headers=headers, follow_redirects=True)
            response.raise_for_status()
            
            # 解析 HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            items = []
            # 查找所有仓库条目
            articles = soup.find_all('article', class_='Box-row')
            
            for article in articles[:limit]:
                item = self._parse_repo_from_html(article, language)
                if item:
                    items.append(item)
            
            return items
                    
        except httpx.HTTPError as e:
            logger.warning(f"GitHub Trending page error for {language or 'all'}: {e}")
            return []
    
    def _parse_repo_from_html(self, article, language: str) -> Optional[ContentItem]:
        """Parse repository data from HTML article element."""
        try:
            # 获取仓库名称和链接
            h2 = article.find('h2', class_='h3')
            if not h2:
                return None
            
            link = h2.find('a')
            if not link:
                return None
            
            repo_path = link.get('href', '').strip()
            full_name = repo_path.lstrip('/')
            url = f"https://github.com{repo_path}"
            
            # 获取描述
            description_elem = article.find('p', class_='col-9')
            description = description_elem.get_text(strip=True) if description_elem else ""
            
            # 获取编程语言
            lang_elem = article.find('span', itemprop='programmingLanguage')
            repo_language = lang_elem.get_text(strip=True) if lang_elem else (language or "Unknown")
            
            # 获取 stars（今日新增）
            stars_elem = article.find('span', class_='d-inline-block float-sm-right')
            stars_today = 0
            if stars_elem:
                stars_text = stars_elem.get_text(strip=True)
                # 解析 "1,234 stars today" 格式
                match = re.search(r'([\d,]+)\s+stars?\s+today', stars_text)
                if match:
                    stars_today = int(match.group(1).replace(',', ''))
            
            # 获取总 stars
            total_stars_elem = article.find('svg', class_='octicon-star')
            total_stars = 0
            if total_stars_elem and total_stars_elem.parent:
                stars_text = total_stars_elem.parent.get_text(strip=True)
                match = re.search(r'([\d,]+)', stars_text)
                if match:
                    total_stars = int(match.group(1).replace(',', ''))
            
            # 获取 forks
            forks_elem = article.find('svg', class_='octicon-repo-forked')
            forks = 0
            if forks_elem and forks_elem.parent:
                forks_text = forks_elem.parent.get_text(strip=True)
                match = re.search(r'([\d,]+)', forks_text)
                if match:
                    forks = int(match.group(1).replace(',', ''))
            
            # 构建内容（不提及 star 数量，让 AI 分析更准确）
            content_parts = []
            if description:
                content_parts.append(f"Description: {description}")
            content_parts.append(f"Language: {repo_language}")
            
            content = "\n".join(content_parts)
            
            # 构建标题（突出项目名称和描述，不提及 star）
            if description:
                title = f"🔥 GitHub Trending: {full_name} - {description[:80]}"
            else:
                title = f"🔥 GitHub Trending: {full_name}"
            
            # 使用今天的日期作为发布时间
            published_at = datetime.now(timezone.utc)
            
            return ContentItem(
                id=self._generate_id("github", "trending", full_name.replace('/', '-')),
                source_type=SourceType.GITHUB,
                title=title,
                url=url,
                content=content,
                author=full_name.split('/')[0],
                published_at=published_at,
                metadata={
                    "stars": total_stars,
                    "stars_today": stars_today,
                    "forks": forks,
                    "language": repo_language,
                    "full_name": full_name,
                    "repo_url": url
                }
            )
            
        except Exception as e:
            logger.warning(f"Error parsing GitHub trending repo: {e}")
            return None
