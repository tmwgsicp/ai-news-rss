"""
简化的邮件服务 - 开源版
仅支持单个 SMTP 配置
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from core.config import config

logger = logging.getLogger(__name__)


class EmailService:
    """简化的邮件服务"""
    
    def __init__(self):
        self.smtp_host = config.get_env("SMTP_HOST")
        self.smtp_port = config.get_env("SMTP_PORT", 465)
        self.smtp_user = config.get_env("SMTP_USER")
        self.smtp_password = config.get_env("SMTP_PASSWORD")
        self.from_address = config.get_env("SMTP_FROM", self.smtp_user)
    
    def is_configured(self) -> bool:
        """检查邮件服务是否配置"""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)
    
    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> bool:
        """
        发送邮件
        
        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            html_body: HTML 邮件正文
            text_body: 纯文本邮件正文（可选）
        
        Returns:
            bool: 是否发送成功
        """
        if not self.is_configured():
            logger.warning("SMTP not configured, skip email sending")
            return False
        
        try:
            # 创建邮件
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_address
            msg['To'] = to_email
            
            # 添加纯文本版本
            if text_body:
                part1 = MIMEText(text_body, 'plain', 'utf-8')
                msg.attach(part1)
            
            # 添加 HTML 版本
            part2 = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(part2)
            
            # 连接 SMTP 服务器并发送
            if self.smtp_port == 465:
                # SSL
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            else:
                # TLS
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
            
            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
    
    def send_daily_brief_notification(
        self,
        to_email: str,
        brief_date: str,
        total_count: int,
        web_url: str
    ) -> bool:
        """
        发送每日简报通知邮件
        
        Args:
            to_email: 收件人邮箱
            brief_date: 日报日期
            total_count: 新闻总数
            web_url: 查看链接
        """
        subject = f"AI News RSS - {brief_date} 日报已生成"
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 8px 8px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #667eea; color: white; text-decoration: none; border-radius: 6px; margin-top: 20px; }}
                .footer {{ text-align: center; margin-top: 20px; color: #999; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📰 AI News RSS</h1>
                    <p>每日简报已生成</p>
                </div>
                <div class="content">
                    <h2>📅 {brief_date}</h2>
                    <p>今日为您精选了 <strong>{total_count}</strong> 条高质量 AI 资讯。</p>
                    <p>点击下方按钮查看完整日报：</p>
                    <a href="{web_url}" class="button">查看今日简报</a>
                </div>
                <div class="footer">
                    <p>AI News RSS - 每天 10 分钟掌握 AI 动态</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        AI News RSS - {brief_date} 日报已生成
        
        今日为您精选了 {total_count} 条高质量 AI 资讯。
        
        查看完整日报：{web_url}
        
        ---
        AI News RSS - 每天 10 分钟掌握 AI 动态
        """
        
        return self.send_email(to_email, subject, html_body, text_body)


# 全局实例
email_service = EmailService()
