"""
Email 寄送模組
支援寄送分析報告與買賣警報
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

logger = logging.getLogger(__name__)


class EmailSender:
    def __init__(self, config):
        """
        Args:
            config: dict with keys: smtp_host, smtp_port, sender, password, recipient
        """
        self.smtp_host = config['smtp_host']
        self.smtp_port = int(config['smtp_port'])
        self.sender = config['sender']
        self.password = config['password']
        self.recipient = config['recipient']

    def _send(self, subject, body, attachments=None, html=False):
        """
        底層寄送方法

        Args:
            subject: 郵件主題
            body: 郵件內容
            attachments: 附件檔案路徑列表
            html: 是否為 HTML 格式
        """
        msg = MIMEMultipart()
        msg['From'] = self.sender
        msg['To'] = self.recipient
        msg['Subject'] = subject

        content_type = 'html' if html else 'plain'
        msg.attach(MIMEText(body, content_type, 'utf-8'))

        # 附加檔案
        if attachments:
            for filepath in attachments:
                path = Path(filepath)
                if not path.exists():
                    logger.warning(f"附件不存在，跳過: {filepath}")
                    continue

                part = MIMEBase('application', 'octet-stream')
                part.set_payload(path.read_bytes())
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{path.name}"'
                )
                msg.attach(part)

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
                server.send_message(msg)
            logger.info(f"Email 寄送成功: {subject}")
            return True
        except Exception as e:
            logger.error(f"Email 寄送失敗: {e}")
            return False

    def send_report(self, subject, body, attachments=None):
        """
        寄送分析報告

        Args:
            subject: 郵件主題
            body: 報告內容（Markdown 純文字）
            attachments: 附件 markdown 檔案路徑列表
        """
        return self._send(subject, body, attachments=attachments)

    def send_alert(self, stocks_info):
        """
        寄送買賣警報

        Args:
            stocks_info: list of dict, 每個 dict 包含:
                - stock_code: 股票代號
                - stock_name: 股票名稱
                - signal_type: "buy" 或 "sell"
                - price: 當前價格
                - reason: 觸發原因
                - suggested_quantity: 建議數量（股）
                - quantity_unit: 數量單位（股）
                - quantity_note: 數量計算說明
        """
        if not stocks_info:
            return False

        buy_alerts = [s for s in stocks_info if s['signal_type'] == 'buy']
        sell_alerts = [s for s in stocks_info if s['signal_type'] == 'sell']

        lines = []
        lines.append("=" * 50)
        lines.append("  台股盤中買賣警報")
        lines.append("=" * 50)
        lines.append("")

        if buy_alerts:
            lines.append("【買入信號】")
            lines.append("-" * 40)
            for s in buy_alerts:
                # 2026-02-15 調整方式: 警報信件新增建議買賣數量與計算說明。
                quantity = s.get('suggested_quantity', 'N/A')
                quantity_unit = str(s.get('quantity_unit', '股')).strip() or '股'
                quantity_note = s.get('quantity_note', 'N/A')
                lines.append(f"  {s['stock_code']} {s['stock_name']}")
                lines.append(f"  當前價格: {s['price']}")
                lines.append(f"  觸發原因: {s['reason']}")
                lines.append(f"  建議數量: {quantity}{quantity_unit}")
                lines.append(f"  數量說明: {quantity_note}")
                lines.append("")

        if sell_alerts:
            lines.append("【賣出信號】")
            lines.append("-" * 40)
            for s in sell_alerts:
                quantity = s.get('suggested_quantity', 'N/A')
                quantity_unit = str(s.get('quantity_unit', '股')).strip() or '股'
                quantity_note = s.get('quantity_note', 'N/A')
                lines.append(f"  {s['stock_code']} {s['stock_name']}")
                lines.append(f"  當前價格: {s['price']}")
                lines.append(f"  觸發原因: {s['reason']}")
                lines.append(f"  建議數量: {quantity}{quantity_unit}")
                lines.append(f"  數量說明: {quantity_note}")
                lines.append("")

        lines.append("=" * 50)
        lines.append("此為自動化系統產生之警報，僅供參考，不構成投資建議。")

        body = '\n'.join(lines)
        subject = f"[台股警報] 買入{len(buy_alerts)}檔 / 賣出{len(sell_alerts)}檔"

        return self._send(subject, body)

    def test_connection(self):
        """測試 SMTP 連線"""
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender, self.password)
            logger.info("SMTP 連線測試成功")
            return True
        except Exception as e:
            logger.error(f"SMTP 連線測試失敗: {e}")
            return False
