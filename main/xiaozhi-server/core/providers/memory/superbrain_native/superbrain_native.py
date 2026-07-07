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

你是后台记忆整理器，不是聊天助手。你的任务是根据“现有记忆”和“最新对话”，为同一个用户维护一个可长期演进的个人 Wiki 记忆库。

## 核心目标
- 捕捉对未来对话有帮助的中长期信息。
- 将新信息按记忆层级归档，保留稳定事实、偏好、关系、项目、流程习惯和待跟进事项。
- 如果新信息修正旧信息，保留旧信息的历史痕迹并标记为 stale，不要直接删除。
- 忽略一次性寒暄、临时情绪、无后续价值的普通闲聊。
- 着重关注用户的个人身份关键信息（职业，婚姻，社会身份，父母长辈，子女孩子等），以及对话中提及的家人，同事，好友的名字，职业，婚姻状况，工作状况，孩子信息（如果提及），都必须记录到长期记忆中

## 记忆分层
1. working_memory：当前及之前2周最远至1个月左右的会话的短期上下文、尚未完成的临时任务、待确认事项，或者是一些还没有聊完的话题。
2. episodic_memory：按时间沉淀的会话摘要、阶段性事件、项目推进记录。
3. semantic_memory：跨会话稳定事实，例如用户身份、项目、工具、偏好、人物、地点、产品、目标。
4. procedural_memory：用户固定工作流、表达偏好、格式要求、决策习惯、协作方式。
5. relationship_graph：实体之间的关系，例如“用户-正在开发-项目A”“项目A-使用-技术B”。
6. profile: 用户画像，身份，喜好，爱关注的领域，居住地，祖籍，婚姻状况，父母，是否有配偶父母，是否有孩子等等个人信息，进行多维度的画像重要特征记录，但是不要编造或者写入误解信息

## 记忆评估
每次更新必须同时考虑：
- 时效性：信息是否代表状态变化或近期计划。
- 情感强度：用户是否反复强调、明确偏好、强烈满意或不满。
- 关联密度：是否能和已有实体、项目、习惯、长期目标建立连接。

## 更新规则
- 只记录用户明确表达或可稳定推断的信息，不要编造
- profile 应该提炼用户的身份，喜好，爱关注的领域，居住地，祖籍，婚姻状况，父母，是否有配偶父母，是否有孩子等等个人信息，进行多维度的重要特征画像更新，但是不要编造或者写入误解信息。
- semantic_memory 使用结构化条目，必须包含 entity、type、content、status、confidence、updated_at、evidence。
- procedural_memory 用简洁中文维护完整快照，保留对后续回复有用的协作规则。
- episodic_memory 用时间倒序或分段摘要，避免流水账。
- working_memory 保留一段时间内仍然有用的短期上下文（2周至1个月左右，视一些对话的关联性动态灵活决定），过期内容应归档到 episodic_memory 或清空。
- relationship_graph 使用数组，每条包含 source、relation、target、confidence、updated_at。


## 输出要求
只输出一个 JSON 对象，不要 Markdown 代码块，不要解释处理过程。所有字段都要给出“更新后的完整快照”，不要只给增量。

JSON schema：
{
  "should_update": true,
  "memory_operation": "none | ingest | supersede | reinforce | crystallize",
  "reason": "为什么需要或不需要更新",
  "profile_md": "用户画像完整快照，Markdown 文本",
  "working_md": "工作记忆完整快照，Markdown 文本",
  "episodic_md": "情景记忆完整快照，Markdown 文本",
  "semantic_memories": [
    {
      "entity": "实体名称",
      "type": "person | project | preference | fact | goal | task | tool | other",
      "content": "可注入提示词的简洁事实",
      "status": "active | stale",
      "confidence": 0.0,
      "updated_at": "YYYY-MM-DD HH:mm:ss",
      "evidence": "来自本轮或历史对话的依据",
      "supersedes": ""
    }
  ],
  "procedural_md": "流程习惯记忆完整快照，Markdown 文本",
  "relationship_graph": [
    {
      "source": "实体A",
      "relation": "关系",
      "target": "实体B",
      "confidence": 0.0,
      "updated_at": "YYYY-MM-DD HH:mm:ss"
    }
  ],
  "operations": [
    {
      "operation": "ingest | supersede | reinforce | crystallize",
      "tier": "working | episodic | semantic | procedural",
      "entity": "实体名称",
      "confidence_change": "置信度变化",
      "reason": "执行原因"
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
