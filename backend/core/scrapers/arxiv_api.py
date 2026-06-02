"""arXiv API scraper - patient rate-limit strategy."""

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import List, Optional
import httpx

from .base import BaseScraper
from models.content_models import ContentItem, SourceType

logger = logging.getLogger(__name__)


class ArxivAPIScraper(BaseScraper):
    """arXiv scraper using official API.
    
    Strategy: respect rate limits strictly.
    - One request per category (not combined query)
    - 30s minimum between requests
    - Patient exponential backoff on 429 (up to 5min wait)
    - Full text fetch via arxiv-txt.org
    """
    
    _last_request_time = 0
    _min_request_interval = 30
    
    def __init__(self, config: dict, http_client: httpx.AsyncClient):
        super().__init__(config, http_client)
        self.base_url = "https://export.arxiv.org/api/query"
        self._headers = {
            'User-Agent': 'AI-NewsRSS/1.0 (https://github.com/tmwgsicp/ai-news-rss; mailto:creator@waytomaster.com)'
        }
        
    async def fetch(self, since: datetime) -> List[ContentItem]:
        """Fetch arXiv papers, one category at a time with patient rate limiting."""
        if not self.config.get("enabled", True):
            return []
        
        categories = self.config.get("categories", ["cs.AI", "cs.CL"])
        max_results = self.config.get("max_results", 100)
        per_category = max(5, max_results // len(categories))
        
        all_items = []
        
        for i, cat in enumerate(categories):
            logger.info(f"arXiv: fetching {cat} ({i+1}/{len(categories)}, {per_category} papers)...")
            
            items = await self._fetch_category(cat, since, per_category)
            all_items.extend(items)
            logger.info(f"arXiv: {cat} returned {len(items)} papers")
            
            # Wait between categories
            if i < len(categories) - 1:
                logger.info(f"arXiv: waiting {self._min_request_interval}s before next category...")
                await asyncio.sleep(self._min_request_interval)
        
        # Deduplicate by arxiv_id (papers can appear in multiple categories)
        seen = set()
        unique = []
        for item in all_items:
            aid = item.metadata.get("arxiv_id", item.id)
            if aid not in seen:
                seen.add(aid)
                unique.append(item)
        
        # Fetch full text for each paper (with rate limiting)
        for item in unique:
            arxiv_id = item.metadata.get("arxiv_id", "").split('/')[-1]
            if arxiv_id:
                full_text = await self._fetch_full_text(arxiv_id)
                if full_text:
                    abstract = item.content.replace("Abstract: ", "")
                    item.content = f"Full Text (truncated):\n{full_text}\n\nAbstract: {abstract}"
                    item.metadata["has_full_text"] = True
                else:
                    item.metadata["has_full_text"] = False
        
        result = unique[:max_results]
        logger.info(f"arXiv total: {len(result)} unique papers (from {len(all_items)} raw)")
        return result
    
    async def _fetch_category(self, category: str, since: datetime, max_results: int) -> List[ContentItem]:
        """Fetch papers for a single category with patient retry."""
        params = {
            'search_query': f'cat:{category}',
            'sortBy': 'lastUpdatedDate',
            'sortOrder': 'descending',
            'max_results': max_results
        }
        url = f"{self.base_url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        
        # Respect rate limit
        await self._wait_for_rate_limit()
        
        # Patient retry: 30s, 60s, 120s, 180s, 300s
        max_retries = 6
        retry_delays = [30, 60, 120, 180, 300, 300]
        
        for attempt in range(max_retries):
            try:
                ArxivAPIScraper._last_request_time = time.time()
                response = await self.client.get(
                    url, timeout=90.0, follow_redirects=True, headers=self._headers
                )
                response.raise_for_status()
                
                items = self._parse_atom_response(response.text, since, [category])
                return items
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = retry_delays[attempt]
                    logger.warning(
                        f"arXiv 429 for {category}, waiting {wait}s "
                        f"(attempt {attempt+1}/{max_retries})..."
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"arXiv HTTP {e.response.status_code} for {category}")
                    return []
                    
            except (httpx.ReadTimeout, httpx.ConnectTimeout):
                wait = retry_delays[attempt]
                logger.warning(
                    f"arXiv timeout for {category}, waiting {wait}s "
                    f"(attempt {attempt+1}/{max_retries})..."
                )
                await asyncio.sleep(wait)
                
            except Exception as e:
                logger.error(f"arXiv unexpected error for {category}: {e}")
                return []
        
        logger.error(f"arXiv failed for {category} after {max_retries} attempts")
        return []
    
    async def _wait_for_rate_limit(self):
        """Wait until rate limit interval has passed."""
        elapsed = time.time() - ArxivAPIScraper._last_request_time
        if elapsed < ArxivAPIScraper._min_request_interval:
            wait = ArxivAPIScraper._min_request_interval - elapsed
            logger.info(f"arXiv rate limit: waiting {wait:.0f}s...")
            await asyncio.sleep(wait)
    
    async def _fetch_full_text(self, arxiv_id: str) -> Optional[str]:
        """Fetch paper full text from arxiv-txt.org."""
        try:
            txt_url = f"https://arxiv-txt.org/pdf/{arxiv_id}"
            response = await self.client.get(txt_url, timeout=30.0, follow_redirects=True)
            
            if response.status_code == 200:
                full_text = response.text
                if len(full_text) > 8000:
                    full_text = full_text[:8000] + "\n\n[Content truncated for length...]"
                return full_text
            return None
                
        except Exception as e:
            logger.debug(f"Full text unavailable for {arxiv_id}: {e}")
            return None
    
    def _parse_atom_response(
        self, 
        xml_text: str, 
        since: datetime,
        target_categories: List[str]
    ) -> List[ContentItem]:
        """Parse Atom XML response from arXiv API."""
        items = []
        
        try:
            root = ET.fromstring(xml_text)
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            entries = root.findall('atom:entry', ns)
            
            for entry in entries:
                try:
                    updated_el = entry.find('atom:updated', ns)
                    published_el = entry.find('atom:published', ns)
                    
                    if updated_el is not None and updated_el.text:
                        time_str = updated_el.text
                    else:
                        time_str = published_el.text
                    
                    entry_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    published_at = datetime.fromisoformat(
                        published_el.text.replace('Z', '+00:00')
                    )
                    
                    if entry_time < since:
                        continue
                    
                    categories = entry.findall('atom:category', ns)
                    cats = [c.get('term') for c in categories]
                    if not cats:
                        continue
                    
                    primary_category = cats[0]
                    if not any(cat in target_categories for cat in cats):
                        continue
                    
                    title = entry.find('atom:title', ns).text.strip()
                    title = ' '.join(title.split())
                    
                    arxiv_id = entry.find('atom:id', ns).text
                    arxiv_id_short = arxiv_id.split('/')[-1]
                    
                    pdf_link = entry.find('atom:link[@title="pdf"]', ns)
                    url = pdf_link.get('href') if pdf_link is not None else arxiv_id
                    
                    summary = entry.find('atom:summary', ns).text.strip()
                    summary = ' '.join(summary.split())
                    
                    authors = entry.findall('atom:author/atom:name', ns)
                    author_names = [a.text for a in authors[:3]]
                    author = ', '.join(author_names)
                    if len(authors) > 3:
                        author += f' et al. ({len(authors)} authors)'
                    
                    item = ContentItem(
                        id=self._generate_id("arxiv", "paper", arxiv_id_short),
                        source_type=SourceType.ARXIV,
                        title=title,
                        url=url,
                        content=f"Abstract: {summary}",
                        author=author,
                        published_at=published_at,
                        metadata={
                            "arxiv_id": arxiv_id,
                            "categories": cats,
                            "primary_category": primary_category,
                            "feed_name": "arXiv",
                            "source": "arXiv API"
                        }
                    )
                    items.append(item)
                    
                except Exception as e:
                    logger.warning(f"Error parsing arXiv entry: {e}")
                    continue
            
            logger.info(f"arXiv parsed: {len(items)} papers from {len(entries)} entries")
            return items
            
        except ET.ParseError as e:
            logger.error(f"Failed to parse arXiv XML: {e}")
            return []
