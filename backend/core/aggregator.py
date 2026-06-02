"""
AI 新闻聚合器
整合多个信息源，进行 AI 分析、去重和分类
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from urllib.parse import urlparse
import httpx

# 数据抓取器
from core.scrapers.hackernews import HackerNewsScraper
from core.scrapers.reddit import RedditScraper
from core.scrapers.rss import RSSScraper
from core.scrapers.github import GitHubTrendingScraper
from core.scrapers.arxiv_api import ArxivAPIScraper
from core.ai.client import get_glm_client
from core.ai.analyzer import ContentAnalyzer
from core.config import load_sources_config, get_score_threshold

# 数据模型
from models.horizon_models import (
    ContentItem, HackerNewsConfig, RedditConfig, RSSSourceConfig,
    RedditSubredditConfig, SourceType
)
from models.ai_news import AggregatedItem, AggregationLog, TOPICS
from models.database import async_session

from sqlalchemy import select

logger = logging.getLogger(__name__)


class AINewsAggregator:
    """AI 新闻聚合器"""

    def __init__(self):
        self._sources_config: Optional[Dict] = None

    def _get_sources_config(self) -> Dict:
        """获取信息源配置（单次加载，避免重复 IO）"""
        if self._sources_config is None:
            self._sources_config = load_sources_config()
        return self._sources_config
    
    async def aggregate_and_save(self) -> List[AggregatedItem]:
        """
        执行全局聚合
        返回保存的条目列表
        """
        task_id = f"aggregation_{int(datetime.now().timestamp())}"
        started_at = int(datetime.now().timestamp())
        
        # 创建日志
        async with async_session() as db:
            log = AggregationLog(
                task_id=task_id,
                status="running"
                # 注意：开源版不传 started_at，使用数据库默认值
            )
            db.add(log)
            await db.commit()
            log_id = log.id
        
        try:
            # 1. 抓取所有信息源
            # 时间窗口（支持环境变量配置）
            # 注意：所有时间统一使用UTC，避免时区混淆
            # - 服务器时间：UTC
            # - 北京时间：UTC+8
            # - 美国PST：UTC-8
            # 例如：北京早上8点 = UTC 00:00，此时抓取过去24小时的内容
            #      相当于北京时间"昨天08:00 - 今天08:00"的内容
            env_hours = os.getenv("TIME_WINDOW_HOURS")
            if env_hours is not None:
                hours = int(env_hours)
            else:
                config = self._get_sources_config()
                hours = int(config.get("aggregation", {}).get("time_window_hours", 24))
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            logger.info(f"[{task_id}] 开始抓取，时间窗口: {hours}小时")
            logger.info(f"[{task_id}] UTC时间范围: {since.isoformat()} - {datetime.now(timezone.utc).isoformat()}")
            logger.info(f"[{task_id}] 北京时间范围: {(since + timedelta(hours=8)).strftime('%m-%d %H:%M')} - {(datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%m-%d %H:%M')}")
            
            all_items = await self._fetch_all_sources(since)
            logger.info(f"[{task_id}] 抓取完成: {len(all_items)} 条")
            
            if not all_items:
                logger.warning(f"[{task_id}] 没有抓取到新内容")
                await self._update_log(log_id, "success", 0, 0, 0, int((datetime.now().timestamp() - started_at) * 1000))
                return []
            
            # 2. 跨源去重
            merged_items = self._merge_cross_source_duplicates(all_items)
            logger.info(f"[{task_id}] 跨源去重后: {len(merged_items)} 条")
            
            # 3. AI 分析
            analyzed_items = await self._analyze_content(merged_items)
            logger.info(f"[{task_id}] AI 分析完成: {len(analyzed_items)} 条")
            
            # 统计 token 使用量
            total_tokens = sum(item.metadata.get('tokens_used', 0) for item in analyzed_items)
            logger.info(f"[{task_id}] Token 使用: {total_tokens:,} tokens")
            
            # 4. 按评分过滤（统一阈值 + 源特定阈值）
            threshold = get_score_threshold()
            
            # 获取源特定配置
            sources_config = self._get_sources_config()
            arxiv_config = sources_config.get("arxiv_api", {})
            arxiv_min_score = arxiv_config.get("min_score", threshold)
            
            important_items = []
            arxiv_filtered_count = 0
            
            for item in analyzed_items:
                if not item.ai_score:
                    continue
                
                # arXiv 使用更高的评分阈值
                if item.source_type == SourceType.ARXIV:
                    if item.ai_score >= arxiv_min_score:
                        important_items.append(item)
                    else:
                        arxiv_filtered_count += 1
                # 其他来源使用全局阈值
                elif item.ai_score >= threshold:
                    important_items.append(item)
            
            important_items.sort(key=lambda x: x.ai_score or 0, reverse=True)
            logger.info(f"[{task_id}] 评分过滤 (全局>={threshold}, arXiv>={arxiv_min_score}): {len(important_items)} 条")
            if arxiv_filtered_count > 0:
                logger.info(f"[{task_id}] arXiv 额外过滤: {arxiv_filtered_count} 条论文")
            
            # 5. 主题去重
            deduped_items = self._merge_topic_duplicates(important_items)
            logger.info(f"[{task_id}] 主题去重后: {len(deduped_items)} 条")
            
            # 6. 保存到数据库
            saved_items = await self._save_to_database(deduped_items)
            logger.info(f"[{task_id}] 保存完成: {len(saved_items)} 条")
            
            # 更新日志
            duration_ms = int((datetime.now().timestamp() - started_at) * 1000)
            await self._update_log(
                log_id, "success",
                len(all_items), len(analyzed_items), len(saved_items),
                duration_ms, total_tokens
            )
            
            return saved_items
        
        except Exception as e:
            logger.exception(f"[{task_id}] 聚合失败: {e}")
            await self._update_log(log_id, "error", 0, 0, 0, 0, error_msg=str(e))
            raise
    
    async def _fetch_all_sources(self, since: datetime) -> List[ContentItem]:
        """抓取所有信息源（HackerNews + RSS + Reddit + GitHub）"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            tasks = []
            
            # 1. HackerNews
            hn_config = self._build_hackernews_config()
            if hn_config.enabled:
                hn_scraper = HackerNewsScraper(hn_config, client)
                tasks.append(self._fetch_with_log("HackerNews", hn_scraper, since))
            
            # 2. RSS 源（从配置文件加载）
            rss_sources = self._build_rss_sources()
            if rss_sources:
                rss_scraper = RSSScraper(rss_sources, client)
                tasks.append(self._fetch_with_log("RSS", rss_scraper, since))
            
            # 3. Reddit（从配置文件加载，需要 API credentials）
            reddit_config = self._build_reddit_config()
            if reddit_config and reddit_config.get("enabled") and os.getenv("REDDIT_CLIENT_ID"):
                reddit_scraper = RedditScraper(reddit_config, client)
                tasks.append(self._fetch_with_log("Reddit", reddit_scraper, since))
            
            # 4. GitHub Trending（从配置文件加载）
            github_config = self._build_github_config()
            if github_config and github_config.get("enabled") and os.getenv("GITHUB_ACCESS_TOKEN"):
                github_scraper = GitHubTrendingScraper(github_config, client)
                tasks.append(self._fetch_with_log("GitHub", github_scraper, since))
            
            # 5. arXiv API（从配置文件加载，使用 48 小时窗口）
            arxiv_config = self._build_arxiv_config()
            if arxiv_config and arxiv_config.get("enabled"):
                arxiv_scraper = ArxivAPIScraper(arxiv_config, client)
                arxiv_since = datetime.now(timezone.utc) - timedelta(hours=48)
                tasks.append(self._fetch_with_log("arXiv", arxiv_scraper, arxiv_since))
            
            # 并发抓取
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            all_items = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"抓取错误: {result}")
                elif isinstance(result, list):
                    all_items.extend(result)
            
            return all_items
    
    async def _fetch_with_log(self, name: str, scraper, since: datetime) -> List[ContentItem]:
        """带日志的抓取"""
        try:
            logger.info(f"  → 抓取 {name}...")
            items = await scraper.fetch(since)
            logger.info(f"  ✓ {name}: {len(items)} 条")
            return items
        except Exception as e:
            logger.error(f"  ✗ {name} 失败: {e}")
            return []
    
    def _build_hackernews_config(self) -> HackerNewsConfig:
        """从配置文件构建 HackerNews 配置"""
        try:
            config = self._get_sources_config()

            hn_config = config.get("hackernews", {})
            return HackerNewsConfig(
                enabled=hn_config.get("enabled", True),
                fetch_top_stories=hn_config.get("fetch_top_stories", 40),
                min_score=hn_config.get("min_score", 100)
            )
        except Exception as e:
            logger.warning(f"加载 HackerNews 配置失败: {e}，使用默认配置")
            return HackerNewsConfig(enabled=True, fetch_top_stories=40, min_score=100)
    
    def _build_reddit_config(self) -> Optional[dict]:
        """从配置文件构建 Reddit 配置（简化版）"""
        try:
            config = self._get_sources_config()

            reddit_config = config.get("reddit", {})
            if not reddit_config.get("enabled", False):
                return None
            
            # 直接返回配置字典，不使用复杂的 Pydantic 模型
            return {
                "enabled": True,
                "subreddits": reddit_config.get("subreddits", []),
                "comment_limit": reddit_config.get("comment_limit", 3)
            }
            
        except Exception as e:
            logger.warning(f"加载 Reddit 配置失败: {e}")
            return None
    
    def _build_github_config(self) -> Optional[dict]:
        """从配置文件构建 GitHub 配置"""
        try:
            config = self._get_sources_config()
            github_config = config.get("github", {})
            
            if not github_config.get("enabled", False):
                return None
            
            # 添加API token
            import os
            github_config["api_token"] = os.getenv("GITHUB_ACCESS_TOKEN")
            
            return github_config
        except Exception as e:
            logger.warning(f"加载 GitHub 配置失败: {e}")
            return None
    
    def _build_arxiv_config(self) -> Optional[dict]:
        """从配置文件构建 arXiv API 配置"""
        try:
            config = self._get_sources_config()
            arxiv_config = config.get("arxiv_api", {})
            
            if not arxiv_config.get("enabled", False):
                return None
            
            return arxiv_config
        except Exception as e:
            logger.warning(f"加载 arXiv API 配置失败: {e}")
            return None
    
    def _build_rss_sources(self) -> List[RSSSourceConfig]:
        """
        从配置文件加载 RSS 信息源
        基于 config/sources.json
        """
        try:
            config = self._get_sources_config()
            sources = []
            rss_sources_config = config.get("rss_sources", [])
            
            for src in rss_sources_config:
                if src.get("enabled", True):
                    sources.append(RSSSourceConfig(
                        name=src["name"],
                        url=src["url"],
                        enabled=True,
                        category=src.get("category", "general")
                    ))
            
            logger.info(f"从配置文件加载了 {len(sources)} 个 RSS 信息源")
            return sources
            
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return self._build_default_rss_sources()
    
    def _build_default_rss_sources(self) -> List[RSSSourceConfig]:
        """
        默认 RSS 信息源（配置文件加载失败时使用）
        """
        sources = []
        
        # 基础官方 RSS（来自 config/sources.json）
        official_rss = [
            ("OpenAI Research", "https://raw.githubusercontent.com/Olshansk/rss-feeds/refs/heads/main/feeds/feed_openai_research.xml", "research"),
            ("Anthropic News", "https://raw.githubusercontent.com/Olshansk/rss-feeds/refs/heads/main/feeds/feed_anthropic_news.xml", "product_updates"),
            ("Anthropic Research", "https://raw.githubusercontent.com/Olshansk/rss-feeds/refs/heads/main/feeds/feed_anthropic_research.xml", "research"),
            ("Google AI Blog", "https://blog.google/technology/ai/rss/", "product_updates"),
            ("xAI News", "https://raw.githubusercontent.com/Olshansk/rss-feeds/refs/heads/main/feeds/feed_xainews.xml", "product_updates"),
            ("DeepMind", "https://deepmind.google/blog/rss.xml", "research"),
            ("Hugging Face", "https://huggingface.co/blog/feed.xml", "tools_discovery"),
            ("MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "industry"),
            ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "industry"),
            ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", "industry"),
        ]
        
        for name, url, category in official_rss:
            sources.append(RSSSourceConfig(
                name=name,
                url=url,
                enabled=True,
                category=category
            ))
        
        logger.info(f"使用默认配置: {len(sources)} 个 RSS 信息源")
        return sources
    
    def _merge_cross_source_duplicates(self, items: List[ContentItem]) -> List[ContentItem]:
        """
        跨源去重：基于 URL 合并重复内容
        """
        def normalize_url(url: str) -> str:
            parsed = urlparse(str(url))
            host = parsed.hostname or ""
            if host.startswith("www."):
                host = host[4:]
            path = parsed.path.rstrip("/")
            return f"{host}{path}"
        
        url_groups: Dict[str, List[ContentItem]] = {}
        for item in items:
            key = normalize_url(str(item.url))
            url_groups.setdefault(key, []).append(item)
        
        merged = []
        for key, group in url_groups.items():
            if len(group) == 1:
                merged.append(group[0])
                continue
            
            # 选择内容最丰富的作为主条目
            primary = max(group, key=lambda x: len(x.content or ""))
            
            # 记录合并信息
            all_sources = set()
            for item in group:
                all_sources.add(item.source_type.value)
                for mk, mv in item.metadata.items():
                    if mk not in primary.metadata or not primary.metadata[mk]:
                        primary.metadata[mk] = mv
            
            primary.metadata["merged_sources"] = list(all_sources)
            merged.append(primary)
        
        logger.info(f"  URL去重: {len(items)} → {len(merged)} 条")
        return merged
    
    async def _analyze_content(self, items: List[ContentItem]) -> List[ContentItem]:
        """AI 分析（使用智谱 GLM）"""
        logger.info(f"  → AI 分析 {len(items)} 条...")
        
        glm_client = get_glm_client()
        analyzer = ContentAnalyzer(glm_client)
        return await analyzer.analyze_batch(items)
    
    def _merge_topic_duplicates(
        self, items: List[ContentItem], threshold: float = 0.25
    ) -> List[ContentItem]:
        """
        主题去重：基于原始标题相似度、标签重叠和关键实体
        
        优化策略：
        1. 使用原始标题（original_title）进行去重，避免翻译失真
        2. 降低相似度阈值：0.33 → 0.25（更敏感）
        3. 增加关键实体匹配：检测公司名、产品名等
        4. 多条件判定：标题相似度 OR 标签重叠 OR 关键实体匹配
        """
        def title_tokens(title: str) -> set:
            tokens = set()
            # 英文单词（3个字母以上）
            for w in re.findall(r'[a-zA-Z]{3,}', title):
                tokens.add(w.lower())
            # 中文二元组
            cjk = re.sub(r'[^\u4e00-\u9fff]', '', title)
            for i in range(len(cjk) - 1):
                tokens.add(cjk[i:i + 2])
            return tokens
        
        def extract_key_entities(title: str) -> set:
            """
            提取关键实体（公司名、产品名、人名等）
            用于跨语言去重
            """
            entities = set()
            # 公司名（英文大写开头的连续词）
            for match in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b', title):
                entities.add(match.group(1).lower())
            # 常见 AI 公司/产品（英文 + 中文）
            common_names = [
                'openai', 'anthropic', 'claude', 'gpt', 'chatgpt', 'gemini', 'meta', 'llama',
                'microsoft', 'google', 'deepmind', 'midjourney', 'stable diffusion', 'dall-e',
                'openai', 'anthropic', 'claude', 'deepseek', '字节', '阿里', '腾讯', '百度',
                '国防部', 'dod', 'pentagon', 'lawsuit', '诉讼', '起诉'
            ]
            title_lower = title.lower()
            for name in common_names:
                if name in title_lower:
                    entities.add(name)
            return entities
        
        kept: List[ContentItem] = []
        duplicate_count = 0
        
        for item in items:
            # 优先使用原始标题（避免翻译失真），如果没有则使用当前标题
            item_title = item.original_title or item.title
            tokens = title_tokens(item_title)
            item_tags = set(item.ai_tags or [])
            item_entities = extract_key_entities(item_title)
            
            merged_into = None
            for accepted in kept:
                accepted_title = accepted.original_title or accepted.title
                a_tokens = title_tokens(accepted_title)
                union = a_tokens | tokens
                title_sim = len(a_tokens & tokens) / len(union) if union else 0.0
                tag_overlap = len(set(accepted.ai_tags or []) & item_tags)
                
                # 关键实体匹配度
                a_entities = extract_key_entities(accepted_title)
                entity_overlap = len(item_entities & a_entities)
                
                # 多条件判定（满足任一即视为重复）
                conditions = [
                    title_sim >= threshold,  # 标题相似度 ≥ 25%
                    (tag_overlap >= 2 and title_sim >= 0.15),  # 标签重叠 ≥ 2 且相似度 ≥ 15%
                    (entity_overlap >= 2 and title_sim >= 0.10),  # 关键实体重叠 ≥ 2 且相似度 ≥ 10%
                ]
                
                if any(conditions):
                    merged_into = accepted
                    duplicate_count += 1
                    logger.debug(
                        f"  去重: {item.title[:50]}... "
                        f"(原始标题相似度={title_sim:.2f}, 标签重叠={tag_overlap}, 实体重叠={entity_overlap})"
                    )
                    break
            
            if merged_into is None:
                kept.append(item)
        
        logger.info(f"  主题去重: {len(items)} → {len(kept)} 条 (去除 {duplicate_count} 条重复)")
        return kept
    
    async def _save_to_database(self, items: List[ContentItem]) -> List[AggregatedItem]:
        """
        保存到数据库
        """
        saved_items = []
        
        async with async_session() as db:
            for item in items:
                # 话题分类
                topics = self._classify_topics(item)
                
                # 转换为 AggregatedItem
                agg_item = AggregatedItem(
                    content_id=item.id,
                    source_type=item.source_type.value,
                    source_name=item.metadata.get("feed_name") or item.source_type.value,
                    topics=json.dumps(topics, ensure_ascii=False),  # SQLite: JSON字符串
                    
                    title=item.title,
                    original_title=item.original_title,  # 保存原始标题
                    url=str(item.url),
                    content=item.content,
                    author=item.author,
                    
                    ai_score=item.ai_score or 0.0,
                    ai_reason=item.ai_reason,
                    ai_summary=item.ai_summary,
                    ai_tags=json.dumps(item.ai_tags or [], ensure_ascii=False),  # SQLite: JSON字符串
                    
                    # 保存metadata (包含discussion_url等)
                    metadata_json=json.dumps(item.metadata, ensure_ascii=False) if item.metadata else None,  # SQLite: JSON字符串
                    
                    published_at=item.published_at,
                    fetched_at=datetime.now(timezone.utc)
                )
                
                # 使用 URL 去重（更可靠）
                from sqlalchemy import select
                existing = await db.execute(
                    select(AggregatedItem).where(AggregatedItem.url == str(item.url))
                )
                existing_item = existing.scalar_one_or_none()
                
                if existing_item:
                    # 如果新的评分更高，更新；否则跳过
                    new_score = item.ai_score or 0.0
                    old_score = existing_item.ai_score or 0.0
                    
                    if new_score > old_score:
                        logger.info(f"  更新更高评分: {item.title[:50]}... ({old_score:.1f} -> {new_score:.1f})")
                        # 更新现有记录
                        existing_item.title = item.title
                        existing_item.original_title = item.original_title
                        existing_item.ai_score = new_score
                        existing_item.ai_reason = item.ai_reason
                        existing_item.ai_summary = item.ai_summary
                        existing_item.ai_tags = json.dumps(item.ai_tags or [], ensure_ascii=False)  # SQLite: JSON字符串
                        existing_item.topics = json.dumps(topics, ensure_ascii=False)  # SQLite: JSON字符串
                        # 注意：不更新 fetched_at，保留首次抓取时间
                        saved_items.append(existing_item)
                    else:
                        logger.debug(f"  跳过重复(URL): {item.id}")
                    continue
                
                db.add(agg_item)
                saved_items.append(agg_item)
            
            await db.commit()
        
        return saved_items
    
    def _classify_topics(self, item: ContentItem) -> List[str]:
        """话题分类：优先使用 AI 的 topics，其次基于 category 和来源类型"""
        # 优先使用 AI 返回的分类
        if item.topics and isinstance(item.topics, list) and len(item.topics) > 0:
            # 验证分类是否有效
            valid_topics = [t for t in item.topics if t in TOPICS]
            if valid_topics:
                return valid_topics[:3]  # 最多 3 个话题
        
        # 备用方案：基于 metadata 中的 category
        topics = []
        category = item.metadata.get("category", "")
        
        if category and category in TOPICS:
            topics.append(category)
        
        # 基于 AI 标签匹配（备用）
        tags = [t.lower() for t in item.ai_tags or []]
        for topic_key, topic_info in TOPICS.items():
            keywords = topic_info.get("keywords", [])
            if any(kw in tags for kw in keywords):
                if topic_key not in topics:
                    topics.append(topic_key)
        
        # 默认分类
        if not topics:
            topics.append("daily_brief")  # 开源版默认分类
        
        return list(set(topics))[:3]  # 最多 3 个话题
    
    async def _update_log(
        self, log_id: int, status: str,
        items_fetched: int, items_analyzed: int, items_saved: int,
        duration_ms: int, tokens_used: int = 0, error_msg: str = ""
    ):
        """更新聚合日志"""
        async with async_session() as db:
            log = await db.get(AggregationLog, log_id)
            if log:
                log.status = status
                log.items_fetched = items_fetched
                log.items_analyzed = items_analyzed
                log.items_saved = items_saved
                log.tokens_used = tokens_used
                log.duration_ms = duration_ms
                log.error_msg = error_msg
                log.finished_at = int(datetime.now().timestamp())
                await db.commit()
