"""
每日 AI 新闻日报接口 - 开源版（简化）
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from models.database import async_session
from models.daily_brief import DailyBrief

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/daily/latest")
async def get_latest_brief():
    """获取最新日报"""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(DailyBrief)
                .order_by(DailyBrief.date.desc())
                .limit(1)
            )
            brief = result.scalar_one_or_none()
            
            if not brief:
                return {
                    "error": "暂无日报数据",
                    "message": "系统正在首次抓取新闻，请稍后刷新"
                }
            
            return brief.to_dict()
    
    except Exception as e:
        logger.error(f"获取最新日报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/daily/list")
async def list_briefs(
    limit: int = Query(10, ge=1, le=30, description="返回数量"),
    offset: int = Query(0, ge=0, description="偏移量")
):
    """获取日报列表"""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(DailyBrief)
                .order_by(DailyBrief.date.desc())
                .limit(limit)
                .offset(offset)
            )
            briefs = result.scalars().all()
            
            return {
                "items": [brief.to_dict() for brief in briefs],
                "total": len(briefs)
            }
    
    except Exception as e:
        logger.error(f"获取日报列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/daily/{date}")
async def get_brief_by_date(date: str):
    """
    获取指定日期的日报

    Args:
        date: 日期，格式 YYYY-MM-DD
    """
    try:
        async with async_session() as db:
            result = await db.execute(
                select(DailyBrief).where(DailyBrief.date == date)
            )
            brief = result.scalar_one_or_none()
            
            if not brief:
                raise HTTPException(status_code=404, detail=f"未找到日期 {date} 的日报")
            
            return brief.to_dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取日报失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/daily/audio/{date}.mp3")
async def get_daily_audio(date: str):
    """
    获取日报音频文件

    Args:
        date: 日期，格式 YYYY-MM-DD
    """
    from fastapi.responses import FileResponse
    from pathlib import Path
    
    date_filename = date.replace('-', '')
    audio_file = Path("data/audio") / f"daily_brief_{date_filename}.mp3"
    
    if not audio_file.exists():
        raise HTTPException(status_code=404, detail="音频文件不存在")
    
    return FileResponse(
        str(audio_file),
        media_type="audio/mpeg",
        filename=f"daily_brief_{date}.mp3"
    )
