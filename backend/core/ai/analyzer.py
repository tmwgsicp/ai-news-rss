"""Content analysis using AI."""

import json
import logging
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential

from .client import GLMClient
from .prompts import CONTENT_ANALYSIS_SYSTEM, CONTENT_ANALYSIS_USER
from models.content_models import ContentItem
from models.ai_news import TOPICS

logger = logging.getLogger(__name__)


class ContentAnalyzer:
    """使用智谱 GLM 分析内容"""

    def __init__(self, glm_client: GLMClient):
        self.client = glm_client

    async def analyze_batch(
        self,
        items: List[ContentItem],
        batch_size: int = 10
    ) -> List[ContentItem]:
        """批量分析内容"""
        analyzed_items = []
        total = len(items)
        
        # 直接 AI 分析所有内容，不做硬过滤
        # AI 模型会根据 prompts.py 中的规则自主判断内容质量和相关性
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            logger.info(f"  AI 分析进度: {i}/{len(items)}")
            
            for item in batch:
                try:
                    await self._analyze_item(item)
                    analyzed_items.append(item)
                except Exception as e:
                    logger.error(f"分析失败 {item.id}: {e}")
                    item.ai_score = 0.0
                    item.ai_reason = "分析失败"
                    item.ai_summary = item.title
                    analyzed_items.append(item)

        return analyzed_items
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=10)
    )
    async def _analyze_item(self, item: ContentItem) -> None:
        """Analyze a single content item.

        Args:
            item: Content item to analyze (modified in-place)
        """
        # Prepare content section
        content_section = ""
        if item.content:
            # Split off comments if present
            content_text = item.content
            if "--- Top Comments ---" in content_text:
                main, comments_part = content_text.split("--- Top Comments ---", 1)
                content_section = f"Content: {main.strip()[:800]}"
            else:
                content_section = f"Content: {content_text[:1000]}"

        # Prepare discussion section (comments, engagement)
        discussion_parts = []
        if item.content and "--- Top Comments ---" in item.content:
            comments_part = item.content.split("--- Top Comments ---", 1)[1]
            discussion_parts.append(f"Community Comments:\n{comments_part[:1500]}")

        meta = item.metadata
        engagement_items = []
        if meta.get("score"):
            engagement_items.append(f"score: {meta['score']}")
        if meta.get("descendants"):
            engagement_items.append(f"{meta['descendants']} comments")
        if meta.get("favorite_count"):
            engagement_items.append(f"{meta['favorite_count']} likes")
        if meta.get("retweet_count"):
            engagement_items.append(f"{meta['retweet_count']} retweets")
        if meta.get("reply_count"):
            engagement_items.append(f"{meta['reply_count']} replies")
        if meta.get("views"):
            engagement_items.append(f"{meta['views']} views")
        if meta.get("bookmarks"):
            engagement_items.append(f"{meta['bookmarks']} bookmarks")
        if meta.get("upvote_ratio"):
            engagement_items.append(f"upvote ratio: {meta['upvote_ratio']:.0%}")
        if engagement_items:
            discussion_parts.append(f"Engagement: {', '.join(engagement_items)}")
        if meta.get("discussion_url"):
            discussion_parts.append(f"Discussion: {meta['discussion_url']}")
        if meta.get("community_note"):
            discussion_parts.append(f"Community Note: {meta['community_note']}")

        discussion_section = "\n".join(discussion_parts) if discussion_parts else ""

        # Generate user prompt
        user_prompt = CONTENT_ANALYSIS_USER.format(
            title=item.title,
            source=f"{item.source_type.value}",
            author=item.author or "Unknown",
            url=str(item.url),
            content_section=content_section,
            discussion_section=discussion_section
        )

        # Get AI completion
        response, tokens_used = await self.client.complete(
            system=CONTENT_ANALYSIS_SYSTEM,
            user=user_prompt,
            temperature=0.3
        )
        
        # Store token count for statistics
        item.metadata = item.metadata or {}
        item.metadata['tokens_used'] = tokens_used

        # Parse JSON response
        try:
            result = json.loads(response)
        except json.JSONDecodeError as e:
            # Try to extract JSON from markdown code block
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
                result = json.loads(json_str)
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
                result = json.loads(json_str)
            else:
                # 记录原始响应以便调试
                logger.error(f"Failed to parse JSON response for {item.id}")
                logger.error(f"Response: {response[:500]}")
                raise ValueError(f"Invalid JSON response: {response[:200]}")
        
        # 验证必需字段
        if "score" not in result:
            logger.error(f"Missing 'score' field in response for {item.id}")
            logger.error(f"Response keys: {result.keys()}")
            raise ValueError("Missing required field: score")

        # Update item with analysis results
        item.ai_score = float(result.get("score", 0))
        item.ai_reason = result.get("reason", "")
        
        # 清理 AI summary 中的 Markdown 语法
        raw_summary = result.get("summary", item.title[:200])
        from utils.text_cleaner import clean_for_display
        item.ai_summary = clean_for_display(raw_summary)
        
        item.ai_tags = result.get("tags", [])
        
        # 处理中文标题
        title_zh = result.get("title_zh", "")
        if title_zh and title_zh != item.title:
            # 保存原始标题（用于去重）
            if not item.original_title:
                item.original_title = item.title
            # 直接使用中文标题（用户可点原文查看英文）
            item.title = title_zh
        
        # 处理分类（category，单个）
        category = result.get("category", "")
        if category and isinstance(category, str):
            # 验证分类是否有效
            try:
                if category in TOPICS:
                    item.topics = [category]  # 单个分类，存入列表
                else:
                    logger.warning(f"Unknown category '{category}', using default")
                    item.topics = ["daily_brief"]  # 默认分类
            except Exception as e:
                logger.error(f"Error checking TOPICS: {e}")
                logger.error(f"TOPICS type: {type(TOPICS)}, value: {list(TOPICS.keys()) if hasattr(TOPICS, 'keys') else 'N/A'}")
                raise
        else:
            # 兼容旧的 categories 字段（多个），取第一个
            categories = result.get("categories", [])
            if categories and isinstance(categories, list) and len(categories) > 0:
                try:
                    if categories[0] in TOPICS:
                        item.topics = [categories[0]]
                    else:
                        item.topics = ["daily_brief"]
                except Exception as e:
                    logger.error(f"Error checking TOPICS in categories: {e}")
                    raise
            else:
                item.topics = ["daily_brief"]
