"""
新闻查询接口 - 开源版（简化）
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, desc

from models.database import async_session
from models.ai_news import AggregatedItem

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/news/{news_id}")
async def get_news_detail(news_id: int):
    """
    获取新闻详情
    
    Args:
        news_id: 新闻 ID
    """
    try:
        async with async_session() as db:
            result = await db.execute(
                select(AggregatedItem).where(AggregatedItem.id == news_id)
            )
            news = result.scalar_one_or_none()
            
            if not news:
                raise HTTPException(status_code=404, detail="新闻不存在")
            
            return {
                "id": news.id,
                "title": news.title,
                "url": news.url,
                "summary": news.ai_summary,
                "content": news.content,
                "source": news.source_name,
                "score": news.ai_score,
                "published_at": news.published_at.isoformat() if news.published_at else None,
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取新闻详情失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/news")
async def list_news(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
):
    """
    新闻列表
    
    Args:
        limit: 返回数量
        offset: 偏移量
    """
    try:
        async with async_session() as db:
            result = await db.execute(
                select(AggregatedItem)
                .order_by(desc(AggregatedItem.published_at))
                .limit(limit)
                .offset(offset)
            )
            news_list = result.scalars().all()
            
            return {
                "items": [
                    {
                        "id": news.id,
                        "title": news.title,
                        "url": news.url,
                        "summary": news.ai_summary,
                        "source": news.source_name,
                        "score": news.ai_score,
                        "published_at": news.published_at.isoformat() if news.published_at else None,
                    }
                    for news in news_list
                ],
                "total": len(news_list)
            }
    
    except Exception as e:
        logger.error(f"获取新闻列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
