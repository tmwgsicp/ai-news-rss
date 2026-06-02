"""
MiniMax TTS Client - 异步语音合成
支持长文本（最长50,000字符）

参考文档: https://platform.minimax.com/docs/llms.txt
支持模型: speech-2.8-hd, speech-2.6-hd, speech-2.8-turbo, speech-2.6-turbo, speech-02-hd, speech-02-turbo
支持40+语言,包括中文、粤语、英语等
"""

import os
import logging
import asyncio
import httpx
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class MiniMaxTTSClient:
    """MiniMax 异步语音合成客户端"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY")
        if not self.api_key:
            raise ValueError("MINIMAX_API_KEY not found")
        
        self.base_url = "https://api.minimaxi.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def create_tts_task(
        self,
        text: str,
        voice_id: str = "audiobook_male_1",
        model: str = "speech-2.8-turbo",
        speed: float = 1.0,
        volume: float = 1.0,
        pitch: int = 0,
        audio_format: str = "mp3",
        sample_rate: int = 32000,
        bitrate: int = 128000,
        language_boost: str = "auto"
    ) -> Optional[str]:
        """创建异步TTS任务
        
        Args:
            text: 待合成文本（最长50,000字符）
            voice_id: 音色ID,如 audiobook_male_1
            model: 模型选择 (speech-2.8-hd/turbo, speech-2.6-hd/turbo, speech-02-hd/turbo)
            speed: 语速 (0.5-2.0)
            volume: 音量 (0-10)
            pitch: 音调 (-12 to 12)
            audio_format: 输出格式 (mp3/wav/flac)
            sample_rate: 采样率
            bitrate: 比特率
            language_boost: 语言增强 (auto/Chinese/English等)
            
        Returns:
            task_id: 任务ID（字符串）
        """
        try:
            url = f"{self.base_url}/t2a_async_v2"
            
            # 按照官方文档构建请求体
            payload = {
                "model": model,
                "text": text,
                "voice_setting": {
                    "voice_id": voice_id,
                    "speed": speed,
                    "vol": volume,
                    "pitch": pitch
                },
                "audio_setting": {
                    "audio_sample_rate": sample_rate,
                    "bitrate": bitrate,
                    "format": audio_format,
                    "channel": 2
                }
            }
            
            # 添加 language_boost（如果不是 null）
            if language_boost:
                payload["language_boost"] = language_boost
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                
                # 检查是否成功
                base_resp = result.get("base_resp", {})
                if base_resp.get("status_code") != 0:
                    logger.error(f"API error: {base_resp.get('status_msg')}")
                    logger.error(f"Full response: {result}")
                    logger.error(f"Request payload: {payload}")
                    return None
                
                task_id = result.get("task_id")
                
                if not task_id:
                    logger.error(f"No task_id in response: {result}")
                    return None
                
                logger.info(f"TTS task created: {task_id}")
                return str(task_id)
        
        except Exception as e:
            logger.error(f"Failed to create TTS task: {e}")
            return None
    
    async def query_task_status(self, task_id: str) -> Dict[str, Any]:
        """查询任务状态"""
        try:
            url = f"{self.base_url}/query/t2a_async_query_v2"
            params = {"task_id": task_id}
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                return response.json()
        
        except Exception as e:
            logger.error(f"Failed to query task status: {e}")
            return {"status": "Failed", "error": str(e)}
    
    async def download_audio(self, file_id: str, output_path: Path) -> bool:
        """下载生成的音频文件"""
        try:
            url = f"{self.base_url}/files/retrieve_content"
            params = {"file_id": file_id}
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                
                # 保存文件
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Audio downloaded: {output_path} ({len(response.content)} bytes)")
                return True
        
        except Exception as e:
            logger.error(f"Failed to download audio: {e}")
            return False
    
    async def generate_speech(
        self,
        text: str,
        output_path: Path,
        voice_id: str = "audiobook_male_1",
        model: str = "speech-2.8-turbo",
        max_wait_seconds: int = 300
    ) -> Optional[str]:
        """生成语音（完整流程）
        
        完整流程:
        1. 创建TTS任务
        2. 轮询查询任务状态
        3. 任务完成后下载音频文件
        
        Args:
            text: 待合成文本
            output_path: 输出文件路径
            voice_id: 音色ID
            model: 使用的模型
            max_wait_seconds: 最大等待时间（秒）
            
        Returns:
            成功返回音频文件路径,失败返回None
        """
        # 1. 创建任务
        task_id = await self.create_tts_task(text, voice_id=voice_id, model=model)
        if not task_id:
            return None
        
        # 2. 轮询任务状态
        start_time = asyncio.get_event_loop().time()
        check_interval = 2
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_seconds:
                logger.error(f"Task timeout after {max_wait_seconds}s")
                return None
            
            result = await self.query_task_status(task_id)
            status = result.get("status")
            
            if status == "Success":
                file_id = result.get("file_id")
                audio_duration = result.get("audio_duration", 0)
                audio_size = result.get("audio_size", 0)
                
                logger.info(f"Task completed: duration={audio_duration}s, size={audio_size} bytes")
                
                # 3. 下载音频
                if await self.download_audio(str(file_id), output_path):
                    return str(output_path)
                else:
                    return None
            
            elif status == "Failed":
                error_msg = result.get("error", "Unknown error")
                logger.error(f"Task failed: {error_msg}")
                return None
            
            elif status == "Processing":
                logger.info(f"Task processing... ({elapsed:.1f}s elapsed)")
                await asyncio.sleep(check_interval)
                check_interval = min(check_interval + 1, 10)
            
            else:
                logger.warning(f"Unknown status: {status}")
                await asyncio.sleep(check_interval)


# 全局单例
_minimax_client: Optional[MiniMaxTTSClient] = None


def get_minimax_client() -> MiniMaxTTSClient:
    """获取全局 MiniMax 客户端实例"""
    global _minimax_client
    if _minimax_client is None:
        _minimax_client = MiniMaxTTSClient()
    return _minimax_client
