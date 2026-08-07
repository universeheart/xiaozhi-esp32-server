from ..base import MemoryProviderBase, logger
import json
import os
import re
import time
from typing import Any, Dict, List

from config.config_loader import get_project_dir
from config.manage_api_client import generate_and_save_chat_summary
from core.utils.util import check_model_key

TAG = __name__

SUPERBRAIN_FILES = {
    "profile": "profile.md",
    "working": "working_memory.md",
    "episodic": "episodic_memory.md",
    "semantic": "semantic_memory.json",
    "procedural": "procedural_memory.md",
    "relations": "relationship_graph.json",
    "index": "memory_index.json",
    "operations": "operation_log.jsonl",
}

DEFAULT_MARKDOWN = {
    "profile": "",
    "working": "",
    "episodic": "",
    "procedural": "",
}

superbrain_memory_prompt = """
# SuperBrain 记忆中枢

你是后台记忆整理器，不是聊天助手。你的任务是根据“现有记忆”和“最新对话”，为同一个用户维护一个可长期演进的个人 Wiki 记忆库。为了确保记忆的时效性和权重管理，记忆将被映射到不同的时间维度的文件目录中。

## 核心目标
- 捕捉对未来对话有帮助的中长期信息，并按时间权重进行路由分发。
- 将新信息严格按“短期（日）”、“中期（月）”、“长期（全局）”的目录结构分类归档，保留稳定事实、偏好、关系、项目、流程习惯和待跟进事项。
- 如果新信息修正旧信息，保留旧信息的历史痕迹并标记为 stale，不要直接删除。
- 忽略一次性寒暄、临时情绪、无后续价值的普通闲聊。
- 极度关注核心身份特征：用户本人及其提及的家人、亲戚、好友、同事的名字、职业、婚姻状况、工作与子女信息，这些必须被视为高优先级长期记忆。

## 记忆分层与存储架构
你的输出将被后端系统物理持久化到用户 ID 下的不同目录中，请根据以下架构理解记忆的时效与权重：

### 1. 长期记忆 (Long-term / 根目录)
这些信息伴随用户的整个生命周期，权重最高，存放于用户目录根节点：
- **profile.md (画像记忆)**：提炼用户的身份、喜好、关注领域、居住地、祖籍、婚姻状况、父母（及配偶父母）、是否有孩子等个人信息。必须同时记录关系极近的亲朋好友的身份、职业、子女等重要情报。**绝对不可编造或写入推测性误解信息。**
- **procedural_memory.md (流程记忆)**：记录用户的工作习惯、固定工作流、表达偏好、格式要求、决策习惯、协作方式及语言习惯。
- **semantic_memories (语义节点)**：跨会话的稳定事实（实体、工具、产品、长期目标等），以结构化数据存在。

### 2. 中期记忆 (Mid-term / 月份子目录 `YYYY-MM/`)
这些信息在当前时间段内权重极高，但随着事件结束或时间推移会被逐步归档降权：
- **episodic_memory.md (情景记忆)**：按时间倒序或分段沉淀的会话摘要、阶段性事件、中短期项目推进记录。避免流水账。
- **relationship_graph.md (关系图谱)**：实体、人物、项目之间的关联脉络（如“用户-开发-项目A”）。随月份演进记录当月的核心社交与事物关系网络。

### 3. 短期记忆 (Short-term / 日期子目录 `YYYY-MM-DD/`)
- **working_memory.json (工作记忆)**：当前、近2周至1个月内的短期上下文、尚未完成的临时任务、每日琐碎安排、待确认事项或未完结的话题。过期内容应被你清空，或提取有价值部分升级合并到中期/长期记忆中。

## 记忆评估
每次更新必须同时考虑：
- **时效路由**：信息是该放入今日的 working memory，还是沉淀到当月的 episodic，或是永久写入根目录的 profile。
- **情感强度**：用户是否反复强调、明确偏好、强烈满意或不满（此类多入档长期记忆）。
- **关联密度**：是否能和已有实体、项目、习惯、长期目标建立连接。

## 更新规则
1. 只记录用户明确表达或可稳定推断的信息，**严禁任何形式的编造**。
2. `profile_md` 和 `procedural_md` 必须维护一份结构清晰的完整 Markdown 快照。
3. `episodic_md` 采用精炼的要点总结，关注“事件进展”而非“聊天记录”。
4. `working_memory_json` 只保留当下依然活跃的临时事项，一旦判断任务结束或话题失去时效性，立即从该字段中剔除。

## 输出要求
只输出一个 JSON 对象，不要 Markdown 代码块包裹（或确保可以被标准 JSON 解析器解析），不要解释处理过程。所有字段必须输出“更新后的完整快照”，不要只给增量。

JSON Schema 结构如下（后端将根据 Key 自动路由保存至对应目录）：

{
  "should_update": true,
  "memory_operation": "none | ingest | supersede | reinforce | crystallize",
  "reason": "简述判断需要或不需要更新的依据",
  
  "//_ROOT_DIRECTORY_//": "以下字段将保存至用户根目录",
  "profile_md": "用户及亲友画像完整快照，Markdown 文本",
  "procedural_md": "工作与表达习惯记忆完整快照，Markdown 文本",
  "semantic_memories": [
    {
      "entity": "实体名称",
      "type": "person | project | preference | fact | goal | task | tool | other",
      "content": "可注入提示词的简洁事实",
      "status": "active | stale",
      "confidence": 0.0,
      "updated_at": "YYYY-MM-DD HH:mm:ss",
      "evidence": "来自本轮或历史对话的依据",
      "supersedes": "被取代的旧实体信息"
    }
  ],

  "//_MONTHLY_DIRECTORY_//": "以下字段将保存至当月目录 [YYYY-MM]",
  "episodic_md": "情景记忆与项目进度完整快照，Markdown 文本",
  "relationship_graph_md": "实体及人物关系图谱，Markdown 文本（建议使用列表或 Mermaid 语法表达关系）",

  "//_DAILY_DIRECTORY_//": "以下字段将保存至当日目录 [YYYY-MM-DD]",
  "working_memory_json": {
    "active_tasks": ["短期任务1", "短期任务2"],
    "pending_confirmations": ["待确认事项1"],
    "open_topics": ["未聊完的上下文段落摘要"]
  },

  "operations_log": [
    {
      "operation": "ingest | supersede | reinforce | crystallize",
      "tier": "working | episodic | semantic | procedural | profile",
      "entity": "实体或事件名称",
      "confidence_change": "+0.1",
      "reason": "执行原因，例如：将过期的短期任务归档至情景记忆"
    }
  ]
}
"""

superbrain_query_prompt = """
你是 SuperBrain 记忆检索器。请从用户的记忆库中挑选与当前用户消息最相关、最应该注入回复提示词的内容。

要求：
- 加载对应用户的中长期记忆(profile, relationship_graph, semantic, working etc.)，并从log里读取最近五条记录帮助短期记忆的衔接
- 只返回对本轮回复有帮助的记忆。
- 保留用户偏好、项目背景、流程习惯、待跟进事项。
- 忽略无关或过时内容，除非过时信息能解释当前上下文。
- 输出简洁中文项目符号，不要 JSON，不要解释检索过程。
- 如果没有相关记忆，返回空字符串。
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


class MemoryProvider(MemoryProviderBase):
    def __init__(self, config, summary_memory=None):
        super().__init__(config)
        self.memory_text = ""
        self.save_to_file = True
        self.memory_root = os.path.join(get_project_dir(), ".superbrain_mem")
        self.user_id = None
        self.user_memory_dir = None
        self.bootstrap_summary_memory = summary_memory or ""

    def init_memory(self, role_id, llm, summary_memory=None, save_to_file=True, **kwargs):
        super().init_memory(role_id, llm, **kwargs)
        self.save_to_file = save_to_file
        self.bootstrap_summary_memory = summary_memory or self.bootstrap_summary_memory
        self.user_id = self._safe_user_id(role_id)
        self.user_memory_dir = self._resolve_user_memory_dir(self.user_id)
        self._ensure_user_memory_dir()
        self._bootstrap_summary()
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
            elif key in ("semantic", "relations"):
                self._write_json(path, [])
            elif key == "index":
                self._write_json(
                    path,
                    {
                        "user_id": self.user_id,
                        "created_at": self._now(),
                        "updated_at": self._now(),
                        "memory_version": "superbrain_native.v1",
                    },
                )
            elif key == "operations":
                self._write_text(path, "")

    def _path(self, key: str) -> str:
        self._ensure_user_memory_dir()
        return os.path.join(self.user_memory_dir, SUPERBRAIN_FILES[key])

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
        if not self.bootstrap_summary_memory:
            return
        episodic_path = self._path("episodic")
        current = self._read_text(episodic_path).strip()
        if current:
            return
        imported = (
            f"## 外部摘要导入 - {self._now()}\n"
            f"{self.bootstrap_summary_memory.strip()}\n"
        )
        self._write_text(episodic_path, imported)

    def load_memory(self, summary_memory=None):
        if summary_memory:
            self.bootstrap_summary_memory = summary_memory
        if not self.role_id:
            self.memory_text = self.bootstrap_summary_memory or ""
            return
        self._ensure_user_memory_dir()
        self._bootstrap_summary()
        self.memory_text = self._compose_memory_context(include_working=True)

    def _load_sections(self) -> Dict[str, Any]:
        self._ensure_user_memory_dir()
        sections = {
            "profile": self._read_text(self._path("profile")).strip(),
            "working": self._read_text(self._path("working")).strip(),
            "episodic": self._read_text(self._path("episodic")).strip(),
            "semantic": self._read_json(self._path("semantic"), []),
            "procedural": self._read_text(self._path("procedural")).strip(),
            "relations": self._read_json(self._path("relations"), []),
            "recent_operations": self._read_recent_operations(limit=5),
        }
        logger.bind(tag=TAG).debug(
            "SuperBrain加载用户记忆文件: "
            + json.dumps(
                {
                    **self._memory_file_debug_info(),
                    "loaded": {
                        "profile_chars": len(sections["profile"]),
                        "working_chars": len(sections["working"]),
                        "episodic_chars": len(sections["episodic"]),
                        "semantic_count": len(sections["semantic"]),
                        "procedural_chars": len(sections["procedural"]),
                        "relations_count": len(sections["relations"]),
                        "recent_operations_count": len(sections["recent_operations"]),
                    },
                },
                ensure_ascii=False,
            )
        )
        return sections

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
        if include_working and sections["working"]:
            parts.append(f"## 工作记忆\n{sections['working']}")
        if sections["episodic"]:
            parts.append(f"## 情景记忆\n{sections['episodic']}")
        if sections["semantic"]:
            parts.append(
                "## 语义记忆\n"
                + json.dumps(sections["semantic"], ensure_ascii=False, indent=2)
            )
        if sections["procedural"]:
            parts.append(f"## 流程习惯记忆\n{sections['procedural']}")
        if sections["relations"]:
            parts.append(
                "## 关系图谱\n"
                + json.dumps(sections["relations"], ensure_ascii=False, indent=2)
            )
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

    def _fallback_append_episode(self, dialogue_text: str, reason: str):
        if not dialogue_text:
            return
        path = self._path("episodic")
        current = self._read_text(path).strip()
        entry = (
            f"## 未结构化会话记录 - {self._now()}\n"
            f"原因：{reason}\n"
            f"{dialogue_text[-2000:]}\n"
        )
        self._write_text(path, f"{entry}\n\n{current}".strip())
        self._append_operation_log(
            [
                {
                    "operation": "ingest",
                    "tier": "episodic",
                    "entity": "未结构化会话",
                    "confidence_change": "unknown",
                    "reason": reason,
                }
            ],
            reason,
        )

    def _apply_memory_update(self, payload: Dict[str, Any]):
        should_update = payload.get("should_update", True)
        reason = str(payload.get("reason", "")).strip()
        if should_update is False:
            self._append_operation_log([], reason)
            return

        self._write_text(self._path("profile"), _as_markdown(payload.get("profile_md")))
        self._write_text(self._path("working"), _as_markdown(payload.get("working_md")))
        self._write_text(self._path("episodic"), _as_markdown(payload.get("episodic_md")))
        self._write_text(
            self._path("procedural"), _as_markdown(payload.get("procedural_md"))
        )

        semantic_memories = _as_list(payload.get("semantic_memories"))
        relationship_graph = _as_list(payload.get("relationship_graph"))
        self._write_json(self._path("semantic"), semantic_memories)
        self._write_json(self._path("relations"), relationship_graph)

        index = self._read_json(self._path("index"), {})
        index.update(
            {
                "user_id": self.user_id,
                "updated_at": self._now(),
                "memory_version": "superbrain_native.v1",
                "semantic_count": len(semantic_memories),
                "relationship_count": len(relationship_graph),
                "last_operation": payload.get("memory_operation", "none"),
            }
        )
        self._write_json(self._path("index"), index)
        self._append_operation_log(_as_list(payload.get("operations")), reason)

    async def save_memory(self, msgs, session_id=None):
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

        current_memory = self._compose_memory_context(include_working=True)
        time_str = self._now()
        llm_input = (
            f"当前用户ID：{self.user_id}\n"
            f"当前时间：{time_str}\n\n"
            f"# 现有记忆\n{current_memory or '无'}\n\n"
            f"# 最新对话\n{dialogue_text}"
        )

        try:
            result = self.llm.response_no_stream(
                superbrain_memory_prompt,
                llm_input,
                max_tokens=3500,
                temperature=0.1,
            )
            payload = _extract_json_payload(result)
            if not payload:
                raise ValueError("SuperBrain LLM未返回有效JSON")
            self._apply_memory_update(payload)
            self.memory_text = self._compose_memory_context(include_working=True)
            logger.bind(tag=TAG).info(
                f"SuperBrain memory saved - User: {self.user_id}, Session: {session_id}"
            )
        except Exception as e:
            logger.bind(tag=TAG).error(f"Error in saving SuperBrain memory: {e}")
            self._fallback_append_episode(dialogue_text, str(e))
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
