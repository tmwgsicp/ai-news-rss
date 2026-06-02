"""
每日日报生成服务
将多条新闻整合成一篇完整的日报，并保存到数据库
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_news import AggregatedItem
from models.daily_brief import DailyBrief
from models.database import async_session

logger = logging.getLogger(__name__)


class DailyBriefGenerator:
    """每日日报生成器"""
    
    async def generate_and_save_daily_brief(self) -> Optional[DailyBrief]:
        """
        生成今日日报并保存到数据库
        
        Returns:
            Optional[DailyBrief]: 生成的日报对象，失败返回 None
        """
        try:
            from core.config import CST, now_cst, today_cst_str

            async with async_session() as db:
                # 查询今日所有新闻（Pro 用户的全部内容）
                # 使用北京时间（CST）作为"今天"的基准
                now = now_cst()
                today_cst = now.replace(hour=0, minute=0, second=0, microsecond=0)
                today_str = today_cst_str()

                # 检查今日日报是否已存在
                result = await db.execute(
                    select(DailyBrief).where(DailyBrief.date == today_str)
                )
                existing = result.scalar_one_or_none()

                if existing:
                    logger.info(f"Daily brief for {today_str} already exists, updating...")
                    brief = existing
                else:
                    brief = DailyBrief(
                        date=today_str,
                        title="",
                        summary="",
                        total_count=0,
                        sections=[]
                    )
                    db.add(brief)

                # 查询高质量新闻（按评分排序，取前 50 条）
                # 开源版策略：展示数据库中评分最高的内容
                from core.config import get_score_threshold
                score_threshold = get_score_threshold()
                
                items_result = await db.execute(
                    select(AggregatedItem)
                    .where(AggregatedItem.ai_score >= score_threshold)
                    .order_by(AggregatedItem.ai_score.desc(), AggregatedItem.published_at.desc())
                    .limit(50)
                )
                items = items_result.scalars().all()

                if not items:
                    logger.warning(f"No news items found for {today_str}")
                    brief.title = f"AI NewsRSS 日报 - {now.strftime('%Y年%m月%d日')}"
                    brief.summary = "今天暂无新资讯"
                    brief.total_count = 0
                    brief.sections = []
                    await db.commit()
                    await db.refresh(brief)
                    return brief
                
                # 生成日报内容
                brief_data = self._generate_brief_data(items)
                
                # 更新日报记录
                brief.title = brief_data['title']
                brief.summary = brief_data['summary']
                brief.total_count = brief_data['total_count']
                brief.sections = brief_data['sections']
                
                await db.commit()
                await db.refresh(brief)

                # 清除该日期的所有缓存（日报更新后旧缓存失效）
                try:
                    from core.redis_client import cache_delete_pattern
                    await cache_delete_pattern(f"daily_brief:{today_str}:*")
                    await cache_delete_pattern(f"rss_xml:{today_str}:*")
                except ImportError:
                    pass

                logger.info(f"Daily brief generated for {today_str}: {brief.total_count} items, {len(brief.sections)} sections")
                return brief
        
        except Exception as e:
            logger.error(f"Failed to generate daily brief: {e}", exc_info=True)
            return None
    
    def _generate_brief_data(self, items: List[AggregatedItem]) -> Dict:
        """生成日报数据"""
        # 按主题分组
        grouped = self._group_by_topic(items)
        
        # 各板块容量控制 + 单源占比平衡
        # deep_read 上限 8 条，其中任一来源最多占 5 条（60%），保证内容多样性
        # 其他板块上限 10 条
        SECTION_CAPS = {'deep_read': 8, 'daily_brief': 10, 'industry_pulse': 10, 'tool_radar': 10, 'community_voice': 10}
        MAX_SINGLE_SOURCE_RATIO = 0.6
        
        for topic_key, topic_items in grouped.items():
            if not topic_items:
                continue
            cap = SECTION_CAPS.get(topic_key, 10)
            if len(topic_items) <= cap:
                continue
            
            # 按评分排序，然后限制单源占比
            topic_items.sort(key=lambda x: x.ai_score, reverse=True)
            max_per_source = max(2, int(cap * MAX_SINGLE_SOURCE_RATIO))
            
            selected = []
            source_counts = {}
            for item in topic_items:
                src = item.source_type
                cur = source_counts.get(src, 0)
                if cur >= max_per_source:
                    continue
                selected.append(item)
                source_counts[src] = cur + 1
                if len(selected) >= cap:
                    break
            
            if len(selected) < len(topic_items):
                logger.info(f"Section '{topic_key}' capped: {len(topic_items)} -> {len(selected)} (sources: {source_counts})")
            grouped[topic_key] = selected
        
        # 生成各部分内容
        sections = []
        total_count = 0
        
        for topic_key, topic_items in grouped.items():
            if not topic_items:
                continue
            
            section = self._generate_section(topic_key, topic_items)
            if section:
                sections.append(section)
                total_count += len(topic_items)
        
        # 生成日报概述
        summary = self._generate_summary(sections, total_count)
        
        from core.config import now_cst
        return {
            "title": f"AI NewsRSS 日报 - {now_cst().strftime('%Y年%m月%d日')}",
            "summary": summary,
            "total_count": total_count,
            "sections": sections
        }
    
    def _group_by_topic(self, items: List[AggregatedItem]) -> Dict[str, List[AggregatedItem]]:
        """
        按主题分组
        
        注意:
        1. 现在每条新闻通常只有一个主题分类
        2. 为了确保不重复,使用 set 去重(基于 item.id)
        3. 顺序: daily_brief → industry_pulse → community_voice → tool_radar → deep_read
        """
        grouped = {
            'daily_brief': [],
            'industry_pulse': [],
            'community_voice': [],
            'tool_radar': [],
            'deep_read': []
        }
        
        # 使用 set 记录已经分配过的新闻 ID，确保不重复
        seen_ids = set()
        
        for item in items:
            # 跳过已经分配过的新闻
            if item.id in seen_ids:
                continue
            
            # 使用 topics_list 属性（自动解析 JSON）
            item_topics = item.topics_list
            if item_topics and len(item_topics) > 0:
                topic = item_topics[0]  # 只取第一个（也是唯一的）分类
                if topic in grouped:
                    grouped[topic].append(item)
                    seen_ids.add(item.id)
        
        return grouped
    
    def _generate_section(self, topic_key: str, items: List[AggregatedItem]) -> Optional[Dict]:
        """生成单个主题的内容板块"""
        topic_info = {
            'daily_brief': {
                'name': '每日速览',
                'icon': '⚡',
                'description': 'AI 行业每日重要新闻精选'
            },
            'tool_radar': {
                'name': '工具雷达',
                'icon': '🔧',
                'description': '最新 AI 工具和产品发布'
            },
            'industry_pulse': {
                'name': '行业脉搏',
                'icon': '📈',
                'description': 'AI 行业趋势和深度分析'
            },
            'deep_read': {
                'name': '深度阅读',
                'icon': '📚',
                'description': '技术论文和研究成果'
            },
            'community_voice': {
                'name': '社区声音',
                'icon': '💬',
                'description': 'Reddit/HackerNews 热门讨论'
            }
        }
        
        if topic_key not in topic_info:
            return None
        
        info = topic_info[topic_key]
        
        # 生成板块摘要（基于前3条新闻）
        top_items = sorted(items, key=lambda x: x.ai_score, reverse=True)[:3]
        highlights = [item.title for item in top_items]
        
        return {
            "topic_key": topic_key,
            "topic_name": info['name'],
            "topic_icon": info['icon'],
            "topic_description": info['description'],
            "count": len(items),
            "highlights": highlights,
            "items": [
                {
                    "id": item.id,
                    "title": item.title,
                    "summary": item.ai_summary,
                    "url": item.url,
                    "source": item.source_name,
                    "source_type": item.source_type,
                    "score": item.ai_score,
                    "published_at": int(item.published_at.timestamp()) if item.published_at else 0,
                    # 双链接支持: 社区讨论链接(如果存在)
                    "discussion_url": item.metadata_dict.get("discussion_url") if item.metadata_dict else None,
                    # 用于 TTS 和邮件
                    "categories": item.topics_list
                }
                for item in sorted(items, key=lambda x: x.ai_score, reverse=True)
            ]
        }
    
    def _generate_summary(self, sections: List[Dict], total_count: int) -> str:
        """生成日报总体摘要"""
        if not sections:
            return "今天暂无新资讯"
        
        summary_parts = []
        for section in sections:
            summary_parts.append(f"{section['topic_icon']} {section['topic_name']}：{section['count']} 条")
        
        return f"今日共精选 {total_count} 条 AI 资讯，包含 " + "、".join(summary_parts)


# 全局单例
daily_brief_generator = DailyBriefGenerator()
