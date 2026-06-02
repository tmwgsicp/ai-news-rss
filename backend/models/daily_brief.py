"""
每日日报数据模型 - SQLite 版本
"""

from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
import json

from models.database import Base


class DailyBrief(Base):
    """每日日报表"""
    
    __tablename__ = "daily_briefs"
    
    id = Column(Integer, primary_key=True)
    date = Column(String(10), unique=True, index=True, nullable=False)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=False)
    total_count = Column(Integer, default=0)
    
    # 存储完整的日报数据（JSON 字符串）
    sections_json = Column(Text, nullable=False)
    
    # TTS 音频文件路径
    audio_path = Column(String(500))
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def sections(self):
        """解析 JSON 字符串为 Python 对象"""
        if self.sections_json:
            return json.loads(self.sections_json)
        return []
    
    @sections.setter
    def sections(self, value):
        """将 Python 对象序列化为 JSON 字符串"""
        self.sections_json = json.dumps(value, ensure_ascii=False)
    
    def __repr__(self):
        return f"<DailyBrief(date={self.date}, total={self.total_count})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            "id": self.id,
            "date": self.date,
            "title": self.title,
            "summary": self.summary,
            "total_count": self.total_count,
            "sections": self.sections,
            "audio_path": self.audio_path,
            "generated_at": self.created_at.isoformat() if self.created_at else None
        }
