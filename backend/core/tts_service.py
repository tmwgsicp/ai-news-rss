"""
TTS 语音播报服务
使用 MiniMax 异步TTS（支持10万字符长文本）

特性：
- 文件去重：已存在的音频不重复生成
- 失败重试：最多重试 3 次，指数退避
- 管理员告警：生成失败时发送邮件通知
- 余额预警：检测到余额不足相关错误时特别提醒
"""

import logging
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.ai.minimax_tts import get_minimax_client

logger = logging.getLogger(__name__)

# TTS 生成失败的常见错误关键词（可能与余额不足相关）
BALANCE_ERROR_KEYWORDS = [
    "insufficient", "balance", "quota", "limit", "exceeded",
    "余额", "配额", "欠费", "充值", "payment",
]


class TTSService:
    """TTS 语音播报服务"""

    def __init__(self):
        self.output_dir = Path(os.getenv("AUDIO_OUTPUT_DIR", "./data/audio"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.enabled = os.getenv("TTS_ENABLED", "false").lower() in ("true", "1")
        self.max_retries = int(os.getenv("TTS_MAX_RETRIES", "3"))

    async def generate_from_daily_brief(self, daily_brief) -> Optional[str]:
        """
        从每日日报生成语音播报

        Args:
            daily_brief: DailyBrief 对象（来自数据库）

        Returns:
            Optional[str]: 生成的音频文件路径，失败返回 None
        """
        if not self.enabled:
            logger.info("TTS is disabled, skipping audio generation")
            return None

        if not daily_brief or not daily_brief.sections:
            logger.warning("No daily brief or sections for TTS generation")
            return None

        date_str = daily_brief.date.replace('-', '')
        output_file = self.output_dir / f"daily_brief_{date_str}.mp3"

        if output_file.exists():
            logger.info(f"TTS audio exists: {output_file} ({output_file.stat().st_size:,} bytes), will overwrite with fresh content")

        try:
            from datetime import datetime as dt
            brief_date = dt.strptime(daily_brief.date, "%Y-%m-%d")

            # 优先尝试 AI 生成播报文稿
            full_script = None
            from core.ai.audio_script import generate_ai_broadcast_script
            try:
                full_script = await generate_ai_broadcast_script(
                    daily_brief.sections, brief_date
                )
                if full_script:
                    logger.info(f"AI broadcast script ready: {len(full_script)} chars")
            except Exception as e:
                logger.warning(f"AI broadcast script failed, falling back to template: {e}")

            # Fallback：模板拼接
            if not full_script:
                news_items_dict = []
                category_order = []
                for section in daily_brief.sections:
                    topic_key = section.get('topic_key', '')
                    if topic_key and topic_key not in category_order:
                        category_order.append(topic_key)
                    for item in section.get('items', []):
                        news_items_dict.append({
                            'title': item['title'],
                            'summary': item['summary'],
                            'score': item['score'],
                            'categories': item.get('categories', [topic_key])
                        })

                if not news_items_dict:
                    logger.warning("No news items in daily brief for TTS")
                    return None

                from core.ai.audio_script import generate_daily_audio_script
                full_script = generate_daily_audio_script(
                    news_items_dict, brief_date, category_order=category_order
                )
                logger.info(f"Template TTS script ready: {len(full_script)} chars")

            # 带重试的 TTS 生成
            audio_path = await self._generate_with_retry(full_script, output_file)

            if audio_path:
                logger.info(f"TTS audio generated: {audio_path}")
                return audio_path
            else:
                # 生成失败，发送管理员告警
                await self._alert_admin(
                    f"TTS 生成失败",
                    f"日期: {daily_brief.date}\n"
                    f"新闻条数: {len(news_items_dict)}\n"
                    f"文稿长度: {len(full_script)} 字符\n"
                    f"已重试 {self.max_retries} 次均失败，请检查 MiniMax API 状态和余额。"
                )
                return None

        except Exception as e:
            error_msg = str(e)
            logger.error(f"TTS generation error: {e}", exc_info=True)

            # 检查是否可能是余额不足
            is_balance_issue = any(kw in error_msg.lower() for kw in BALANCE_ERROR_KEYWORDS)
            if is_balance_issue:
                await self._alert_admin(
                    "⚠️ MiniMax TTS 疑似余额不足",
                    f"日期: {daily_brief.date}\n"
                    f"错误信息: {error_msg}\n\n"
                    f"请尽快登录 MiniMax 控制台检查余额并充值：\n"
                    f"https://platform.minimax.com/",
                    is_balance_issue=True
                )
            else:
                await self._alert_admin(
                    f"TTS 生成异常",
                    f"日期: {daily_brief.date}\n"
                    f"错误类型: {type(e).__name__}\n"
                    f"错误信息: {error_msg}"
                )
            return None

    async def _generate_with_retry(self, script: str, output_file: Path) -> Optional[str]:
        """
        带重试机制的 TTS 生成

        Args:
            script: 语音文稿
            output_file: 输出文件路径

        Returns:
            Optional[str]: 成功返回文件路径，失败返回 None
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"TTS generation attempt {attempt}/{self.max_retries}")

                client = get_minimax_client()
                audio_path = await client.generate_speech(
                    text=script,
                    output_path=output_file,
                    voice_id="audiobook_male_1",
                    max_wait_seconds=300
                )

                if audio_path:
                    return audio_path

                last_error = "generate_speech returned None"
                logger.warning(f"TTS attempt {attempt} returned None")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"TTS attempt {attempt} failed: {e}")

                # 检查是否为余额不足类错误，不需要重试
                if any(kw in str(e).lower() for kw in BALANCE_ERROR_KEYWORDS):
                    logger.error("Detected possible balance issue, stopping retries")
                    break

            # 指数退避：10s, 30s, 60s
            if attempt < self.max_retries:
                wait = min(10 * (2 ** (attempt - 1)), 60)
                logger.info(f"Retrying in {wait}s...")
                await asyncio.sleep(wait)

        logger.error(f"TTS generation failed after {self.max_retries} attempts. Last error: {last_error}")
        return None

    async def _alert_admin(self, title: str, message: str, is_balance_issue: bool = False):
        """
        发送管理员告警（通过 webhook，如企业微信群机器人）

        Args:
            title: 告警标题
            message: 告警内容
            is_balance_issue: 是否为余额不足相关问题
        """
        try:
            from core.webhook_notifier import webhook_notifier as webhook
            event = "tts_balance_warning" if is_balance_issue else "tts_generation_failed"
            await webhook.notify(event, {
                "标题": title,
                "详情": message,
            })
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")


# 全局单例
tts_service = TTSService()
