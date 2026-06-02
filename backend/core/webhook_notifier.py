#!/usr/bin/env python3
"""
Webhook 通知模块 - 开源版
支持企业微信、钉钉等 Webhook 通知
"""

import httpx
import time
import logging
from typing import Optional, Dict
from datetime import datetime

from core.config import config

logger = logging.getLogger(__name__)

# 事件标签映射
EVENT_LABELS = {
    "aggregation_start": "新闻聚合开始",
    "aggregation_complete": "新闻聚合完成",
    "aggregation_failed": "新闻聚合失败",
    "daily_brief_generated": "日报生成完成",
    "tts_generated": "TTS 生成完成",
}


class WebhookNotifier:
    """Webhook 通知器"""
    
    def __init__(self):
        self._last_notification: Dict[str, float] = {}
        self._notification_interval = 300  # 5分钟内相同事件不重复通知
    
    @property
    def webhook_url(self) -> str:
        """获取 Webhook URL"""
        return config.get_env("WEBHOOK_URL", "").strip()
    
    @property
    def enabled(self) -> bool:
        """检查是否启用 Webhook"""
        return bool(self.webhook_url)
    
    def _is_wecom(self, url: str) -> bool:
        """判断是否为企业微信 Webhook"""
        return "qyapi.weixin.qq.com" in url
    
    def _is_dingtalk(self, url: str) -> bool:
        """判断是否为钉钉 Webhook"""
        return "oapi.dingtalk.com" in url
    
    def _build_payload(self, url: str, event: str, data: Dict) -> dict:
        """
        根据 Webhook 类型构造消息体
        
        Args:
            url: Webhook URL
            event: 事件类型
            data: 事件数据
        
        Returns:
            dict: 消息体
        """
        label = EVENT_LABELS.get(event, event)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构造消息内容
        lines = [f"**{label}**", f"> {ts}"]
        for k, v in (data or {}).items():
            if v is not None:
                lines.append(f"> {k}: {v}")
        
        content = "\n".join(lines)
        
        # 企业微信格式
        if self._is_wecom(url):
            return {
                "msgtype": "markdown",
                "markdown": {"content": content},
            }
        
        # 钉钉格式
        if self._is_dingtalk(url):
            return {
                "msgtype": "markdown",
                "markdown": {
                    "title": label,
                    "text": content
                }
            }
        
        # 通用格式
        return {
            "event": event,
            "timestamp": int(time.time()),
            "timestamp_str": ts,
            "message": content,
            "data": data or {},
        }
    
    async def notify(self, event: str, data: Optional[Dict] = None) -> bool:
        """
        发送 Webhook 通知
        
        Args:
            event: 事件类型
            data: 事件数据
        
        Returns:
            bool: 是否发送成功
        """
        url = self.webhook_url
        if not url:
            logger.debug("Webhook not configured, skip notification")
            return False
        
        # 防止短时间内重复通知
        now = time.time()
        last = self._last_notification.get(event, 0)
        if now - last < self._notification_interval:
            logger.debug(
                f"Skip duplicate webhook: {event} ({int(now - last)}s since last)"
            )
            return False
        
        # 构造消息体
        payload = self._build_payload(url, event, data or {})
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                
                # 检查响应
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    body = resp.json()
                    errcode = body.get("errcode", 0)
                    if errcode != 0:
                        errmsg = body.get("errmsg", "unknown")
                        logger.error(f"Webhook errcode={errcode}: {errmsg}")
                        return False
            
            self._last_notification[event] = now
            logger.info(f"Webhook sent: {event}")
            return True
        
        except Exception as e:
            logger.error(f"Webhook failed: {event} - {e}")
            return False
    
    async def notify_aggregation_start(self) -> bool:
        """通知：新闻聚合开始"""
        return await self.notify("aggregation_start", {
            "状态": "开始抓取新闻"
        })
    
    async def notify_aggregation_complete(
        self,
        total_items: int,
        sources: str,
        duration_seconds: int
    ) -> bool:
        """通知：新闻聚合完成"""
        return await self.notify("aggregation_complete", {
            "新闻总数": total_items,
            "信息源": sources,
            "耗时": f"{duration_seconds}秒"
        })
    
    async def notify_aggregation_failed(self, error: str) -> bool:
        """通知：新闻聚合失败"""
        return await self.notify("aggregation_failed", {
            "错误": error
        })
    
    async def notify_daily_brief_generated(
        self,
        date: str,
        total_count: int,
        sections_count: int
    ) -> bool:
        """通知：日报生成完成"""
        return await self.notify("daily_brief_generated", {
            "日期": date,
            "新闻数": total_count,
            "版块数": sections_count
        })
    
    async def notify_tts_generated(self, audio_path: str) -> bool:
        """通知：TTS 生成完成"""
        return await self.notify("tts_generated", {
            "音频文件": audio_path
        })


# 全局实例
webhook_notifier = WebhookNotifier()
