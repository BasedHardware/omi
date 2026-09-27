#!/usr/bin/env python3
"""Convert Omi conversation JSON exports into Tab-Separated Values (TSV) format.

Optimized for command-line text processing (`grep`, `awk`, `cut`, `sed`).
Multi-line summaries and transcripts have newlines and tabs escaped safely to
guarantee strictly 1 line per record.

Features:
- Zero external dependencies: Python standard library only.
- Unwraps bare JSON arrays or envelope objects (`conversations`, `items`, `data`, `results`).
- Supports reading from files or standard input (`-`).
- Supports writing to files or standard output (`-`).
- Path traversal guard refusing '..' in destination paths.
- Exclusive creation by default to avoid accidental overwrites, with `-f` / `--force` to override.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# TSV 导出的核心字段契约
FIELDS: Tuple[str, ...] = (
    "id",
    "started_at",
    "title",
    "category",
    "source",
    "overview",
    "transcript",
)


def escape_tsv_field(value: Any) -> str:
    """将字段值安全转义为符合 TSV 单行约束的纯文本。

    规则：
    1. None 返回空字符串；
    2. 非字符串对象进行 JSON 或字符串化；
    3. 将换行符 (\\r\\n, \\r, \\n) 安全转义为字面量 '\\n'；
    4. 将制表符 (\\t) 安全转义为字面量 '\\t'；
    5. 杜绝控制字符破坏 TSV 记录的单行完整性。
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
    else:
        text = value

    # 标准化并转义换行符与制表符，保证单行性
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "\\t")
    text = text.replace("\n", "\\n")
    return text


def extract_transcript(item: Dict[str, Any]) -> str:
    """从对话对象中提取转录文本，兼容顶层 transcript 字符串或 segments/transcripts 数组。"""
    transcript_val = item.get("transcript")
    if isinstance(transcript_val, str) and transcript_val.strip():
        return transcript_val

    # 兼容分段转录列表
    segments = item.get("segments") or item.get("transcripts")
    if isinstance(segments, list):
        parts: List[str] = []
        for seg in segments:
            if isinstance(seg, dict):
                speaker = seg.get("speaker") or seg.get("speaker_label")
                text = seg.get("text") or seg.get("content") or ""
                if text:
                    if speaker:
                        parts.append(f"{speaker}: {text}")
                    else:
                        parts.append(str(text))
            elif isinstance(seg, str) and seg.strip():
                parts.append(seg.strip())
        if parts:
            return " ".join(parts)

    return ""


def unwrap_conversations(data: Any, source_name: str = "input") -> List[Dict[str, Any]]:
    """解包并验证 JSON 数据，支持纯列表或多种外层包装信封对象。"""
    if isinstance(data, dict):
        for envelope_key in ("conversations", "items", "data", "results"):
            candidate = data.get(envelope_key)
            if isinstance(candidate, list):
                data = candidate
                break

    if not isinstance(data, list):
        raise ValueError(
            f"{source_name}: expected a JSON array or envelope object containing 'conversations', 'items', 'data', or 'results'"
        )

    conversations: List[Dict[str, Any]] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"{source_name}: conversation at index {idx} must be a JSON object, got {type(item).__name__}")
        conversations.append(item)

    return conversations


def validate_destination_path(destination: str, force: bool = False) -> Path:
    """验证目标文件路径安全性，防御路径遍历攻击与意外覆盖。"""
    path = Path(destination)
    if ".." in path.parts:
        raise ValueError(f"Output path {destination!r} contains '..'; refusing to write outside intended directory.")

    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}. Use -f/--force to overwrite.")

    return path


def conversations_to_tsv_string(conversations: Iterable[Dict[str, Any]]) -> str:
    """将对话列表格式化为符合严格单行契约的 TSV 字符串。"""
    output = io.StringIO()
    # 写入首行表头
    output.write("\t".join(FIELDS) + "\n")

    for item in conversations:
        structured = item.get("structured")
        if not isinstance(structured, dict):
            structured = {}

        conv_id = item.get("id") or ""
        started_at = item.get("started_at") or item.get("created_at") or ""
        title = structured.get("title") or item.get("title") or ""
        category = structured.get("category") or item.get("category") or ""
        source = item.get("source") or ""
        overview = structured.get("overview") or item.get("overview") or ""
        transcript = extract_transcript(item)

        row_values = [
            escape_tsv_field(conv_id),
            escape_tsv_field(started_at),
            escape_tsv_field(title),
            escape_tsv_field(category),
            escape_tsv_field(source),
            escape_tsv_field(overview),
            escape_tsv_field(transcript),
        ]
        output.write("\t".join(row_values) + "\n")

    return output.getvalue()


def convert(source: str, destination: Optional[str] = None, force: bool = False) -> str:
    """执行转换流程。若 destination 为 None 或 '-'，直接返回 TSV 字符串并可流式输出。"""
    # 1. 读取数据
    if source == "-":
        raw_text = sys.stdin.read()
        source_name = "<stdin>"
    else:
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw_text = source_path.read_text(encoding="utf-8").lstrip("\ufeff")
        source_name = str(source_path)

    # 2. 解析 JSON
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in {source_name}: {exc}") from exc

    # 3. 解包数据
    conversations = unwrap_conversations(data, source_name=source_name)

    # 4. 生成 TSV
    tsv_content = conversations_to_tsv_string(conversations)

    # 5. 输出
    if destination is None or destination == "-":
        return tsv_content

    dest_path = validate_destination_path(destination, force=force)
    # 创建父目录（若不存在）
    if dest_path.parent and not dest_path.parent.exists():
        dest_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入文件
    dest_path.write_text(tsv_content, encoding="utf-8")
    return tsv_content


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI 入口点。"""
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports into Tab-Separated Values (TSV) format."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file or '-' for stdin (default: '-')",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output TSV file or '-' for stdout (default: stdout if omitted)",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        dest="opt_output",
        help="Alternative flag to specify output TSV file",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file without confirmation",
    )

    args = parser.parse_args(argv)
    dest = args.opt_output or args.output

    try:
        result = convert(source=args.input, destination=dest, force=args.force)
        if dest is None or dest == "-":
            sys.stdout.write(result)
            sys.stdout.flush()
        return 0
    except Exception as exc:
        sys.stderr.write(f"TSV export failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
