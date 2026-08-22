from ..base import MemoryProviderBase, logger
import hashlib
import json
import os
import re
import threading
import time
from typing import Any, Dict, List

from config.config_loader import get_project_dir
from config.manage_api_client import (
    generate_and_save_chat_summary,
    upsert_memory_profile,
)
from core.utils.util import check_model_key

TAG = __name__

SUPERBRAIN_FILES = {
    "profile": "profile.md",
    "semantic": "semantic_memory.json",
    "procedural": "procedural_memory.md",
    "index": "memory_index.json",
    "operations": "operation_log.jsonl",
}

MONTHLY_FILES = {
    "episodic": "episodic_memory.md",
    "relations": "relationship_graph.md",
}

DAILY_FILES = {"working": "working_memory.json"}

# v1曾将所有层级都放在用户根目录，保留这些名称用于无损迁移。
LEGACY_FILES = {
    "working": "working_memory.md",
    "episodic": "episodic_memory.md",
    "relations": "relationship_graph.json",
}

DEFAULT_MARKDOWN = {
    "profile": "",
    "procedural": "",
}

DEFAULT_WORKING_MEMORY = {
    "active_tasks": [],
    "pending_confirmations": [],
    "open_topics": [],
    "recent_dialogues": [],
}

superbrain_memory_prompt = """
你是 SuperBrain 长期记忆分析器。输入只属于当前硬件用户。深入分析连续对话，提炼对未来交流长期有价值的事实，并输出更新后的完整用户画像。

提炼姓名、称呼、职业、主要职业、居住地、祖籍、婚姻、子女、亲友关系、稳定偏好、长期目标、工作流程、表达习惯、常用工具和重要经历。
只记录用户明确说出或现有画像已确认的事实；助手回复不能作为事实来源。保留未被否定的旧信息，新信息纠正旧信息时以新信息为准。忽略寒暄、一次性问题、临时情绪和系统错误。
profile_md 汇总全部长期信息并使用结构清晰的 Markdown；其他字段填写对应精炼值，没有可靠内容时为 null。interests 可用逗号分隔。
所有字段名必须与 memory_profile 数据库列名完全一致。只能输出一个标准 JSON 对象，不要代码围栏、解释、注释或外层包装。

{
  "mac_address": "当前用户ID",
  "member_id": null,
  "username": null,
  "occupation": null,
  "primary_occupation": null,
  "interests": null,
  "favorite_role": null,
  "favorite_tv_show": null,
  "chinese_name": null,
  "english_name": null,
  "profile_md": "完整的长期用户画像 Markdown"
}
"""

superbrain_query_prompt = """
你是只读的 SuperBrain 记忆检索器。输入中的用户记忆库只属于当前设备用户。

严格规则：
1. 只能引用记忆库中明确存在且与当前消息直接相关的事实；不得猜测或使用模型自身记忆补全。
2. 不得把其他用户、外部摘要、示例文字或系统说明混入结果。
3. operation_log 只帮助判断更新时间；错误原因、校验信息和“未结构化会话”等系统诊断不是用户事实，禁止返回。
4. 优先级：未完成事项 > 明确身份与称呼 > 稳定偏好/关系/项目 > 历史事件。
5. status=stale、已过期或无关内容不返回。
6. 只输出最多 8 条简洁中文项目符号，不要标题、JSON或解释；没有可靠相关记忆时输出空字符串。
"""


def _extract_content(content):
    try:
        if content and content.strip().startswith("{") and content.strip().endswith("}"):
            data = json.loads(content)
            if "content" in data:
                return data["content"]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    return content


def _extract_json_payload(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    raw = text.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
    return {}


def _as_markdown(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value if item is not None).strip()
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value).strip()


def _as_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _as_working_memory(value: Any) -> Dict[str, List[str]]:
    result = {key: [] for key in DEFAULT_WORKING_MEMORY}
    if not isinstance(value, dict):
        return result
    for key in result:
        items = value.get(key, [])
        if isinstance(items, list):
            result[key] = [str(item).strip() for item in items if str(item).strip()]
        elif items is not None and str(items).strip():
            result[key] = [str(items).strip()]
    return result


class MemoryProvider(MemoryProviderBase):
    def __init__(self, config, summary_memory=None):
        super().__init__(config)
        self.memory_text = ""
        self.save_to_file = True
        self.memory_root = os.path.join(get_project_dir(), ".superbrain_mem")
        self.user_id = None
        self.user_memory_dir = None
        self.bootstrap_summary_memory = summary_memory or ""
        self._save_lock = threading.Lock()
        self._last_saved_dialogue_hash = None

    def init_memory(self, role_id, llm, summary_memory=None, save_to_file=True, **kwargs):
        super().init_memory(role_id, llm, **kwargs)
        self.save_to_file = save_to_file
        self.bootstrap_summary_memory = summary_memory or self.bootstrap_summary_memory
        self.user_id = self._safe_user_id(role_id)
        self.user_memory_dir = self._resolve_user_memory_dir(self.user_id)
        self._ensure_user_memory_dir()
        self.load_memory()

    def _safe_user_id(self, user_id) -> str:
        raw = str(user_id or "unknown_user").strip()
        safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", raw).lower()
        safe = safe.strip("._") or "unknown_user"
        return safe[:120]

    def _compact_user_id(self, user_id) -> str:
        return re.sub(r"[^a-zA-Z0-9]", "", str(user_id or "")).lower()

    def _resolve_user_memory_dir(self, user_id: str) -> str:
        """Resolve historical user directories even if device-id format changes."""
        os.makedirs(self.memory_root, exist_ok=True)
        target_safe = self._safe_user_id(user_id)
        target_compact = self._compact_user_id(user_id)

        for entry in os.listdir(self.memory_root):
            candidate = os.path.join(self.memory_root, entry)
            if not os.path.isdir(candidate):
                continue
            if entry == target_safe:
                return candidate
            if self._compact_user_id(entry) == target_compact:
                self.user_id = entry
                return candidate

            index_path = os.path.join(candidate, SUPERBRAIN_FILES["index"])
            index_data = self._read_json(index_path, {})
            indexed_user_id = index_data.get("user_id") if isinstance(index_data, dict) else ""
            if indexed_user_id and self._compact_user_id(indexed_user_id) == target_compact:
                self.user_id = entry
                return candidate

        return os.path.join(self.memory_root, target_safe)

    def _refresh_user_dir_from_role(self):
        if not self.role_id:
            return
        safe_user_id = self._safe_user_id(self.role_id)
        if self.user_id != safe_user_id or not self.user_memory_dir:
            self.user_id = safe_user_id
            self.user_memory_dir = self._resolve_user_memory_dir(self.user_id)

    def _ensure_user_memory_dir(self):
        self._refresh_user_dir_from_role()
        if not self.user_memory_dir:
            self.user_id = self._safe_user_id(self.role_id)
            self.user_memory_dir = self._resolve_user_memory_dir(self.user_id)

        os.makedirs(self.user_memory_dir, exist_ok=True)
        for key, filename in SUPERBRAIN_FILES.items():
            path = os.path.join(self.user_memory_dir, filename)
            if os.path.exists(path):
                continue
            if key in DEFAULT_MARKDOWN:
                self._write_text(path, DEFAULT_MARKDOWN[key])
            elif key == "semantic":
                self._write_json(path, [])
            elif key == "index":
                self._write_json(
                    path,
                    {
                        "user_id": self.user_id,
                        "created_at": self._now(),
                        "updated_at": self._now(),
                        "memory_version": "superbrain_native.v2",
                    },
                )
            elif key == "operations":
                self._write_text(path, "")

        month_dir = self._month_dir()
        day_dir = self._day_dir()
        os.makedirs(month_dir, exist_ok=True)
        os.makedirs(day_dir, exist_ok=True)
        for filename in MONTHLY_FILES.values():
            path = os.path.join(month_dir, filename)
            if not os.path.exists(path):
                self._write_text(path, "")
        working_path = os.path.join(day_dir, DAILY_FILES["working"])
        if not os.path.exists(working_path):
            self._write_json(working_path, DEFAULT_WORKING_MEMORY)
        self._migrate_legacy_layout()

    def _path(self, key: str) -> str:
        self._ensure_user_memory_dir()
        return os.path.join(self.user_memory_dir, SUPERBRAIN_FILES[key])

    def _month_key(self, timestamp=None) -> str:
        return time.strftime("%Y-%m", time.localtime(timestamp))

    def _day_key(self, timestamp=None) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(timestamp))

    def _month_dir(self, month=None) -> str:
        return os.path.join(self.user_memory_dir, month or self._month_key())

    def _day_dir(self, day=None) -> str:
        return os.path.join(self.user_memory_dir, day or self._day_key())

    def _monthly_path(self, key: str, month=None) -> str:
        return os.path.join(self._month_dir(month), MONTHLY_FILES[key])

    def _daily_path(self, key: str, day=None) -> str:
        return os.path.join(self._day_dir(day), DAILY_FILES[key])

    def _migrate_legacy_layout(self):
        """Copy v1 root-level memories into the current v2 period directories once."""
        if not self.user_memory_dir:
            return
        index_path = os.path.join(self.user_memory_dir, SUPERBRAIN_FILES["index"])
        index = self._read_json(index_path, {})
        if index.get("legacy_layout_migrated"):
            return
        episodic_target = self._monthly_path("episodic")
        relations_target = self._monthly_path("relations")
        working_target = self._daily_path("working")

        legacy_episode = os.path.join(self.user_memory_dir, LEGACY_FILES["episodic"])
        if not self._read_text(episodic_target).strip() and os.path.exists(legacy_episode):
            self._write_text(episodic_target, self._read_text(legacy_episode).strip())

        legacy_relations = os.path.join(self.user_memory_dir, LEGACY_FILES["relations"])
        if not self._read_text(relations_target).strip() and os.path.exists(legacy_relations):
            relations = self._read_json(legacy_relations, [])
            self._write_text(relations_target, _as_markdown(relations))

        legacy_working = os.path.join(self.user_memory_dir, LEGACY_FILES["working"])
        current_working = self._read_json(working_target, DEFAULT_WORKING_MEMORY)
        if (
            current_working == DEFAULT_WORKING_MEMORY
            and os.path.exists(legacy_working)
            and self._read_text(legacy_working).strip()
        ):
            migrated = dict(DEFAULT_WORKING_MEMORY)
            migrated["open_topics"] = [self._read_text(legacy_working).strip()]
            self._write_json(working_target, migrated)
        index.update(
            {
                "memory_version": "superbrain_native.v2",
                "legacy_layout_migrated": True,
                "legacy_layout_migrated_at": self._now(),
            }
        )
        self._write_json(index_path, index)

    def _now(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def _read_text(self, path: str) -> str:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def _write_text(self, path: str, content: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content or "")
        os.replace(tmp_path, path)

    def _read_json(self, path: str, default):
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if data is not None else default
        except Exception as e:
            logger.bind(tag=TAG).warning(f"读取SuperBrain JSON失败: {path}, {e}")
            return default

    def _memory_file_debug_info(self) -> Dict[str, Any]:
        self._ensure_user_memory_dir()
        files = {}
        for key, filename in SUPERBRAIN_FILES.items():
            path = os.path.join(self.user_memory_dir, filename)
            files[key] = {
                "path": path,
                "exists": os.path.exists(path),
                "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            }
        for key in MONTHLY_FILES:
            path = self._monthly_path(key)
            files[f"monthly_{key}"] = {
                "path": path,
                "exists": os.path.exists(path),
                "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
            }
        path = self._daily_path("working")
        files["daily_working"] = {
            "path": path,
            "exists": os.path.exists(path),
            "bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        }
        return {
            "user_id": self.user_id,
            "role_id": self.role_id,
            "memory_dir": self.user_memory_dir,
            "files": files,
        }

    def _write_json(self, path: str, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)

    def _append_operation_log(self, operations: List[Dict[str, Any]], reason: str):
        if not operations and not reason:
            return
        path = self._path("operations")
        with open(path, "a", encoding="utf-8") as f:
            if operations:
                for operation in operations:
                    record = dict(operation)
                    record.setdefault("created_at", self._now())
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            elif reason:
                f.write(
                    json.dumps(
                        {
                            "created_at": self._now(),
                            "operation": "none",
                            "reason": reason,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def _bootstrap_summary(self):
        # summaryMemory没有设备归属证明，禁止写入按MAC隔离的SuperBrain目录。
        return

    def load_memory(self, summary_memory=None):
        if not self.role_id:
            self.memory_text = ""
            return
        self._ensure_user_memory_dir()
        self.memory_text = self._compose_memory_context(include_working=True)

    def _load_sections(self) -> Dict[str, Any]:
        self._ensure_user_memory_dir()
        monthly = self._load_period_memories(MONTHLY_FILES, limit=6)
        daily = self._load_period_memories(DAILY_FILES, limit=30, json_keys={"working"})
        sections = {
            "profile": self._read_text(self._path("profile")).strip(),
            "semantic": self._read_json(self._path("semantic"), []),
            "procedural": self._read_text(self._path("procedural")).strip(),
            "monthly": monthly,
            "daily": daily,
            "recent_operations": self._read_recent_operations(limit=5),
        }
        logger.bind(tag=TAG).debug(
            "SuperBrain加载用户记忆文件: "
            + json.dumps(
                {
                    **self._memory_file_debug_info(),
                    "loaded": {
                        "profile_chars": len(sections["profile"]),
                        "semantic_count": len(sections["semantic"]),
                        "procedural_chars": len(sections["procedural"]),
                        "monthly_period_count": len(sections["monthly"]),
                        "daily_period_count": len(sections["daily"]),
                        "recent_operations_count": len(sections["recent_operations"]),
                    },
                },
                ensure_ascii=False,
            )
        )
        return sections

    def _load_period_memories(
        self, file_map: Dict[str, str], limit: int, json_keys=None
    ) -> List[Dict[str, Any]]:
        """Load newest dated directories without mixing snapshots across tiers."""
        json_keys = json_keys or set()
        if not self.user_memory_dir or not os.path.isdir(self.user_memory_dir):
            return []
        if file_map is MONTHLY_FILES:
            pattern = re.compile(r"^\d{4}-\d{2}$")
            date_format = "%Y-%m"
            max_age_days = 190
        else:
            pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
            date_format = "%Y-%m-%d"
            max_age_days = 31
        now = time.time()

        def is_recent_period(name: str) -> bool:
            try:
                period_time = time.mktime(time.strptime(name, date_format))
                age_days = (now - period_time) / 86400
                return -1 <= age_days <= max_age_days
            except ValueError:
                return False

        period_names = sorted(
            (
                name
                for name in os.listdir(self.user_memory_dir)
                if pattern.match(name)
                and is_recent_period(name)
                and os.path.isdir(os.path.join(self.user_memory_dir, name))
            ),
            reverse=True,
        )[:limit]
        result = []
        for period in period_names:
            values = {"period": period}
            has_content = False
            for key, filename in file_map.items():
                path = os.path.join(self.user_memory_dir, period, filename)
                if key in json_keys:
                    value = self._read_json(path, DEFAULT_WORKING_MEMORY)
                    if value != DEFAULT_WORKING_MEMORY:
                        has_content = True
                else:
                    value = self._read_text(path).strip()
                    if value:
                        has_content = True
                values[key] = value
            if has_content:
                result.append(values)
        return result

    def _read_recent_operations(self, limit=5) -> List[Dict[str, Any]]:
        path = self._path("operations")
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f.readlines() if line.strip()]
            operations = []
            for line in lines[-limit:]:
                try:
                    operations.append(json.loads(line))
                except json.JSONDecodeError:
                    operations.append({"raw": line})
            return operations
        except Exception as e:
            logger.bind(tag=TAG).warning(f"读取SuperBrain操作日志失败: {e}")
            return []

    def _compose_memory_context(self, include_working=False) -> str:
        sections = self._load_sections()
        parts = []
        if sections["profile"]:
            parts.append(f"## 用户画像\n{sections['profile']}")
        if include_working and sections["daily"]:
            parts.append(
                "## 短期记忆（日目录，按日期倒序）\n"
                + json.dumps(sections["daily"], ensure_ascii=False, indent=2)
            )
        if sections["monthly"]:
            parts.append(
                "## 中期记忆（月目录，按月份倒序）\n"
                + json.dumps(sections["monthly"], ensure_ascii=False, indent=2)
            )
        if sections["semantic"]:
            parts.append(
                "## 语义记忆\n"
                + json.dumps(sections["semantic"], ensure_ascii=False, indent=2)
            )
        if sections["procedural"]:
            parts.append(f"## 流程习惯记忆\n{sections['procedural']}")
        if sections["recent_operations"]:
            parts.append(
                "## 最近记忆操作\n"
                + json.dumps(sections["recent_operations"], ensure_ascii=False, indent=2)
            )
        return "\n\n".join(parts).strip()

    def _build_dialogue_text(self, msgs) -> str:
        lines = []
        for msg in msgs[-40:]:
            if msg.role in ("system", "tool"):
                continue
            content = _extract_content(msg.content)
            if content is None:
                continue
            if msg.role == "user":
                lines.append(f"User: {content}")
            elif msg.role == "assistant":
                lines.append(f"Assistant: {content}")
        return "\n".join(lines)

    def _record_dialogue_snapshots(self, msgs):
        """Persist short/mid-term conversation history without relying on LLM JSON."""
        latest = []
        seen_assistant = False
        for msg in reversed(msgs):
            if msg.role not in ("user", "assistant"):
                continue
            content = _extract_content(msg.content)
            if not content:
                continue
            if msg.role == "assistant" and not seen_assistant:
                latest.append(f"Assistant: {content}")
                seen_assistant = True
            elif msg.role == "user" and seen_assistant:
                latest.append(f"User: {content}")
                break
        if len(latest) < 2:
            return
        excerpt = "\n".join(reversed(latest))[-2000:].strip()
        daily_path = self._daily_path("working")
        working = self._read_json(daily_path, DEFAULT_WORKING_MEMORY)
        working = _as_working_memory(working)
        recent = working.setdefault("recent_dialogues", [])
        if not recent or recent[-1] != excerpt:
            recent.append(excerpt)
        working["recent_dialogues"] = recent[-20:]
        self._write_json(daily_path, working)

        monthly_path = self._monthly_path("episodic")
        current = self._read_text(monthly_path).strip()
        entry = f"## 对话记录 - {self._now()}\n{excerpt}"
        if entry not in current:
            self._write_text(monthly_path, f"{entry}\n\n{current}".strip())

    def _apply_profile_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Persist the complete long-term profile returned by the memory LLM."""
        existing = self._read_json(self._path("semantic"), {})
        if not isinstance(existing, dict):
            existing = {}
        existing.setdefault("profile_md", self._read_text(self._path("profile")).strip())

        def updated_value(key):
            value = payload.get(key)
            value = value if value not in (None, "") else existing.get(key)
            if isinstance(value, list):
                return ", ".join(str(item) for item in value if str(item).strip()) or None
            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)
            return str(value).strip() if value not in (None, "") else None

        profile = {
            "mac_address": str(self.role_id),
            "member_id": updated_value("member_id"),
            "username": updated_value("username"),
            "occupation": updated_value("occupation"),
            "primary_occupation": updated_value("primary_occupation"),
            "interests": updated_value("interests"),
            "favorite_role": updated_value("favorite_role"),
            "favorite_tv_show": updated_value("favorite_tv_show"),
            "chinese_name": updated_value("chinese_name"),
            "english_name": updated_value("english_name"),
            "profile_md": _as_markdown(updated_value("profile_md")),
        }
        if profile["profile_md"]:
            self._write_text(self._path("profile"), profile["profile_md"])
        self._write_json(self._path("semantic"), profile)
        index = self._read_json(self._path("index"), {})
        index.update({
            "user_id": self.user_id,
            "updated_at": self._now(),
            "memory_version": "superbrain_native.v3",
            "current_month": self._month_key(),
            "current_day": self._day_key(),
            "last_operation": "profile_upsert",
        })
        self._write_json(self._path("index"), index)
        return profile

    async def save_memory(self, msgs, session_id=None):
        # 同一设备连续回复可能启动多个后台保存线程，串行化可避免旧快照后写覆盖新快照。
        with self._save_lock:
            dialogue_text = self._build_dialogue_text(msgs)
            dialogue_hash = hashlib.sha256(dialogue_text.encode("utf-8")).hexdigest()
            if dialogue_text and dialogue_hash == self._last_saved_dialogue_hash:
                logger.bind(tag=TAG).debug(
                    f"跳过重复SuperBrain快照 - User: {self.user_id}, Session: {session_id}"
                )
                return self.memory_text
            result = await self._save_memory_locked(msgs, session_id)
            if dialogue_text:
                # 即使模型失败，_save_memory_locked也已将原始对话写入中期保底记录。
                self._last_saved_dialogue_hash = dialogue_hash
            return result

    async def _save_memory_locked(self, msgs, session_id=None):
        model_info = getattr(
            self.llm, "model_name", self.llm.__class__.__name__ if self.llm else "未设置"
        )
        logger.bind(tag=TAG).debug(f"SuperBrain使用记忆模型: {model_info}")

        if self.llm is None:
            logger.bind(tag=TAG).error("LLM is not set for SuperBrain memory provider")
            return None

        api_key = getattr(self.llm, "api_key", None)
        memory_key_msg = check_model_key("SuperBrain记忆专用LLM", api_key)
        if memory_key_msg:
            logger.bind(tag=TAG).error(memory_key_msg)

        if len(msgs) < 2:
            return self.memory_text

        self._ensure_user_memory_dir()
        dialogue_text = self._build_dialogue_text(msgs)
        if not dialogue_text:
            return self.memory_text
        self._record_dialogue_snapshots(msgs)

        current_profile = self._read_json(self._path("semantic"), {})
        if not isinstance(current_profile, dict):
            current_profile = {}
        current_profile_md = self._read_text(self._path("profile")).strip()
        time_str = self._now()
        llm_input = (
            f"当前用户ID（mac_address）：{self.role_id}\n"
            f"当前时间：{time_str}\n\n"
            "# 现有长期画像JSON\n"
            f"{json.dumps(current_profile, ensure_ascii=False, indent=2)}\n\n"
            f"# 现有profile_md\n{current_profile_md or '无'}\n\n"
            f"# 最新对话\n{dialogue_text}"
        )

        try:
            result = self.llm.response_no_stream(
                superbrain_memory_prompt,
                llm_input,
                max_tokens=2200,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            payload = _extract_json_payload(result)
            if not payload:
                raise ValueError("SuperBrain LLM未返回长期画像JSON")
            profile = self._apply_profile_update(payload)
            if profile["profile_md"]:
                await upsert_memory_profile(profile)
            self.memory_text = self._compose_memory_context(include_working=True)
            logger.bind(tag=TAG).info(
                f"SuperBrain memory saved - User: {self.user_id}, Session: {session_id}"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"Error in saving SuperBrain memory: {e}")
            self.memory_text = self._compose_memory_context(include_working=True)

        if not self.save_to_file:
            try:
                summary_id = session_id if session_id else self.role_id
                await generate_and_save_chat_summary(summary_id)
            except Exception as e:
                logger.bind(tag=TAG).warning(f"SuperBrain远端摘要触发失败: {e}")

        return self.memory_text

    async def query_memory(self, query: str) -> str:
        if not self.role_id:
            logger.bind(tag=TAG).warning("SuperBrain query skipped: role_id is empty")
            return ""
        self.load_memory()
        self._ensure_user_memory_dir()
        memory_context = self._compose_memory_context(include_working=True)
        logger.bind(tag=TAG).debug(
            "SuperBrain query_memory读取结果: "
            + json.dumps(
                {
                    "user_id": self.user_id,
                    "role_id": self.role_id,
                    "memory_dir": self.user_memory_dir,
                    "query": _extract_content(query) or query,
                    "memory_context_chars": len(memory_context),
                    "has_memory": bool(memory_context),
                },
                ensure_ascii=False,
            )
        )
        if not memory_context:
            logger.bind(tag=TAG).info(
                f"SuperBrain query found no memory - User: {self.user_id}, Dir: {self.user_memory_dir}"
            )
            return ""

        query_text = _extract_content(query) or query
        if self.llm is None:
            return f"【SuperBrain记忆】\n{memory_context}"

        try:
            result = self.llm.response_no_stream(
                superbrain_query_prompt,
                f"当前用户消息：{query_text}\n\n# 用户记忆库\n{memory_context}",
                max_tokens=1200,
                temperature=0.1,
            )
            relevant_memory = (result or "").strip()
            if not relevant_memory:
                logger.bind(tag=TAG).info(
                    f"SuperBrain query refinement returned empty, using full memory - User: {self.user_id}, Dir: {self.user_memory_dir}"
                )
                return f"【SuperBrain记忆】\n{memory_context}"
            logger.bind(tag=TAG).debug(
                "SuperBrain query_memory提炼完成: "
                + json.dumps(
                    {
                        "user_id": self.user_id,
                        "memory_context_chars": len(memory_context),
                        "relevant_memory_chars": len(relevant_memory),
                    },
                    ensure_ascii=False,
                )
            )
            return f"【SuperBrain记忆】\n{relevant_memory}"
        except Exception as e:
            logger.bind(tag=TAG).warning(f"SuperBrain记忆检索提炼失败，使用完整记忆: {e}")
            return f"【SuperBrain记忆】\n{memory_context}"
