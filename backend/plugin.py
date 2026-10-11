# -*- coding: utf-8 -*-
"""qwenpaw-ask-user-plugin — Backend entry point.

Registration model (QwenPaw 2.x):
  * ``ask_user`` is registered through the official ``PluginApi.register_tool``
    so the LLM can discover and call it; the placeholder body simply tells the
    model the call is handled by the agent runtime.
  * A middleware (``register_middleware``) intercepts the ``ask_user`` tool
    call via the ``on_acting`` hook, blocks the agent on an asyncio Future, and
    emits the questionnaire to the frontend through the console push channel.

This replaces the old monkey-patch of ``QwenPawAgent._acting`` (removed in
QwenPaw 2.x) with the supported middleware API, and hardens the plugin with a
single-use submit secret, answer TTL, answer validation and answer auth.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from agentscope.message import Msg, TextBlock
from agentscope.middleware import MiddlewareBase
from agentscope.tool import ToolResponse
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from qwenpaw.plugins.api import PluginApi

from .question_service import get_question_service

logger = logging.getLogger(__name__)

_PLUGIN_DIR = Path(__file__).parent.resolve()

# How long the agent blocks for a user answer before timing out.
ASK_TIMEOUT_SECONDS = 1800.0  # 30 minutes


# ══════════════════════════════════════════════════════════════════════
# Tool function (placeholder body; real logic is in the middleware)
# ══════════════════════════════════════════════════════════════════════

async def qwenpaw_ask_user(questions: list[dict], title: str = "") -> str:
    """向用户弹出一个多页问卷并等待回答。

    调用后会在屏幕上弹出问卷窗口，用户可以逐页回答。
    支持单选（single）、多选（multi）、问答题（text）。
    所有选择题均附带“其他”文本框。问卷最后一页有一个与问题同级的“其他意见”文本框。

    Args:
        title: 问卷标题（可选）
        questions: 问题列表，每项为：
            {"type": "single", "title": "...", "options": ["A", "B", ...]}
            {"type": "multi",  "title": "...", "options": ["A", "B", ...]}
            {"type": "text",   "title": "..."}

    Returns:
        JSON 字符串，格式为：
        {"answers": {qN: {type, value, other}, ...}, "other": "...", "skipped": false}
        或 {"skipped": true}（用户跳过/超时）
    """
    return json.dumps(
        {"skipped": False, "message": "handled by ask-user middleware"},
        ensure_ascii=False,
    )


# ══════════════════════════════════════════════════════════════════════
# Middleware: intercept ask_user tool calls
# ══════════════════════════════════════════════════════════════════════

class AskUserMiddleware(MiddlewareBase):
    """Blocks the agent on a Future while the user fills in a questionnaire."""

    async def on_acting(
        self,
        agent: Any,
        input_kwargs: dict[str, Any],
        next_handler: Callable[..., AsyncGenerator[Any, None]],
    ) -> AsyncGenerator[Any, None]:
        tool_call = input_kwargs.get("tool_call")
        tool_name = getattr(tool_call, "name", "")
        if tool_name != "qwenpaw_ask_user":
            # Not ours — let the chain proceed normally.
            async for event in next_handler():
                yield event
            return

        try:
            result = await self._handle_ask_user(agent, tool_call)
        except Exception as exc:  # noqa: BLE001
            logger.exception("ask_user handling failed")
            result = {"skipped": True, "error": str(exc)}

        # Surface the answer as a ToolResponse so the agent continues with it.
        yield ToolResponse(
            content=[TextBlock(type="text", text=json.dumps(result, ensure_ascii=False))],
            metadata={"ask_user": True},
        )

    async def _handle_ask_user(self, agent: Any, tool_call: Any) -> dict:
        svc = get_question_service()
        params: dict = getattr(tool_call, "input", None) or {}
        questions: list[dict] = params.get("questions", [])
        title: str = params.get("title", "请回答以下问题")

        ctx = getattr(agent, "_request_context", None) or {}
        session_id = str(ctx.get("session_id", "") or "")
        agent_id = str(ctx.get("agent_id", "unknown") or "")
        user_id = str(ctx.get("user_id", "") or "")
        channel = str(ctx.get("channel", "") or "")

        try:
            pq = await svc.create(
                session_id=session_id,
                agent_id=agent_id,
                user_id=user_id,
                channel=channel,
                title=title,
                questions=questions,
                timeout_seconds=ASK_TIMEOUT_SECONDS,
            )
        except ValueError as exc:
            logger.warning("ask_user rejected invalid questions: %s", exc)
            return {"skipped": True, "error": f"invalid questions: {exc}"}

        secret = svc.get_secret(pq)

        # Build a chat bubble summarizing the questionnaire.
        lines = [f"❓ **{title}**\n"]
        for i, q in enumerate(pq.questions):
            tl = {"single": "单选", "multi": "多选", "text": "问答"}.get(q.type, q.type)
            opts = q.options or []
            lines.append(
                f"{i + 1}. [{tl}] {q.title}"
                + ("（" + "、".join(opts) + "）" if opts else "")
            )

        msg = Msg(
            agent.name if hasattr(agent, "name") else "agent",
            [TextBlock(type="text", text="\n".join(lines))],
            "assistant",
            metadata={
                "message_type": "agent_question",
                "request_id": pq.request_id,
                "session_id": session_id,
                "agent_id": agent_id,
                "title": title,
                "secret": secret,
                "questions": [q.__dict__ for q in pq.questions],
            },
        )
        if hasattr(agent, "print"):
            await agent.print(msg, True)

        # Push a fast notification so the frontend can open the modal instantly.
        try:
            from qwenpaw.app.console_push_store import append as push_append
            await push_append(
                session_id,
                f"ask_user_question:{pq.request_id}:{secret}",
            )
        except Exception:
            logger.debug("Push notification unavailable (non-console channel)")

        # Block until the user answers / skips / times out.
        try:
            answer = await asyncio.wait_for(pq.future, timeout=ASK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await svc.skip(pq.request_id, secret)
            logger.info("Question %s timed out", pq.request_id[:8])
            answer = {"skipped": True, "expired": True}

        return answer


# ══════════════════════════════════════════════════════════════════════
# REST API schemas
# ══════════════════════════════════════════════════════════════════════

class AnswerRequest(BaseModel):
    request_id: str = Field(..., description="Question request ID")
    session_id: str = Field(..., description="Session ID")
    secret: str = Field(..., description="Single-use submit secret")
    answers: dict = Field(default_factory=dict, description="Question answers")
    other: str = Field(default="", description="Final 'other' field")


class SkipRequest(BaseModel):
    request_id: str = Field(..., description="Question request ID")
    session_id: str = Field(..., description="Session ID")
    secret: str = Field(..., description="Single-use submit secret")


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
        """Submit answers to a pending question (requires the secret)."""
        pq = await svc.get_request(body.request_id)
        if pq is None:
            raise HTTPException(status_code=404, detail="Question not found")
        if pq.session_id and body.session_id and pq.session_id != body.session_id:
            raise HTTPException(status_code=403, detail="Session mismatch")

        try:
            resolved = await svc.submit_answer(
                body.request_id, body.secret, body.answers, body.other,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if resolved is None:
            raise HTTPException(status_code=403, detail="Invalid secret or expired")

        return AnswerResponse(
            success=True,
            message=f"Question {body.request_id[:8]} answered",
            request_id=body.request_id,
        )

    @router.post("/skip", response_model=AnswerResponse)
    async def skip_question(body: SkipRequest):
        """Skip a pending question (requires the secret)."""
        pq = await svc.get_request(body.request_id)
        if pq is None:
            raise HTTPException(status_code=404, detail="Question not found")
        if pq.session_id and body.session_id and pq.session_id != body.session_id:
            raise HTTPException(status_code=403, detail="Session mismatch")

        resolved = await svc.skip(body.request_id, body.secret)
        if resolved is None:
            raise HTTPException(status_code=403, detail="Invalid secret or expired")

        return AnswerResponse(
            success=True,
            message=f"Question {body.request_id[:8]} skipped",
            request_id=body.request_id,
        )

    @router.get("/pending")
    async def get_pending(session_id: str = ""):
        """Return all pending questions, optionally filtered by session."""
        items = await svc.pending_public_list(session_id)
        return {"count": len(items), "items": items}

    @router.get("/details")
    async def get_details(request_id: str):
        """Return full details for a pending question by request ID."""
        pq = await svc.get_request(request_id)
        if pq is None:
            raise HTTPException(status_code=404, detail="Question not found")
        public = svc._public_view(pq) if hasattr(svc, "_public_view") else None
        if public is None:
            public = {
                "request_id": pq.request_id,
                "session_id": pq.session_id,
                "agent_id": pq.agent_id,
                "title": pq.title,
                "questions": [q.__dict__ for q in pq.questions],
                "question_count": len(pq.questions),
                "status": pq.status,
            }
        return public

    @router.post("/cancel-session")
    async def cancel_session(request: Request, session_id: str = ""):
        """Cancel all pending questions for a session (e.g. on disconnect)."""
        count = await svc.cancel_all_by_session(session_id)
        return {"success": True, "cancelled": count}

    return router


# ══════════════════════════════════════════════════════════════════════
# Plugin registration
# ══════════════════════════════════════════════════════════════════════

class AskUserPlugin:
    """qwenpaw-ask-user-plugin."""

    def register(self, api: PluginApi) -> None:
        logger.info("Registering qwenpaw-ask-user-plugin...")

        # REST API
        api.register_http_router(
            build_router(),
            prefix="/ask-user",
            tags=["ask-user"],
        )

        # Tool registration (official API; replaces manual module injection)
        api.register_tool(
            tool_name="qwenpaw_ask_user",
            tool_func=qwenpaw_ask_user,
            description=(
                "向用户弹出一个多页问卷并等待回答。参数：questions (问题列表), "
                "title (标题,可选)。问题类型：single(单选), multi(多选), text(问答)。"
                "所有选择题含'其他'文本。问卷末页有独立'其他意见'框。"
            ),
            icon="❓",
            tool_type="internal",
        )

        # Middleware that intercepts ask_user calls (replaces _acting patch)
        api.register_middleware(
            lambda ctx, agent_config: AskUserMiddleware(),
            priority=50,
        )

        logger.info("✓ qwenpaw-ask-user-plugin registered")


# Export
plugin = AskUserPlugin()
