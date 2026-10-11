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
# Kept short so an abandoned questionnaire cannot wedge the session long.
ASK_TIMEOUT_SECONDS = 600.0  # 10 minutes


# ══════════════════════════════════════════════════════════════════════
# Tool function (placeholder body; real logic is in the middleware)
# ══════════════════════════════════════════════════════════════════════

async def qwenpaw_ask_user(questions: list[dict], title: str = "") -> str:
    """向用户弹出一个多页问卷并阻塞等待回答。

    【调用规范 — 必须严格遵守，否则工具会报错】
    1. 只在确实需要用户输入时才调用；调用后当前对话会暂停直到用户作答。
    2. questions 必须是 list，每个元素是一个 dict，type 只能是以下三选一：
       - 单选 single：  {"type":"single","title":"问题","options":["选项A","选项B"]}
       - 多选 multi：   {"type":"multi", "title":"问题","options":["选项A","选项B"]}
       - 问答 text：    {"type":"text",  "title":"问题"}
    3. options 必须是【纯字符串数组】，例如 ["A","B"]。严禁传对象数组
       （如 {"label":..,"value":..}）或带 value 字段。
    4. title 可选，字符串。
    5. 一次最多 20 题。

    返回（JSON 字符串）：
      用户作答：{"answers":{"q0":{"type":..,"value":..,"other":""},...},"other":"..","skipped":false}
      跳过/超时：{"skipped":true,"error":".."}   ← error 会说明原因，请据此修正后重试。
    """
    return json.dumps(
        {"skipped": False, "message": "handled by ask-user middleware"},
        ensure_ascii=False,
    )


# ══════════════════════════════════════════════════════════════════════
# Middleware: intercept ask_user tool calls
# ══════════════════════════════════════════════════════════════════════


def _validate_questions_format(questions: Any) -> str:
    """Return an actionable error string if the questions payload is malformed.

    The message is meant to be returned to the LLM so it can self-correct on
    the next attempt (e.g. "options must be a plain string array").
    """
    if not isinstance(questions, list) or not questions:
        return (
            "questions 必须是非空 list。示例: "
            '[{"type":"single","title":"问题","options":["A","B"]}]'
        )
    if len(questions) > 20:
        return f"questions 最多 20 题，当前 {len(questions)} 题。"
    valid = {"single", "multi", "text"}
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            return f"第 {i} 题必须是 dict，例如 " \
                   '{"type":"single","title":"问题","options":["A","B"]}'
        t = q.get("type")
        if t not in valid:
            return (
                f"第 {i} 题 type 必须是 single/multi/text，收到 {t!r}。"
                ' 示例: {"type":"single","title":"问题","options":["A","B"]}'
            )
        if t in ("single", "multi"):
            opts = q.get("options")
            if not isinstance(opts, list) or not opts:
                return (
                    f"第 {i} 题（{t}）options 必须是非空 list，"
                    '例如 ["A","B"]（纯字符串，禁止对象）。'
                )
            for o in opts:
                if isinstance(o, dict):
                    return (
                        f"第 {i} 题 options 必须是纯字符串数组，"
                        '禁止 {"label":..,"value":..} 形式。'
                        ' 正确示例: ["选项A","选项B"]'
                    )
                if not isinstance(o, str) or not str(o).strip():
                    return f"第 {i} 题 options 含非法项: {o!r}（必须是非空字符串）"
    return ""

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
        # QwenPaw 2.x may hand tool_call.input as a JSON string rather than a
        # dict, depending on the agent/serialization path. Normalize both.
        raw_input = getattr(tool_call, "input", None)
        if isinstance(raw_input, str):
            try:
                raw_input = json.loads(raw_input)
            except (ValueError, TypeError):
                raw_input = {}
        params: dict = raw_input or {}
        questions: list[dict] = params.get("questions", [])
        title: str = params.get("title", "请回答以下问题")

        # Early, explicit validation so the model gets an actionable error
        # instead of a stack trace it cannot interpret.
        fmt_err = _validate_questions_format(questions)
        if fmt_err:
            return {
                "skipped": True,
                "error": fmt_err,
            }

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
            name=agent.name if hasattr(agent, "name") else "agent",
            content=[TextBlock(type="text", text="\n".join(lines))],
            role="assistant",
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
                "向用户弹出一个多页问卷并阻塞等待回答（【必读规范】questions 必须是 list，"
                "每项 type∈single/multi/text：single/multi 须带 options 且为【纯字符串数组】"
                '如 ["A","B"]，严禁对象数组；text 只需 title；最多20题；title可选。'
                "格式错误会返回 {skipped:true,error:原因}，请照改后重试。返回用户作答或跳过。"
            ),
            icon="❓",
            tool_type="internal",
        )

        # Middleware that intercepts ask_user calls (replaces _acting patch)
        api.register_middleware(
            lambda ctx, agent_config: AskUserMiddleware(),
            priority=50,
        )

        # Ship the companion skill so the agent knows how to call this tool
        # correctly (parameter format, retries on validation errors).
        self._install_skill(api)

        logger.info("✓ qwenpaw-ask-user-plugin registered")

    def _install_skill(self, api: PluginApi) -> None:
        """Copy skills/qwenpaw-ask-user into each workspace's skills dir.

        Uses the supported workspace-created hook so the skill lands in every
        workspace (existing + future) without hard-coding a path.
        """
        skill_src = _PLUGIN_DIR / "skills" / "qwenpaw-ask-user"
        if not skill_src.exists():
            return

        def _copy_to(workspace_info: dict) -> None:
            wdir = workspace_info.get("workspace_dir") or workspace_info.get(
                "workspace",
            )
            if not wdir:
                return
            dest = Path(wdir) / "skills" / "qwenpaw-ask-user"
            try:
                dest.mkdir(parents=True, exist_ok=True)
                import shutil
                for f in skill_src.iterdir():
                    if f.is_file():
                        shutil.copy2(f, dest / f.name)
                logger.info("Skill qwenpaw-ask-user -> %s", dest)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to install skill: %s", exc)

        try:
            api.register_workspace_created_hook(
                hook_name="ask-user-install-skill",
                callback=_copy_to,
                reload_safe=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("register_workspace_created_hook unavailable: %s", exc)


# Export
plugin = AskUserPlugin()
