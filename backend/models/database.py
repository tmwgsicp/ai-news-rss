"""
数据库配置 - SQLite 版本（开源版）
"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from core.config import config

# 创建异步引擎
engine = create_async_engine(
    config.database_url,
    echo=config.debug,
    future=True,
)

# 创建会话工厂
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    """SQLAlchemy 基类"""
    pass

async def init_db():
    """初始化数据库表"""
    # 必须在这里导入所有模型，确保它们被注册到 Base.metadata
    import models.ai_news
    import models.daily_brief
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
