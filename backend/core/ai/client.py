"""
AI Client - 智谱 AI (GLM)
支持 LLM 和 TTS 功能
"""

import os
import logging
from typing import Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class GLMClient:
    """智谱 AI 客户端"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化智谱 AI 客户端
        
        Args:
            api_key: API Key，如果不提供则从环境变量读取
        """
        self.api_key = api_key or os.getenv("GLM_API_KEY")
        if not self.api_key:
            raise ValueError("GLM_API_KEY not found in environment variables")
        
        # 智谱 AI 兼容 OpenAI SDK
        # 官方文档: https://docs.bigmodel.cn/
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/"
        )
        
        # 模型配置：优先 env var，其次 sources.json，最后默认值
        from core.config import load_sources_config
        try:
            ai_config = load_sources_config().get("ai", {})
        except Exception:
            ai_config = {}

        self.model = os.getenv("GLM_MODEL") or ai_config.get("model", "glm-4-flashx")
        self.temperature = float(os.getenv("GLM_TEMPERATURE") or ai_config.get("temperature", 0.3))
        self.max_tokens = int(os.getenv("GLM_MAX_TOKENS") or ai_config.get("max_tokens", 2000))
    
    async def complete(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> tuple[str, int]:
        """
        生成文本补全
        
        Args:
            system: 系统提示词
            user: 用户输入
            temperature: 温度参数（0-1），控制随机性
            max_tokens: 最大生成长度
        
        Returns:
            tuple[str, int]: (生成的文本, 使用的token数)
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens
            )
            
            content = response.choices[0].message.content
            tokens_used = response.usage.total_tokens if response.usage else 0
            
            return content, tokens_used
        
        except Exception as e:
            logger.error(f"GLM API error: {e}")
            raise
    
    async def generate_speech(
        self,
        text: str,
        voice: str = "tongtong",
        speed: float = 1.0,
        response_format: str = "wav"
    ) -> bytes:
        """生成语音（TTS）
        
        Args:
            text: 要转换的文本 (≤1024字符)
            voice: 音色选择 (tongtong/chuichui/xiaochen/jam/kazi/douji/luodo)
            speed: 语速（0.5-2.0）
            response_format: 音频格式 (wav/pcm)，默认wav
        
        Returns:
            bytes: 音频数据（WAV或PCM格式）
        """
        try:
            # 智谱API使用OpenAI SDK兼容接口
            # response_format是标准参数
            response = await self.client.audio.speech.create(
                model="glm-tts",
                voice=voice,
                input=text,
                speed=speed,
                response_format=response_format  # 直接传递，不用extra_body
            )
            
            # OpenAI SDK 返回 HttpxBinaryResponseContent 对象
            # 需要调用 read() 来获取实际的字节数据
            if hasattr(response, 'read'):
                # read() 是同步方法
                audio_data = response.read()
            elif hasattr(response, 'content'):
                audio_data = response.content
            else:
                # 如果是异步迭代器，收集所有数据
                chunks = []
                async for chunk in response.iter_bytes():
                    chunks.append(chunk)
                audio_data = b''.join(chunks)
            
            logger.info(f"Generated audio ({response_format}): {len(audio_data)} bytes")
            return audio_data
            
        except Exception as e:
            logger.error(f"GLM TTS error: {e}")
            raise


# 全局单例
_glm_client: Optional[GLMClient] = None


def get_glm_client() -> GLMClient:
    """获取全局 GLM 客户端实例"""
    global _glm_client
    if _glm_client is None:
        _glm_client = GLMClient()
    return _glm_client


def create_glm_client(api_key: Optional[str] = None) -> GLMClient:
    """创建新的 GLM 客户端实例"""
    return GLMClient(api_key)
