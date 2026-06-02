"""
日报文稿生成器 - 专门为语音播报优化
支持两种模式：
1. AI 重写（默认）：调用 ZhipuAI 生成专业播报文稿
2. 模板拼接（fallback）：机械拼接标题+摘要
"""

import logging
import os
from typing import List, Dict, Optional
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)


class DailyBriefScriptGenerator:
    """日报文稿生成器，生成适合语音播报的内容"""
    
    def __init__(self):
        self.category_names = {
            "daily_brief": "每日速览",
            "tool_radar": "工具雷达",
            "industry_pulse": "行业脉搏",
            "deep_read": "深度阅读",
            "community_voice": "社区声音"
        }
    
    def generate_opening(self, date: datetime) -> str:
        """生成开场白"""
        weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekday_names[date.weekday()]
        
        return f"""大家好，欢迎收听 AI NewsRSS 日报。
今天是{date.year}年{date.month}月{date.day}日，{weekday}。
我们为您精选全球AI行业最新动态，
告别信息焦虑，高效掌握前沿资讯。"""
    
    def generate_closing(self, total_count: int) -> str:
        """生成结束语"""
        return f"""今天的日报到这里就结束了，共为您播报{total_count}条精选资讯。
AI NewsRSS 每天24小时智能监测，只推送真正有价值的内容。
感谢收听，明天见。"""
    
    def format_news_for_speech(self, news_item: Dict, detail_level: str = "full") -> str:
        """将新闻格式化为语音友好的文本

        Args:
            news_item: 新闻数据，包含 title, summary, score, categories 等
            detail_level:
                "full"    - 标题 + 完整摘要
                "brief"   - 标题 + 摘要第一句
                "title"   - 仅标题
        """
        from utils.text_cleaner import clean_for_speech
        
        title = clean_for_speech(news_item.get('title', ''))

        if detail_level == "title":
            return title

        summary = clean_for_speech(news_item.get('summary', ''))

        if detail_level == "brief" and summary:
            import re
            first_sentence = re.split(r'[。！？.!?]', summary, maxsplit=1)[0]
            if first_sentence:
                summary = first_sentence + '。'

        return f"{title}。{summary}" if summary else title
    
    def generate_category_intro(self, category: str, count: int, position: str = "next") -> str:
        """生成分类引导语
        
        Args:
            category: 分类 key
            count: 该分类的条目数
            position: "first" / "next" / "last" 控制过渡语
        """
        name = self.category_names.get(category, category)

        descriptions = {
            "daily_brief": f"为您带来{count}条今日最重要的AI动态",
            "tool_radar": f"发现{count}个实用的AI工具和开源项目",
            "industry_pulse": f"为您解读{count}条行业趋势和商业动态",
            "deep_read": f"精选{count}篇前沿研究和技术分析",
            "community_voice": f"看看技术社区正在讨论什么，{count}条热门话题"
        }
        desc = descriptions.get(category, f"共{count}条")

        if position == "first":
            return f"首先是{name}，{desc}"
        elif position == "last":
            return f"最后是{name}，{desc}"
        else:
            return f"接下来是{name}，{desc}"
    
    def generate_category_section(self, category: str, news_items: List[Dict], position: str = "next") -> str:
        """生成某个分类的播报文本
        
        内容分级策略（控制音频时长和 TTS 成本）：
        - 前3条：标题 + 完整摘要（高分核心内容）
        - 第4~8条：标题 + 摘要首句（保留关键信息）
        - 第9条起：仅标题（快速扫过，确保完整覆盖）
        """
        if not news_items:
            return ""

        FULL_LIMIT = 3
        BRIEF_LIMIT = 8

        intro = self.generate_category_intro(category, len(news_items), position)
        lines = [f"\n{intro}。"]

        for i, item in enumerate(news_items, 1):
            if i <= FULL_LIMIT:
                detail = "full"
            elif i <= BRIEF_LIMIT:
                detail = "brief"
            else:
                detail = "title"

            news_text = self.format_news_for_speech(item, detail_level=detail)

            if len(news_items) > 1:
                lines.append(f"\n第{i}条，{news_text}")
            else:
                lines.append(f"\n{news_text}")

        return "\n".join(lines)
    
    def generate_full_script(
        self,
        date: datetime,
        news_by_category: Dict[str, List[Dict]],
        category_order: List[str] = None,
    ) -> str:
        """生成完整的日报播报文稿（全部条目，内容分级精简）"""
        if category_order is None:
            category_order = list(news_by_category.keys())

        active_categories = [c for c in category_order if c in news_by_category and news_by_category[c]]

        sections = []
        total_count = 0

        sections.append(self.generate_opening(date))

        for idx, category in enumerate(active_categories):
            items = news_by_category[category]
            if not items:
                continue

            total_count += len(items)

            if idx == 0:
                position = "first"
            elif idx == len(active_categories) - 1:
                position = "last"
            else:
                position = "next"

            section = self.generate_category_section(category, items, position)
            if section:
                sections.append(section)

        sections.append(self.generate_closing(total_count))

        return "\n\n".join(sections)


def generate_daily_audio_script(
    news_items: List[Dict],
    date: datetime = None,
    category_order: List[str] = None
) -> str:
    """模板模式：生成日报语音文稿（fallback 用）"""
    if date is None:
        date = datetime.now()

    news_by_category: Dict[str, List[Dict]] = {}
    for item in news_items:
        categories = item.get('categories', [])
        if categories:
            category = categories[0]
            if category not in news_by_category:
                news_by_category[category] = []
            news_by_category[category].append(item)

    generator = DailyBriefScriptGenerator()
    return generator.generate_full_script(date, news_by_category, category_order=category_order)


ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"

BROADCAST_SYSTEM_PROMPT = """你是 AI NewsRSS 的专业播报员，负责将每日 AI 行业资讯整理成一篇适合语音朗读的播报文稿。

要求：
1. 语气自然、口语化，像一位专业主播在播报科技新闻
2. 板块之间用自然的过渡语衔接，不要机械地说"第1条、第2条"
3. 每条新闻用1-3句话概括核心信息，避免罗列细节
4. 重要新闻可以多说几句分析，次要新闻一句话带过
5. 开头有简短问候和日期，结尾有总结和告别
6. 总字数控制在2500字以内
7. 不要出现任何 URL、emoji、特殊符号
8. 不要出现任何 markdown 格式标记
9. 输出纯文本，直接可以送入 TTS 引擎朗读"""


CATEGORY_NAMES = {
    "daily_brief": "每日速览",
    "tool_radar": "工具雷达",
    "industry_pulse": "行业脉搏",
    "deep_read": "深度阅读",
    "community_voice": "社区声音",
}


def _build_ai_prompt(daily_brief_sections: List[Dict], date: datetime) -> str:
    """将日报 sections 构造成 AI prompt 输入"""
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday = weekday_names[date.weekday()]
    date_str = f"{date.year}年{date.month}月{date.day}日，{weekday}"

    parts = [f"日期：{date_str}\n"]

    for section in daily_brief_sections:
        topic_key = section.get("topic_key", "")
        topic_name = CATEGORY_NAMES.get(topic_key, section.get("topic_name", topic_key))
        items = section.get("items", [])
        if not items:
            continue

        parts.append(f"\n## {topic_name}（{len(items)}条）\n")
        for i, item in enumerate(items, 1):
            title = item.get("title", "")
            summary = item.get("summary", "")
            content = item.get("content", "")
            content_snippet = content[:300] if content else ""

            entry = f"{i}. {title}"
            if summary:
                entry += f"\n   摘要：{summary}"
            if content_snippet and content_snippet != summary:
                entry += f"\n   补充：{content_snippet}"
            parts.append(entry)

    parts.append("\n\n请基于以上资讯，生成一篇完整的语音播报文稿。")
    return "\n".join(parts)


async def generate_ai_broadcast_script(
    daily_brief_sections: List[Dict],
    date: datetime,
) -> Optional[str]:
    """
    调用 ZhipuAI 生成专业播报文稿。
    返回 None 表示失败，调用方应 fallback 到模板模式。
    """
    api_key = os.getenv("ZHIPU_API_KEY", "")
    if not api_key:
        logger.warning("ZHIPU_API_KEY not set, skipping AI broadcast script")
        return None

    model = os.getenv("TTS_SCRIPT_MODEL", "glm-4-flash")
    user_prompt = _build_ai_prompt(daily_brief_sections, date)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{ZHIPU_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": BROADCAST_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4096,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        if not content or len(content) < 200:
            logger.warning("AI broadcast script too short (%d chars), fallback", len(content or ""))
            return None

        logger.info("AI broadcast script generated: %d chars, model=%s", len(content), model)
        return content

    except Exception as e:
        logger.error("Failed to generate AI broadcast script: %s", e, exc_info=True)
        return None
