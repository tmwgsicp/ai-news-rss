"""
文本清理工具 - 用于统一处理各种格式的文本
包括：Markdown 清理、HTML 清理、特殊字符处理等
"""

import re
from typing import Optional


def clean_markdown(text: str) -> str:
    """
    清理 Markdown 语法，保留纯文本内容
    
    清理内容：
    - **加粗** / __加粗__
    - *斜体* / _斜体_
    - `代码`
    - [链接](url)
    - # 标题
    
    Args:
        text: 原始文本
        
    Returns:
        清理后的纯文本
    """
    if not text:
        return ""
    
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    
    text = re.sub(r'`(.+?)`', r'\1', text)
    
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    
    return text.strip()


def clean_for_display(text: str) -> str:
    """
    清理文本用于前端显示
    
    包括：
    - Markdown 清理
    - 多余空白清理
    - 特殊字符规范化
    
    Args:
        text: 原始文本
        
    Returns:
        适合显示的纯文本
    """
    if not text:
        return ""
    
    text = clean_markdown(text)
    
    text = ' '.join(text.split())
    
    return text.strip()


def clean_for_speech(text: str) -> str:
    """
    清理文本用于语音播报
    
    包括：
    - Markdown 清理
    - Emoji 移除
    - URL 移除
    - 特殊符号处理
    
    Args:
        text: 原始文本
        
    Returns:
        适合语音朗读的纯文本
    """
    if not text:
        return ""
    
    text = clean_markdown(text)
    
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    
    text = re.sub(r'https?://\S+', '', text)
    
    text = text.replace('【', '').replace('】', '')
    text = text.replace('[', '').replace(']', '')
    text = text.replace('《', '').replace('》', '')
    
    text = ' '.join(text.split())
    
    if text and not text.endswith(('。', '！', '？', '.')):
        text += '。'
    
    return text.strip()
