#!/usr/bin/env python3
"""Batch processing pipeline for Omi memories exports to JSONL and CSV.

Optimized for:
1. LLM fine-tuning and RAG vector database ingestion (JSONL / NDJSON format).
2. Spreadsheet reporting and structured tabular analysis (CSV format).
3. Multi-page deduplication across paginated exports.
4. Flexible category filtering and privacy guards.

Zero external dependencies: Python standard library only.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

# CSV 导出标准列
CSV_FIELDS: Tuple[str, ...] = (
    "id",
    "created_at",
    "updated_at",
    "category",
    "content",
    "tags",
    "visibility",
)


def parse_utc_timestamp(val: Optional[str]) -> Optional[datetime]:
    """安全解析 ISO-8601 时间戳并标准化为 UTC datetime 对象。"""
    if not val or not isinstance(val, str):
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def sanitize_csv_cell(value: Any) -> str:
    """清洗字段以防御电子表格公式注入漏洞（Spreadsheet Formula Injection）。"""
    if value is None:
        return ""
    if isinstance(value, list):
        text = ", ".join(str(v).strip() for v in value if v is not None)
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)

    # 若以公式操作符开头，添加单引号前缀转义
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def unwrap_memories_data(raw_data: Any, source_name: str = "input") -> List[Dict[str, Any]]:
    """从纯列表或常见包装信封（memories, items, data, results）中提取记忆对象。"""
    if isinstance(raw_data, dict):
        for envelope_key in ("memories", "items", "data", "results"):
            candidate = raw_data.get(envelope_key)
            if isinstance(candidate, list):
                raw_data = candidate
                break

    if not isinstance(raw_data, list):
        raise ValueError(
            f"{source_name}: expected a JSON array or envelope object containing 'memories', 'items', 'data', or 'results'"
        )

    memories: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_data):
        if not isinstance(item, dict):
            raise ValueError(f"{source_name}: memory item at index {idx} must be a JSON object, got {type(item).__name__}")
        memories.append(item)

    return memories


def load_and_deduplicate(
    sources: Sequence[str],
    categories: Optional[Set[str]] = None,
    include_private: bool = True,
) -> List[Dict[str, Any]]:
    """加载一个或多个输入源（文件或 stdin），依据 ID 去重，并执行条件过滤。"""
    dedup_map: Dict[str, Dict[str, Any]] = {}
    ordered_ids: List[str] = []

    for src in sources:
        if src == "-":
            raw_text = sys.stdin.read()
            source_name = "<stdin>"
        else:
            p = Path(src)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {src}")
            raw_text = p.read_text(encoding="utf-8").lstrip("\ufeff")
            source_name = str(p)

        try:
            parsed_json = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON in {source_name}: {exc}") from exc

        items = unwrap_memories_data(parsed_json, source_name=source_name)

        for item in items:
            mem_id = str(item.get("id") or "").strip()
            if not mem_id:
                # 若无 ID，以内容哈希或对象哈希作为临时键
                mem_id = f"anon-{hash(json.dumps(item, sort_keys=True))}"

            # 类别过滤
            item_cat = str(item.get("category") or "").strip().lower()
            if categories and item_cat not in categories:
                continue

            # 隐私过滤
            vis = str(item.get("visibility") or "").strip().lower()
            if not include_private and vis == "private":
                continue

            if mem_id in dedup_map:
                # 冲突时比对 updated_at 或 created_at，保留最新者
                existing = dedup_map[mem_id]
                new_dt = parse_utc_timestamp(item.get("updated_at") or item.get("created_at"))
                old_dt = parse_utc_timestamp(existing.get("updated_at") or existing.get("created_at"))
                if new_dt and old_dt:
                    if new_dt > old_dt:
                        dedup_map[mem_id] = item
                else:
                    dedup_map[mem_id] = item
            else:
                dedup_map[mem_id] = item
                ordered_ids.append(mem_id)

    return [dedup_map[m_id] for m_id in ordered_ids]


def format_as_jsonl(memories: Iterable[Dict[str, Any]], schema_mode: str = "raw") -> str:
    """将记忆数据转换为 JSONL (JSON Lines) 字符串。

    schema_mode:
    - 'raw': 保持原始记忆实体结构，单行紧凑 JSON；
    - 'chat': 适配 LLM 指令微调（OpenAI/Anthropic/Gemini 风格的 messages 格式）。
    """
    buffer = io.StringIO()
    for item in memories:
        if schema_mode == "chat":
            cat = item.get("category") or "general"
            content = str(item.get("content") or "").strip()
            record = {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a personal memory retrieval assistant. Recall facts and knowledge accurately.",
                    },
                    {
                        "role": "user",
                        "content": f"What do you remember regarding {cat}?",
                    },
                    {
                        "role": "assistant",
                        "content": content,
                    },
                ],
                "metadata": {
                    "id": item.get("id"),
                    "created_at": item.get("created_at"),
                    "tags": item.get("tags") or [],
                },
            }
        else:
            # 保证按 key 排序或干净输出，确保紧凑单行
            record = item

        buffer.write(json.dumps(record, ensure_ascii=False) + "\n")

    return buffer.getvalue()


def format_as_csv(memories: Iterable[Dict[str, Any]]) -> str:
    """将记忆数据转换为标准 CSV 字符串，内嵌单元格清洗。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_FIELDS)

    for item in memories:
        row = [
            sanitize_csv_cell(item.get("id")),
            sanitize_csv_cell(item.get("created_at")),
            sanitize_csv_cell(item.get("updated_at")),
            sanitize_csv_cell(item.get("category")),
            sanitize_csv_cell(item.get("content")),
            sanitize_csv_cell(item.get("tags")),
            sanitize_csv_cell(item.get("visibility")),
        ]
        writer.writerow(row)

    return buffer.getvalue()


def validate_destination_path(destination: str, force: bool = False) -> Path:
    """路径安全检验：拒绝包含 '..' 的路径，且默认排他性创建。"""
    p = Path(destination)
    if ".." in p.parts:
        raise ValueError(f"Output path {destination!r} contains '..'; refusing to write outside intended directory.")

    if p.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}. Use -f/--force to overwrite.")

    return p


def run_pipeline(
    sources: Sequence[str],
    destination: Optional[str] = None,
    output_format: Optional[str] = None,
    schema_mode: str = "raw",
    categories: Optional[Sequence[str]] = None,
    include_private: bool = True,
    force: bool = False,
) -> str:
    """运行流水线全流程：加载 -> 去重 -> 过滤 -> 转换 -> 输出。"""
    # 类别集合
    cat_set = {c.strip().lower() for c in categories} if categories else None

    # 1. 加载并去重
    memories = load_and_deduplicate(
        sources=sources,
        categories=cat_set,
        include_private=include_private,
    )

    # 2. 推断输出格式
    fmt = (output_format or "").strip().lower()
    if not fmt:
        if destination and destination != "-":
            suffix = Path(destination).suffix.lower()
            if suffix in (".jsonl", ".ndjson"):
                fmt = "jsonl"
            elif suffix == ".csv":
                fmt = "csv"
            else:
                fmt = "jsonl"
        else:
            fmt = "jsonl"

    # 3. 格式化数据
    if fmt == "csv":
        result_text = format_as_csv(memories)
    elif fmt in ("jsonl", "ndjson"):
        result_text = format_as_jsonl(memories, schema_mode=schema_mode)
    else:
        raise ValueError(f"Unsupported format: {fmt}. Must be 'jsonl' or 'csv'.")

    # 4. 写入输出
    if destination is None or destination == "-":
        return result_text

    dest_path = validate_destination_path(destination, force=force)
    if dest_path.parent and not dest_path.parent.exists():
        dest_path.parent.mkdir(parents=True, exist_ok=True)

    dest_path.write_text(result_text, encoding="utf-8")
    return result_text


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 命令行入口点。"""
    parser = argparse.ArgumentParser(
        description="Batch processing pipeline for Omi memories exports to JSONL and CSV."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["-"],
        help="One or more input JSON export files or '-' for stdin (default: '-')",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help="Destination path for output file or '-' for stdout",
    )
    parser.add_argument(
        "--format",
        choices=["jsonl", "csv"],
        default=None,
        help="Output format (jsonl or csv; auto-inferred from output filename if omitted, default: jsonl)",
    )
    parser.add_argument(
        "--schema",
        choices=["raw", "chat"],
        default="raw",
        help="JSONL record schema: 'raw' for compact original object, 'chat' for LLM fine-tuning messages (default: raw)",
    )
    parser.add_argument(
        "--category",
        dest="category",
        help="Filter by category (comma-separated, e.g. 'work,learnings')",
    )
    parser.add_argument(
        "--no-private",
        dest="include_private",
        action="store_false",
        help="Exclude memories marked with visibility='private'",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file without confirmation",
    )

    args = parser.parse_args(argv)

    cat_list = [c.strip() for c in args.category.split(",") if c.strip()] if args.category else None
    sources = args.inputs if args.inputs else ["-"]

    try:
        content = run_pipeline(
            sources=sources,
            destination=args.output,
            output_format=args.format,
            schema_mode=args.schema,
            categories=cat_list,
            include_private=args.include_private,
            force=args.force,
        )
        if args.output is None or args.output == "-":
            sys.stdout.write(content)
            sys.stdout.flush()
        return 0
    except Exception as exc:
        sys.stderr.write(f"Memories pipeline failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
