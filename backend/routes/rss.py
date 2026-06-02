"""
RSS 订阅路由 - 开源版（简化）
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from sqlalchemy import select

from models.database import async_session
from models.daily_brief import DailyBrief
from core.config import config

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/rss/daily.xml")
async def get_daily_rss():
    """
    获取 RSS 订阅（最近7天的日报）
    
    Returns:
        XML 格式的 RSS feed
    """
    try:
        async with async_session() as db:
            # 获取最近7天的日报
            result = await db.execute(
                select(DailyBrief)
                .order_by(DailyBrief.date.desc())
                .limit(7)
            )
            briefs = result.scalars().all()
            
            # 生成 RSS XML
            xml = generate_rss_xml(briefs)
            
            return Response(content=xml, media_type="application/xml; charset=utf-8")
    
    except Exception as e:
        logger.error(f"生成 RSS 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def generate_rss_xml(briefs: list) -> str:
    """
    生成 RSS XML
    
    Args:
        briefs: DailyBrief 列表
    
    Returns:
        RSS XML 字符串
    """
    from html import escape as html_escape
    
    rss_title = config.rss_title
    rss_description = config.rss_description
    rss_base_url = config.rss_base_url
    build_date = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    
    items_xml = ""
    
    for brief in briefs:
        # 构建 HTML 描述
        sections_html = ""
        for section in brief.sections:
            topic_name = section.get('topic_name', '')
            topic_icon = section.get('topic_icon', '📄')
            items = section.get('items', [])
            
            items_html = ""
            for item in items:
                items_html += f"""
                <div style="background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 20px; margin-bottom: 16px;">
                    <div style="display: flex; gap: 12px; margin-bottom: 12px; font-size: 12px; color: #6b7280;">
                        <span style="font-weight: 500;">{html_escape(item.get('source', ''))}</span>
                        <span>·</span>
                        <span style="color: #1890ff; font-weight: 600;">评分 {item.get('score', 0):.1f}</span>
                    </div>
                    <h4 style="margin: 0 0 8px 0; font-size: 16px; font-weight: 600; color: #111827;">
                        <a href="{html_escape(item.get('url', ''))}" style="color: #111827; text-decoration: none;">{html_escape(item.get('title', ''))}</a>
                    </h4>
                    <p style="color: #4b5563; font-size: 14px; line-height: 1.6; margin: 0;">
                        {html_escape(item.get('summary', ''))}
                    </p>
                </div>
                """
            
            sections_html += f"""
            <div style="margin-bottom: 32px;">
                <h3 style="font-size: 18px; font-weight: 700; color: #262626; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 2px solid #f0f0f0;">
                    {topic_icon} {html_escape(topic_name)}
                </h3>
                {items_html}
            </div>
            """
        
        description = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; line-height: 1.6;">
            <div style="background: #e8f4fd; border-left: 4px solid #1890ff; padding: 16px; margin-bottom: 24px; border-radius: 6px;">
                <p style="color: #333; font-size: 14px; margin: 0;">
                    {html_escape(brief.summary)}
                </p>
            </div>
            {sections_html}
        </div>
        """
        
        pub_date = brief.created_at.strftime('%a, %d %b %Y %H:%M:%S GMT') if brief.created_at else build_date
        
        items_xml += f"""
        <item>
            <title>{html_escape(brief.title)}</title>
            <link>{rss_base_url}/</link>
            <description><![CDATA[{description}]]></description>
            <pubDate>{pub_date}</pubDate>
            <guid isPermaLink="false">ainewsrss-{brief.date}</guid>
        </item>
        """
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{html_escape(rss_title)}</title>
    <link>{rss_base_url}</link>
    <description>{html_escape(rss_description)}</description>
    <language>zh-CN</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{rss_base_url}/rss/daily.xml" rel="self" type="application/rss+xml"/>
    {items_xml}
  </channel>
</rss>"""
    
    return xml
