"""Validate AI suggestions and write a small, controlled set of note metadata."""
from __future__ import annotations

import json
import re


CATEGORY_FOLDERS = {
    "inbox": "00_收集箱", "note": "01_知识笔记", "mistake": "02_错题本",
    "plan": "03_学习计划", "card": "04_复习卡片", "profile": "05_学习档案",
}
SUBJECTS = ("数学", "物理", "化学", "生物", "计算机", "英语", "医学", "经济管理", "人文社科", "综合")
CONTROLLED_FIELDS = {"category", "subject", "tags"}


def validate_classification(value: dict) -> dict:
    """Never accept a model-selected path or free-form metadata keys."""
    if not isinstance(value, dict):
        raise ValueError("分类结果须为 JSON 对象。")
    category, subject, tags = value.get("category"), value.get("subject"), value.get("tags")
    if not isinstance(category, str) or category not in CATEGORY_FOLDERS:
        raise ValueError("笔记类型不合法，请重新分类。")
    if not isinstance(subject, str) or subject not in SUBJECTS:
        raise ValueError("学科不合法，请重新分类。")
    if not isinstance(tags, list) or len(tags) > 5:
        raise ValueError("分类标签须为最多 5 个标签的列表。")
    clean_tags = []
    for tag in tags:
        if not isinstance(tag, str) or not re.fullmatch(r"[\w\u3400-\u9fff][\w\u3400-\u9fff-]{0,39}", tag):
            raise ValueError("分类标签须为 1 至 40 字的字母、数字、汉字、下划线或连字符。")
        if tag not in clean_tags:
            clean_tags.append(tag)
    reason = value.get("reason", "")
    if not isinstance(reason, str) or len(reason) > 300 or any(ord(c) < 32 for c in reason):
        raise ValueError("分类理由须为不超过 300 字的单行文本。")
    folder = CATEGORY_FOLDERS[category]
    if category != "profile":
        folder += "/" + subject
    return {"category": category, "subject": subject, "tags": clean_tags,
            "reason": reason.strip(), "folder": folder}


def parse_classification_output(output: str) -> dict:
    candidate = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", output.strip(), flags=re.I)
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("AI 返回的分类格式无法识别，请重新分类。") from exc
    if isinstance(parsed, dict) and "classification" in parsed:
        parsed = parsed["classification"]
    return validate_classification(parsed)


def frontmatter_parts(content: str) -> tuple[list[str] | None, str, str]:
    """Keep untouched YAML lines and the Markdown body, including line endings."""
    lines = content.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in content else "\n"
    if not lines or lines[0].strip() != "---":
        return None, content, newline
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError("笔记的 YAML 属性区缺少结束标记，请修正后再保存分类。")
    return lines[1:end], "".join(lines[end + 1:]), newline


def strip_controlled_fields(lines: list[str]) -> list[str]:
    retained = []
    skipping = False
    for line in lines:
        key = re.match(r"^(?:([\w-]+)|'([^']+)'|\"([^\"]+)\")\s*:", line)
        if key:
            name = next(item for item in key.groups() if item is not None)
            skipping = name in CONTROLLED_FIELDS
        if not skipping:
            retained.append(line)
    return retained


def apply_classification(content: str, value: dict) -> str:
    classification = validate_classification(value)
    lines, body, newline = frontmatter_parts(content)
    retained = strip_controlled_fields(lines or [])
    if retained and not retained[-1].endswith(("\r", "\n")):
        retained[-1] += newline
    attributes = ["category: " + classification["category"],
                  "subject: " + json.dumps(classification["subject"], ensure_ascii=False),
                  "tags: " + json.dumps(classification["tags"], ensure_ascii=False)]
    return ("---" + newline + "".join(retained) + newline.join(attributes) + newline +
            "---" + newline + body)


def extract_draft_classification(output: str) -> tuple[str, dict | None, list[str]]:
    """AI drafts stay reviewable when their optional metadata cannot be trusted."""
    warning = "AI 未返回有效的自动分类，请点击自动分类后检查笔记类型、学科和标签。"
    try:
        lines, body, newline = frontmatter_parts(output)
    except ValueError:
        return output, None, [warning]
    if lines is None:
        return output, None, [warning]
    values = {}
    active = None
    for line in lines:
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*?)\s*$", line)
        if match:
            active, value = match.groups()
            if active == "tags":
                if value.startswith("["):
                    try:
                        values[active] = json.loads(value)
                    except json.JSONDecodeError:
                        # YAML's unquoted inline list is common in model output.
                        if value.endswith("]"):
                            values[active] = [part.strip().strip("'\"") for part in value[1:-1].split(",") if part.strip()]
                        else:
                            values[active] = None
                elif not value or value == "[]":
                    values[active] = []
                else:
                    values[active] = None
            elif active in ("category", "subject"):
                values[active] = value.strip("'\"")
        elif active == "tags" and re.match(r"^\s+-\s+", line) and isinstance(values.get("tags"), list):
            values["tags"].append(re.sub(r"^\s+-\s+", "", line).strip().strip("'\""))
    retained = strip_controlled_fields(lines)
    clean_body = ("---" + newline + "".join(retained) + "---" + newline + body) if any(line.strip() for line in retained) else body
    try:
        return clean_body, validate_classification(values), []
    except ValueError:
        return clean_body, None, [warning]
