#!/usr/bin/env python3
"""
從 IMAP 信箱解析股票買賣紀錄，輸出交易歷史與目前持股。

2026-02-14 調整方式: 新增 mail 交易解析腳本，採單次掃描 + CSV/JSON 落地。
"""

import argparse
import csv
import email
import hashlib
import imaplib
import json
import os
import re
import sys
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
DEFAULT_OUTPUT_CSV = os.path.join(PROJECT_ROOT, "outputs", "mail_trade_records.csv")
DEFAULT_OUTPUT_HOLDINGS = os.path.join(PROJECT_ROOT, "outputs", "current_holdings.json")
CSV_HEADERS = ["mail_date", "message_id", "action", "stock_code", "price", "quantity"]

FIELD_PATTERN = re.compile(r"^\s*([A-Za-z_ ]+)\s*:\s*(.+?)\s*$")


def parse_arguments():
    parser = argparse.ArgumentParser(description="掃描信件並整理股票交易紀錄")
    parser.add_argument("--subject-keyword", required=True, help="主旨關鍵字（包含比對）")
    parser.add_argument("--imap-host", default="", help="IMAP 主機")
    parser.add_argument("--imap-port", type=int, default=0, help="IMAP 連接埠")
    parser.add_argument("--imap-user", default="", help="IMAP 帳號")
    parser.add_argument("--imap-secret", default="", help="IMAP 密鑰")
    parser.add_argument("--mailbox", default="INBOX", help="信箱資料夾")
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV, help="交易紀錄 CSV")
    parser.add_argument(
        "--output-holdings",
        default=DEFAULT_OUTPUT_HOLDINGS,
        help="目前持股 JSON",
    )
    parser.add_argument("--dry-run", action="store_true", help="僅解析不寫入")
    return parser.parse_args()


def _decode_header_text(raw_text):
    if not raw_text:
        return ""

    try:
        return str(make_header(decode_header(raw_text))).strip()
    except Exception:
        return str(raw_text).strip()


def _normalize_mail_date(raw_date):
    if not raw_date:
        return ""

    try:
        return parsedate_to_datetime(raw_date).isoformat()
    except Exception:
        return str(raw_date).strip()


def _extract_plain_text(message_obj):
    if message_obj.is_multipart():
        for part in message_obj.walk():
            if part.get_content_maintype() != "text":
                continue
            if part.get_content_subtype() != "plain":
                continue
            if str(part.get("Content-Disposition", "")).lower().startswith("attachment"):
                continue

            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            if payload is None:
                continue
            return payload.decode(charset, errors="replace")
        return ""

    payload = message_obj.get_payload(decode=True)
    charset = message_obj.get_content_charset() or "utf-8"
    if payload is None:
        return ""
    return payload.decode(charset, errors="replace")


def _normalize_field_name(raw_name):
    normalized_name = raw_name.strip().lower().replace("_", "").replace(" ", "")
    alias_map = {
        "action": "action",
        "stockcode": "stock_code",
        "stockid": "stock_code",
        "price": "price",
        "quantity": "quantity",
    }
    return alias_map.get(normalized_name, "")


def _normalize_action(raw_action):
    text = str(raw_action).strip().upper()
    if text in ["BUY", "SELL"]:
        return text
    return ""


def parse_trade_records(mail_body):
    records = []
    warning_messages = []
    current_record = {}

    lines = str(mail_body or "").splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        matched = FIELD_PATTERN.match(raw_line)
        if not matched:
            continue

        raw_key, raw_value = matched.groups()
        field_name = _normalize_field_name(raw_key)
        if not field_name:
            continue

        if field_name == "action" and current_record:
            _append_trade_record(current_record, records, warning_messages, line_number)
            current_record = {}

        current_record[field_name] = raw_value.strip()
        if _is_trade_record_complete(current_record):
            _append_trade_record(current_record, records, warning_messages, line_number)
            current_record = {}

    if current_record:
        _append_trade_record(current_record, records, warning_messages, len(lines))

    return records, warning_messages


def _is_trade_record_complete(record_item):
    required_fields = ["action", "stock_code", "price", "quantity"]
    return all(record_item.get(field) for field in required_fields)


def _append_trade_record(record_item, records, warning_messages, line_number):
    normalized_action = _normalize_action(record_item.get("action", ""))
    stock_code = str(record_item.get("stock_code", "")).strip()

    try:
        price = float(record_item.get("price", 0))
    except (TypeError, ValueError):
        price = 0

    try:
        quantity = int(float(record_item.get("quantity", 0)))
    except (TypeError, ValueError):
        quantity = 0

    if not normalized_action or not stock_code or price <= 0 or quantity <= 0:
        warning_messages.append(f"忽略無效交易資料（line={line_number}）: {record_item}")
        return

    records.append(
        {
            "action": normalized_action,
            "stock_code": stock_code,
            "price": price,
            "quantity": quantity,
        }
    )


def _load_existing_rows(csv_path):
    if not os.path.exists(csv_path):
        return []

    with open(csv_path, "r", encoding="utf-8", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        return [row for row in reader if row]


def _normalize_price_text(price_value):
    return f"{float(price_value):.6f}"


def build_record_key(row_item):
    return (
        str(row_item.get("message_id", "")).strip(),
        str(row_item.get("action", "")).strip().upper(),
        str(row_item.get("stock_code", "")).strip(),
        _normalize_price_text(row_item.get("price", 0)),
        str(int(float(row_item.get("quantity", 0)))).strip(),
    )


def _build_existing_key_set(rows):
    key_set = set()
    for row_item in rows:
        try:
            key_set.add(build_record_key(row_item))
        except Exception:
            continue
    return key_set


def _ensure_parent_dir(file_path):
    folder_path = os.path.dirname(os.path.abspath(file_path))
    os.makedirs(folder_path, exist_ok=True)


def append_csv_rows(csv_path, rows):
    _ensure_parent_dir(csv_path)
    file_exists = os.path.exists(csv_path)

    with open(csv_path, "a", encoding="utf-8", newline="") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CSV_HEADERS)
        if not file_exists:
            writer.writeheader()

        for row_item in rows:
            writer.writerow(row_item)


def rebuild_current_holdings(all_rows):
    positions = {}
    warning_messages = []

    sorted_rows = sorted(
        all_rows,
        key=lambda item: (str(item.get("mail_date", "")), str(item.get("message_id", ""))),
    )

    for row_item in sorted_rows:
        stock_code = str(row_item.get("stock_code", "")).strip()
        action = str(row_item.get("action", "")).strip().upper()

        try:
            price = float(row_item.get("price", 0))
            quantity = int(float(row_item.get("quantity", 0)))
        except (TypeError, ValueError):
            continue

        if not stock_code or quantity <= 0 or price <= 0:
            continue

        position_item = positions.setdefault(stock_code, {"quantity": 0, "avg_price": 0.0})

        if action == "BUY":
            old_quantity = position_item["quantity"]
            old_cost = old_quantity * position_item["avg_price"]
            new_quantity = old_quantity + quantity
            new_avg_price = (old_cost + quantity * price) / new_quantity
            position_item["quantity"] = new_quantity
            position_item["avg_price"] = new_avg_price
            continue

        if action == "SELL":
            old_quantity = position_item["quantity"]
            new_quantity = old_quantity - quantity
            if new_quantity <= 0:
                if new_quantity < 0:
                    warning_messages.append(
                        f"股票 {stock_code} 發生賣超，已將庫存歸零（原庫存={old_quantity}, 賣出={quantity}）"
                    )
                position_item["quantity"] = 0
                position_item["avg_price"] = 0.0
            else:
                position_item["quantity"] = new_quantity
            continue

    normalized_positions = []
    for stock_code, position_item in sorted(positions.items()):
        if position_item["quantity"] <= 0:
            continue

        normalized_positions.append(
            {
                "stock_code": stock_code,
                "quantity": int(position_item["quantity"]),
                "avg_price": round(float(position_item["avg_price"]), 4),
            }
        )

    return normalized_positions, warning_messages


def write_holdings_json(json_path, positions):
    _ensure_parent_dir(json_path)
    payload = {
        "generated_at": datetime.now().isoformat(),
        "positions": positions,
    }
    with open(json_path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def _build_fallback_message_id(subject_text, mail_date_text, mail_body):
    source_text = f"{subject_text}|{mail_date_text}|{mail_body}".encode("utf-8", errors="ignore")
    digest = hashlib.sha1(source_text).hexdigest()
    return f"fallback-{digest}"


def _resolve_imap_settings(args_obj):
    imap_host = args_obj.imap_host or os.getenv("MAIL_IMAP_HOST", "")
    imap_port = args_obj.imap_port or int(os.getenv("MAIL_IMAP_PORT", "993"))
    imap_user = args_obj.imap_user or os.getenv("MAIL_IMAP_USER", "")
    imap_secret = args_obj.imap_secret or os.getenv("MAIL_IMAP_SECRET", "")

    if not imap_host or not imap_user or not imap_secret:
        raise ValueError("IMAP 設定不完整，請提供 host/user/secret")

    return imap_host, imap_port, imap_user, imap_secret


def _iter_unseen_uids(imap_conn):
    status, data = imap_conn.uid("search", None, "UNSEEN")
    if status != "OK" or not data:
        return []

    raw_uids = data[0].decode("utf-8") if isinstance(data[0], bytes) else str(data[0])
    return [uid for uid in raw_uids.split() if uid]


def _fetch_message_by_uid(imap_conn, uid_text):
    status, data = imap_conn.uid("fetch", uid_text, "(BODY.PEEK[])")
    if status != "OK" or not data:
        return None

    for item in data:
        if isinstance(item, tuple) and len(item) >= 2:
            raw_mail = item[1]
            if isinstance(raw_mail, (bytes, bytearray)):
                return email.message_from_bytes(raw_mail)

    return None


def _mark_seen(imap_conn, uid_text):
    imap_conn.uid("store", uid_text, "+FLAGS", "(\\Seen)")


def run_scan(args_obj):
    imap_host, imap_port, imap_user, imap_secret = _resolve_imap_settings(args_obj)
    existing_rows = _load_existing_rows(args_obj.output_csv)
    existing_key_set = _build_existing_key_set(existing_rows)

    new_rows = []
    seen_uids = []
    parsed_count = 0
    matched_count = 0

    with imaplib.IMAP4_SSL(imap_host, imap_port) as imap_conn:
        imap_conn.login(imap_user, imap_secret)
        select_status, _ = imap_conn.select(args_obj.mailbox)
        if select_status != "OK":
            raise RuntimeError(f"無法選取信箱: {args_obj.mailbox}")

        for uid_text in _iter_unseen_uids(imap_conn):
            message_obj = _fetch_message_by_uid(imap_conn, uid_text)
            if message_obj is None:
                continue

            parsed_count += 1
            subject_text = _decode_header_text(message_obj.get("Subject", ""))
            if args_obj.subject_keyword not in subject_text:
                continue

            matched_count += 1
            mail_body = _extract_plain_text(message_obj)
            trade_records, warning_messages = parse_trade_records(mail_body)
            for warning_message in warning_messages:
                print(f"[WARN] {warning_message}")

            if not trade_records:
                continue

            message_id = str(message_obj.get("Message-ID", "")).strip()
            mail_date_text = _normalize_mail_date(message_obj.get("Date", ""))
            if not message_id:
                message_id = _build_fallback_message_id(subject_text, mail_date_text, mail_body)
                print(f"[WARN] 郵件缺少 Message-ID，使用 fallback: {message_id}")

            message_new_count = 0
            for trade_item in trade_records:
                row_item = {
                    "mail_date": mail_date_text,
                    "message_id": message_id,
                    "action": trade_item["action"],
                    "stock_code": trade_item["stock_code"],
                    "price": trade_item["price"],
                    "quantity": trade_item["quantity"],
                }
                row_key = build_record_key(row_item)
                if row_key in existing_key_set:
                    continue

                existing_key_set.add(row_key)
                new_rows.append(row_item)
                message_new_count += 1

            if message_new_count > 0:
                seen_uids.append(uid_text)

        if args_obj.dry_run:
            print("[INFO] dry-run 模式，不寫入檔案，不標記已讀")
            return {
                "parsed_count": parsed_count,
                "matched_count": matched_count,
                "new_count": len(new_rows),
                "holdings_count": 0,
            }

        all_rows = list(existing_rows)
        if new_rows:
            append_csv_rows(args_obj.output_csv, new_rows)
            all_rows.extend(new_rows)

        current_positions, holding_warnings = rebuild_current_holdings(all_rows)
        for warning_message in holding_warnings:
            print(f"[WARN] {warning_message}")

        write_holdings_json(args_obj.output_holdings, current_positions)

        for uid_text in seen_uids:
            _mark_seen(imap_conn, uid_text)

    return {
        "parsed_count": parsed_count,
        "matched_count": matched_count,
        "new_count": len(new_rows),
        "holdings_count": len(current_positions),
    }


def main():
    args_obj = parse_arguments()

    try:
        result = run_scan(args_obj)
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(
        "[INFO] 掃描完成: "
        f"解析 {result['parsed_count']} 封, "
        f"主旨命中 {result['matched_count']} 封, "
        f"新增交易 {result['new_count']} 筆, "
        f"目前持股 {result['holdings_count']} 檔"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
