#!/usr/bin/env python3
"""
配置管理模块
分离静态配置（.env）和运行时状态（data/runtime.json）
"""

import os
import json
from pathlib import Path
from typing import Any, Optional
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# 北京时间（UTC+8）
CST = timezone(timedelta(hours=8))


def now_cst() -> datetime:
    """获取当前北京时间（timezone-aware）"""
    return datetime.now(CST)


def today_cst_str() -> str:
    """获取今日北京时间日期字符串 YYYY-MM-DD"""
    return now_cst().strftime('%Y-%m-%d')

class Config:
    """配置管理单例"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 项目根目录
        self.base_dir = Path(__file__).parent.parent.parent
        
        # 加载 .env 文件（仅在开发环境，Docker 会直接传入环境变量）
        env_file = self.base_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
        
        # 数据目录
        self.data_dir = Path(os.getenv("DATA_DIR", "./data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "audio").mkdir(exist_ok=True)
        
        # 运行时配置文件（可写）
        self.runtime_config_file = self.data_dir / "runtime.json"
        
        # 加载运行时配置
        self._runtime_config = self._load_runtime_config()
        
        self._initialized = True
    
    def _load_runtime_config(self) -> dict:
        """加载运行时配置"""
        if self.runtime_config_file.exists():
            try:
                with open(self.runtime_config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}
    
    def _save_runtime_config(self):
        """保存运行时配置"""
        try:
            with open(self.runtime_config_file, 'w', encoding='utf-8') as f:
                json.dump(self._runtime_config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] 保存运行时配置失败: {e}")
    
    # ==================== 静态配置（来自 .env，只读）====================
    
    @property
    def glm_api_key(self) -> str:
        return os.getenv("GLM_API_KEY", "")
    
    @property
    def glm_model(self) -> str:
        return os.getenv("GLM_MODEL", "glm-4-flashx")
    
    @property
    def glm_temperature(self) -> float:
        return float(os.getenv("GLM_TEMPERATURE", "0.3"))
    
    @property
    def port(self) -> int:
        return int(os.getenv("PORT", "8000"))
    
    @property
    def host(self) -> str:
        return os.getenv("HOST", "0.0.0.0")
    
    @property
    def debug(self) -> bool:
        return os.getenv("DEBUG", "false").lower() == "true"
    
    @property
    def poller_mode(self) -> str:
        return os.getenv("POLLER_MODE", "daily")
    
    @property
    def poller_hour(self) -> int:
        return int(os.getenv("POLLER_HOUR", "7"))
    
    @property
    def poller_minute(self) -> int:
        return int(os.getenv("POLLER_MINUTE", "30"))
    
    @property
    def reddit_client_id(self) -> str:
        return os.getenv("REDDIT_CLIENT_ID", "")
    
    @property
    def reddit_client_secret(self) -> str:
        return os.getenv("REDDIT_CLIENT_SECRET", "")
    
    @property
    def github_access_token(self) -> str:
        return os.getenv("GITHUB_ACCESS_TOKEN", "")
    
    @property
    def tts_enabled(self) -> bool:
        return os.getenv("TTS_ENABLED", "false").lower() == "true"
    
    @property
    def minimax_api_key(self) -> str:
        return os.getenv("MINIMAX_API_KEY", "")
    
    @property
    def rss_title(self) -> str:
        return os.getenv("RSS_TITLE", "AI News RSS")
    
    @property
    def rss_description(self) -> str:
        return os.getenv("RSS_DESCRIPTION", "AI 行业新闻聚合")
    
    @property
    def rss_base_url(self) -> str:
        return os.getenv("RSS_BASE_URL", "http://localhost:8000")
    
    @property
    def database_url(self) -> str:
        db_path = self.data_dir / "ainewsrss.db"
        return os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    
    @property
    def webhook_url(self) -> str:
        return os.getenv("WEBHOOK_URL", "")
    
    @property
    def webhook_notification_interval(self) -> int:
        return int(os.getenv("WEBHOOK_NOTIFICATION_INTERVAL", "300"))
    
    @property
    def notification_email(self) -> str:
        return os.getenv("NOTIFICATION_EMAIL", "")
    
    def get_env(self, key: str, default: str = "") -> str:
        """获取环境变量（通用方法）"""
        return os.getenv(key, default)
    
    # ==================== 运行时状态（可写）====================
    
    def get_runtime(self, key: str, default: Any = None) -> Any:
        return self._runtime_config.get(key, default)
    
    def set_runtime(self, key: str, value: Any):
        self._runtime_config[key] = value
        self._save_runtime_config()
    
    def update_runtime(self, updates: dict):
        self._runtime_config.update(updates)
        self._save_runtime_config()
    
    # ==================== 验证 ====================
    
    def validate(self) -> list[str]:
        """验证配置，返回错误列表"""
        errors = []
        
        if not self.glm_api_key:
            errors.append("GLM_API_KEY 未配置，AI 分析功能将无法使用")
        
        return errors
    
    def print_config(self):
        """打印当前配置（脱敏）"""
        print("📋 当前配置:")
        print(f"   - GLM API Key: {'✅ 已配置' if self.glm_api_key else '❌ 未配置'}")
        print(f"   - GLM Model: {self.glm_model}")
        print(f"   - Port: {self.port}")
        print(f"   - Poller Time: {self.poller_hour:02d}:{self.poller_minute:02d}")
        print(f"   - TTS Enabled: {self.tts_enabled}")
        print(f"   - Data Dir: {self.data_dir}")
        print(f"   - Database: {self.database_url}")


# 全局单例
config = Config()


# ==================== 辅助函数 ====================

def load_sources_config() -> dict:
    """
    加载信息源配置文件
    
    Returns:
        Dict: 包含 RSS、Reddit、HackerNews 等所有信息源的配置
    """
    config_file = Path(__file__).parent.parent / "config" / "sources.json"
    
    if not config_file.exists():
        return {
            "rss_sources": [],
            "hackernews": {"enabled": True},
            "reddit": {"enabled": False, "subreddits": []},
            "github": {"enabled": False},
            "arxiv": {"enabled": True}
        }
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 加载 sources.json 失败: {e}")
        return {}


def get_score_threshold() -> float:
    """
    获取全局 AI 评分阈值
    
    优先级：环境变量 > sources.json > 默认值 7.0
    """
    env_val = os.getenv("AI_SCORE_THRESHOLD")
    if env_val is not None:
        try:
            return float(env_val)
        except ValueError:
            pass
    
    sources_config = load_sources_config()
    return sources_config.get("score_threshold", 7.0)
