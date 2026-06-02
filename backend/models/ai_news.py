"""
AI 新闻聚合数据模型 - SQLite 版本
"""

import time
from sqlalchemy import Column, String, Integer, Float, Text, DateTime, Index
from datetime import datetime, timezone

from models.database import Base


# 话题分类定义
# 话题分类定义（与SaaS版完全一致）
TOPICS = {
    "daily_brief": {
        "name": "每日速览",
        "name_en": "Daily Brief",
        "desc": "大厂官方动态、重要新闻，5分钟快速了解今日AI",
        "icon": "⚡",
        "keywords": ["official", "announcement", "release", "major news"],
        "priority": 1,
    },
    "tool_radar": {
        "name": "工具雷达",
        "name_en": "Tool Radar",
        "desc": "GitHub开源项目、实用工具，发现效率神器",
        "icon": "🔧",
        "keywords": ["tool", "library", "github", "open-source", "framework"],
        "priority": 2,
    },
    "industry_pulse": {
        "name": "行业脉搏",
        "name_en": "Industry Pulse",
        "desc": "融资、政策、市场分析，把握行业方向",
        "icon": "📈",
        "keywords": ["funding", "policy", "market", "business", "regulation"],
        "priority": 3,
    },
    "deep_read": {
        "name": "深度阅读",
        "name_en": "Deep Read",
        "desc": "技术博客、论文解读、工程实践，周末精读",
        "icon": "📚",
        "keywords": ["research", "paper", "tutorial", "technical", "engineering"],
        "priority": 4,
    },
    "community_voice": {
        "name": "社区声音",
        "name_en": "Community Voice",
        "desc": "HackerNews、Reddit热议，听听同行怎么说",
        "icon": "💬",
        "keywords": ["discussion", "community", "hackernews", "reddit"],
        "priority": 5,
    }
}


class AggregatedItem(Base):
    """
    聚合新闻条目
    """
    __tablename__ = "aggregated_items"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 来源信息
    content_id = Column(String(200), unique=True, nullable=False, index=True)
    source_type = Column(String(50), nullable=False)
    source_name = Column(String(200), nullable=False)
    
    # 话题分类（JSON 字符串存储）
    topics = Column(Text, nullable=False)
    
    # 内容
    title = Column(Text, nullable=False)
    original_title = Column(Text)
    url = Column(Text, nullable=False)
    content = Column(Text)
    author = Column(String(200))
    
    # AI 分析结果
    ai_score = Column(Float, nullable=False, index=True)
    ai_reason = Column(Text)
    ai_summary = Column(Text)
    ai_tags = Column(Text)
    
    # 元数据（JSON 字符串）
    metadata_json = Column(Text)
    
    # 时间
    published_at = Column(DateTime, nullable=False, index=True)
    fetched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # ===== 属性方法用于自动序列化/反序列化 =====
    
    @property
    def topics_list(self):
        """返回topics的列表形式"""
        if not self.topics:
            return []
        if isinstance(self.topics, list):
            return self.topics
        import json
        try:
            return json.loads(self.topics)
        except (json.JSONDecodeError, TypeError):
            return []
    
    @property
    def ai_tags_list(self):
        """返回ai_tags的列表形式"""
        if not self.ai_tags:
            return []
        if isinstance(self.ai_tags, list):
            return self.ai_tags
        import json
        try:
            return json.loads(self.ai_tags)
        except (json.JSONDecodeError, TypeError):
            return []
    
    @property
    def metadata_dict(self):
        """返回metadata_json的字典形式"""
        if not self.metadata_json:
            return {}
        if isinstance(self.metadata_json, dict):
            return self.metadata_json
        import json
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}
    
    # 索引
    __table_args__ = (
        Index('idx_source_type', 'source_type'),
        Index('idx_fetched_at', 'fetched_at'),
    )


class AggregationLog(Base):
    """
    聚合任务日志
    """
    __tablename__ = "aggregation_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    
    # 统计
    items_fetched = Column(Integer, default=0)
    items_analyzed = Column(Integer, default=0)
    items_saved = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    duration_ms = Column(Integer)
    error_msg = Column(Text, default='')
    
    started_at = Column(Integer, nullable=False, default=lambda: int(time.time()))
    finished_at = Column(Integer, default=0)
