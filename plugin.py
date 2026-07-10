# -*- coding: utf-8 -*-
"""Ask-User Plugin — Backend Entry Point.

Tool registration happens inline during ``register()`` so it's available
BEFORE agents are initialized at app startup.  The ``_acting()`` patch
is applied immediately (class-level), and the REST API is registered
for user-answer submission.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from qwenpaw.plugins.api import PluginApi

from .question_service import get_question_service

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).parent.resolve()


# ══════════════════════════════════════════════════════════════════════
# REST API schemas
# ══════════════════════════════════════════════════════════════════════

class AnswerRequest(BaseModel):
    request_id: str = Field(..., description="Question request ID")
    session_id: str = Field(..., description="Session ID")
    answers: dict = Field(default_factory=dict, description="Question answers")
    other: str = Field(default="", description="Final 'other' field")


class SkipRequest(BaseModel):
    request_id: str = Field(..., description="Question request ID")
    session_id: str = Field(..., description="Session ID")


class AnswerResponse(BaseModel):
    success: bool
    message: str
    request_id: str


# ══════════════════════════════════════════════════════════════════════
# REST API router
# ══════════════════════════════════════════════════════════════════════

def build_router() -> APIRouter:
    router = APIRouter()
    svc = get_question_service()

    @router.post("/answer", response_model=AnswerResponse)
    async def submit_answer(body: AnswerRequest):
        """Submit answers to a pending question."""
        pq = await svc.get_request(body.request_id)
        if pq is None:
            raise HTTPException(status_code=404, detail="Question not found")
        if pq.session_id and body.session_id and pq.session_id != body.session_id:
            raise HTTPException(status_code=403, detail="Session mismatch")

        await svc.submit_answer(body.request_id, body.answers, body.other)
        return AnswerResponse(
            success=True,
            message=f"Question {body.request_id[:8]} answered",
            request_id=body.request_id,
        )

    @router.post("/skip", response_model=AnswerResponse)
    async def skip_question(body: SkipRequest):
        """Skip a pending question."""
        pq = await svc.get_request(body.request_id)
        if pq is None:
            raise HTTPException(status_code=404, detail="Question not found")
        if pq.session_id and body.session_id and pq.session_id != body.session_id:
            raise HTTPException(status_code=403, detail="Session mismatch")

        await svc.skip(body.request_id)
        return AnswerResponse(
            success=True,
            message=f"Question {body.request_id[:8]} skipped",
            request_id=body.request_id,
        )

    @router.get("/pending")
    async def get_pending(session_id: str = ""):
        """Return all pending questions, optionally filtered by session."""
        items = []
        for pq in svc._pending.values():
            if session_id and pq.session_id != session_id:
                continue
            items.append({
                "request_id": pq.request_id,
                "session_id": pq.session_id,
                "agent_id": pq.agent_id,
                "title": pq.title,
                "questions": pq.questions,  # Full question definitions
                "question_count": len(pq.questions),
                "status": pq.status,
            })
        return {"count": len(items), "items": items}

    @router.get("/details")
    async def get_details(request_id: str):
        """Return full details for a pending question by request ID."""
        pq = await svc.get_request(request_id)
        if pq is None:
            raise HTTPException(status_code=404, detail="Question not found")
        return {
            "request_id": pq.request_id,
            "session_id": pq.session_id,
            "agent_id": pq.agent_id,
            "title": pq.title,
            "questions": pq.questions,
            "question_count": len(pq.questions),
            "status": pq.status,
        }

    return router


# ══════════════════════════════════════════════════════════════════════
# Inline registration — runs during plugin.register(), not deferred
# ══════════════════════════════════════════════════════════════════════

# Flag to guard against double registration
_REGISTERED = False


def _register_tool_and_patch() -> None:
    """Inject ``ask_user`` into ``qwenpaw.agents.tools`` and patch
    ``QwenPawAgent._acting()`` — runs at plugin load time so the tool
    is available before any agent is initialized."""
    global _REGISTERED
    if _REGISTERED:
        return
    _REGISTERED = True

    from agentscope.message import Msg, TextBlock, ToolResultBlock

    # ── 1. Define the tool function ────────────────────────────────
    async def ask_user(questions: list[dict], title: str = "") -> str:
        """向用户弹出一个多页问卷并等待回答。

        调用后会在屏幕上弹出问卷窗口，用户可以逐页回答。
        支持单选（single）、多选（multi）、问答题（text）。

        Args:
            title: 问卷标题（可选）
            questions: 问题列表，每项为：
              {"type":"single", "title":"...", "options":["A","B",...]}
              {"type":"multi",  "title":"...", "options":["A","B",...]}
              {"type":"text",   "title":"..."}
        Returns:
            JSON 字符串，格式：{"answers":{...}, "other":"...", "skipped":false}
        """
        return '{"skipped": false, "message": "intercepted by plugin"}'

    # ── 2. Inject into qwenpaw.agents.tools ────────────────────────
    try:
        import qwenpaw.agents.tools as tools_module
        setattr(tools_module, "ask_user", ask_user)
        if "ask_user" not in tools_module.__all__:
            tools_module.__all__.append("ask_user")
        logger.info("✓ ask_user injected into qwenpaw.agents.tools")
    except Exception as exc:
        logger.error(f"Failed to inject ask_user: {exc}", exc_info=True)
        return

    # ── 3. Patch QwenPawAgent._acting() ────────────────────────────
    try:
        from qwenpaw.agents.react_agent import QwenPawAgent
        from .question_service import get_question_service as _get_svc

        _original_acting = QwenPawAgent._acting

        async def _patched_acting(self, tool_call: dict) -> dict | None:
            """Intercept ask_user tool calls."""
            if tool_call.get("name") != "ask_user":
                return await _original_acting(self, tool_call)

            params: dict = tool_call.get("input", {}) or {}
            questions: list[dict] = params.get("questions", [])
            title: str = params.get("title", "请回答以下问题")

            session_id = str(self._request_context.get("session_id", ""))
            agent_id = str(self._request_context.get("agent_id", "unknown"))
            user_id = str(self._request_context.get("user_id", ""))
            channel = str(self._request_context.get("channel", ""))

            svc = _get_svc()
            pending = await svc.create(
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                channel=channel,
                title=title,
                questions=questions,
            )

            # Build summary for chat bubble
            lines = [f"❓ **{title}**\n"]
            for i, q in enumerate(questions):
                q_type = q.get("type", "text")
                q_title = q.get("title", f"Q{i + 1}")
                tl = {"single": "单选", "multi": "多选", "text": "问答"}.get(q_type, q_type)
                opts = q.get("options", [])
                lines.append(
                    f"{i + 1}. [{tl}] {q_title}"
                    + ("（" + "、".join(opts) + "）" if opts else "")
                )

            # Emit message with metadata for frontend
            msg = Msg(
                self.name,
                [TextBlock(type="text", text="\n".join(lines))],
                "assistant",
                metadata={
                    "message_type": "agent_question",
                    "request_id": pending.request_id,
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "title": title,
                    "questions": questions,
                },
            )
            await self.print(msg, True)

            # ── Push notification so frontend can react instantly ──
            try:
                from qwenpaw.app.console_push_store import append as push_append
                await push_append(
                    session_id,
                    f"ask_user_question:{pending.request_id}",
                )
            except Exception:
                logger.debug("Push notification not available (non-console channel)")

            # Block indefinitely (no timeout)
            try:
                answer = await pending.future
            except asyncio.CancelledError:
                await svc.skip(pending.request_id)
                answer = {"skipped": True}

            answer_json = json.dumps(answer, ensure_ascii=False, indent=2)
            is_answered = not answer.get("skipped")

            result_msg = Msg(
                "system",
                [
                    ToolResultBlock(
                        type="tool_result",
                        id=tool_call.get("id", ""),
                        name="ask_user",
                        output=[{"type": "text", "text": answer_json}],
                    ),
                ],
                "system",
            )
            await self.print(result_msg, True)
            await self.memory.add(result_msg)
            return None

        QwenPawAgent._acting = _patched_acting
        logger.info("✓ Patched QwenPawAgent._acting() for ask_user")
    except Exception as exc:
        logger.error(f"Failed to patch agent: {exc}", exc_info=True)


# ══════════════════════════════════════════════════════════════════════
# Plugin registration
# ══════════════════════════════════════════════════════════════════════


class AskUserPlugin:
    """Ask-User plugin."""

    def register(self, api: PluginApi) -> None:
        logger.info("Registering ask-user plugin...")

        # REST API
        api.register_http_router(
            build_router(),
            prefix="/ask-user",
            tags=["ask-user"],
        )

        # Tool registration + agent patch — runs NOW, not deferred
        _register_tool_and_patch()

        logger.info("✓ Ask-user plugin registered")


# Export
plugin = AskUserPlugin()
