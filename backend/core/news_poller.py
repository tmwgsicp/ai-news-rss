"""
AI 新闻轮询器 - 开源版（简化）
每天固定时间执行聚合任务
"""

import asyncio
import logging
from datetime import datetime, timedelta

from core.config import config

logger = logging.getLogger(__name__)


class NewsPoller:
    """AI 新闻轮询器"""
    
    _task = None
    _running = False
    
    async def start_scheduled(self, hour: int = 7, minute: int = 30):
        """
        启动每日定时聚合
        
        Args:
            hour: 聚合时间（小时，0-23）
            minute: 聚合时间（分钟，0-59）
        """
        if self._running:
            logger.warning("NewsPoller already running")
            return
        
        self._running = True
        self._hour = hour
        self._minute = minute
        
        self._task = asyncio.create_task(self._loop_daily())
        logger.info(f"NewsPoller started: daily at {hour:02d}:{minute:02d}")
    
    async def stop(self):
        """停止轮询器"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("NewsPoller stopped")
    
    async def _loop_daily(self):
        """每日定时循环"""
        skip_initial = config.get_runtime("skip_initial_run", True)
        
        while self._running:
            try:
                now = datetime.now()
                target = now.replace(hour=self._hour, minute=self._minute, second=0, microsecond=0)
                
                # 如果今天的时间已过，调到明天
                if now >= target:
                    target += timedelta(days=1)
                
                sleep_seconds = (target - now).total_seconds()
                
                # 首次启动时立即执行一次（除非配置了跳过）
                if not skip_initial:
                    logger.info("Initial run: executing aggregation immediately")
                    await self._run_aggregation()
                    config.set_runtime("skip_initial_run", True)
                
                logger.info(f"Next aggregation: {target.strftime('%Y-%m-%d %H:%M:%S')} (in {sleep_seconds/3600:.1f}h)")
                await asyncio.sleep(sleep_seconds)
                
                # 执行聚合
                await self._run_aggregation()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Daily loop error: {e}", exc_info=True)
                await asyncio.sleep(3600)
    
    async def _run_aggregation(self):
        """执行聚合流程"""
        import time as time_module
        start_time = time_module.time()
        
        try:
            logger.info("="*70)
            logger.info("开始新闻聚合...")
            logger.info("="*70)
            
            # 发送开始通知
            from core.webhook_notifier import webhook_notifier
            await webhook_notifier.notify_aggregation_start()
            
            # 1. 聚合新闻
            from core.aggregator import AINewsAggregator
            aggregator = AINewsAggregator()
            await aggregator.aggregate_and_save()
            
            # 2. 生成日报
            daily_brief = await self._generate_daily_brief()
            
            # 3. 生成 TTS（可选）
            if config.tts_enabled and daily_brief:
                await self._generate_tts()
            
            # 计算耗时
            duration = int(time_module.time() - start_time)
            
            # 4. 发送完成通知
            if daily_brief:
                from core.webhook_notifier import webhook_notifier
                await webhook_notifier.notify_aggregation_complete(
                    total_items=daily_brief.total_count,
                    sources="HackerNews, Reddit, GitHub, Arxiv, RSS",
                    duration_seconds=duration
                )
                
                # 5. 发送邮件通知（如果配置了）
                from core.email_service import email_service
                if email_service.is_configured() and config.notification_email:
                    web_url = f"{config.rss_base_url}"
                    email_service.send_daily_brief_notification(
                        to_email=config.notification_email,
                        brief_date=daily_brief.date,
                        total_count=daily_brief.total_count,
                        web_url=web_url
                    )
            
            logger.info("="*70)
            logger.info(f"新闻聚合完成！耗时 {duration} 秒")
            logger.info("="*70)
            
        except Exception as e:
            logger.error(f"Aggregation failed: {e}", exc_info=True)
            
            # 发送失败通知
            from core.webhook_notifier import webhook_notifier
            await webhook_notifier.notify_aggregation_failed(str(e))
    
    async def _generate_daily_brief(self):
        """生成日报"""
        try:
            from core.daily_brief_generator import DailyBriefGenerator
            
            generator = DailyBriefGenerator()
            brief = await generator.generate_and_save_daily_brief()
            
            if brief:
                logger.info(f"Daily brief generated: {brief.date}, {brief.total_count} items")
                
                # 发送日报生成通知
                from core.webhook_notifier import webhook_notifier
                await webhook_notifier.notify_daily_brief_generated(
                    date=brief.date,
                    total_count=brief.total_count,
                    sections_count=len(brief.sections)
                )
                return brief
            else:
                logger.warning("Failed to generate daily brief")
                return None
        
        except Exception as e:
            logger.error(f"Failed to generate daily brief: {e}", exc_info=True)
            return None
    
    async def _generate_tts(self):
        """生成 TTS 语音（可选）"""
        try:
            from core.tts_service import TTSService
            from models.database import async_session
            from models.daily_brief import DailyBrief
            from sqlalchemy import select
            
            # 获取今日日报
            today_str = datetime.now().strftime('%Y-%m-%d')
            
            async with async_session() as db:
                result = await db.execute(
                    select(DailyBrief).where(DailyBrief.date == today_str)
                )
                daily_brief = result.scalar_one_or_none()
            
            if not daily_brief:
                logger.warning("No daily brief found for TTS generation")
                return
            
            # 生成 TTS
            logger.info("Generating TTS...")
            tts_service = TTSService()
            audio_path = await tts_service.generate_from_daily_brief(daily_brief)
            
            if audio_path:
                # 更新日报的音频路径
                async with async_session() as db:
                    result = await db.execute(
                        select(DailyBrief).where(DailyBrief.date == today_str)
                    )
                    brief = result.scalar_one_or_none()
                    if brief:
                        brief.audio_path = audio_path
                        await db.commit()
                logger.info(f"TTS generated: {audio_path}")
                
                # 发送 TTS 生成通知
                from core.webhook_notifier import webhook_notifier
                await webhook_notifier.notify_tts_generated(audio_path)
            else:
                logger.warning("TTS generation failed")
        
        except Exception as e:
            logger.error(f"TTS generation error: {e}", exc_info=True)


# 全局实例
news_poller = NewsPoller()
