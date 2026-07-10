# -*- coding: utf-8 -*-
"""Question service for the ask-user plugin.

Manages pending questions with asyncio Futures — agents block on these
Futures until the user submits answers via the REST API.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# GC thresholds
_GC_MAX_AGE_SECONDS = 3600.0
_GC_MAX_COMPLETED = 200
_GC_PENDING_MAX_AGE_SECONDS = 3600.0
_GC_MAX_PENDING = 100


@dataclass
class QuestionDef:
    """Definition of a single question."""
    type: str          # "single" | "multi" | "text"
    title: str
    options: list[str] | None = None  # for single/multi only
    answer: Any | None = None
    other: str = ""


@dataclass
class PendingQuestion:
    """In-memory record for one pending questionnaire."""
    request_id: str
    session_id: str = ""
    agent_id: str = ""
    user_id: str = ""
    channel: str = ""
    title: str = ""
    questions: list[dict] = field(default_factory=list)
    created_at: float = 0.0
    future: asyncio.Future | None = None
    status: str = "pending"
    resolved_at: float | None = None
    skip_reason: str = ""


class QuestionService:
    """Singleton service managing pending questions.

    Agents block on PendingQuestion.future; the REST API resolves
    them when the user submits answers.
    """

    _instance: QuestionService | None = None

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._pending: dict[str, PendingQuestion] = {}

    @classmethod
    def get_instance(cls) -> QuestionService:
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def create(self, **kwargs) -> PendingQuestion:
        """Create a new pending question record.

        Required kwargs: session_id, title, questions, agent_id
        Returns the PendingQuestion with an unresolved Future.
        """
        loop = asyncio.get_running_loop()
        pq = PendingQuestion(
            request_id=str(uuid.uuid4()),
            session_id=kwargs.get("session_id", ""),
            agent_id=kwargs.get("agent_id", ""),
            user_id=kwargs.get("user_id", ""),
            channel=kwargs.get("channel", ""),
            title=kwargs.get("title", ""),
            questions=kwargs.get("questions", []),
            created_at=time.time(),
            future=loop.create_future(),
        )

        async with self._lock:
            self._pending[pq.request_id] = pq
            self._gc_locked()

        logger.info(
            "Question pending: request_id=%s agent=%s q_count=%d",
            pq.request_id[:8], pq.agent_id, len(pq.questions),
        )
        return pq

    async def submit_answer(
        self, request_id: str, answers: dict, other: str = "",
    ) -> PendingQuestion | None:
        """Resolve a pending question with the user's answers."""
        async with self._lock:
            pq = self._pending.pop(request_id, None)
            if pq is None:
                logger.warning("Question %s not found", request_id[:8])
                return None
            pq.status = "answered"
            pq.resolved_at = time.time()

        result = {
            "answers": answers,
            "other": other,
            "skipped": False,
        }
        if pq.future and not pq.future.done():
            pq.future.set_result(result)

        logger.info("Question %s answered (%d answers)", request_id[:8], len(answers))
        return pq

    async def skip(self, request_id: str) -> PendingQuestion | None:
        """Resolve a pending question with a skip marker."""
        async with self._lock:
            pq = self._pending.pop(request_id, None)
            if pq is None:
                return None
            pq.status = "skipped"
            pq.resolved_at = time.time()

        if pq.future and not pq.future.done():
            pq.future.set_result({"skipped": True})

        logger.info("Question %s skipped", request_id[:8])
        return pq

    async def cancel_all_by_session(self, session_id: str) -> int:
        """Cancel all pending questions for a session."""
        count = 0
        async with self._lock:
            to_remove = [
                rid for rid, pq in self._pending.items()
                if pq.session_id == session_id
            ]
            for rid in to_remove:
                pq = self._pending.pop(rid)
                pq.status = "cancelled"
                if pq.future and not pq.future.done():
                    pq.future.set_result({"skipped": True})
                count += 1
        if count:
            logger.info("Cancelled %d questions for session %s", count, session_id[:8])
        return count

    async def get_request(self, request_id: str) -> PendingQuestion | None:
        """Get a pending request by ID."""
        async with self._lock:
            return self._pending.get(request_id)

    def _gc_locked(self) -> None:
        """Clean up stale entries (must hold _lock)."""
        now = time.time()
        to_remove = []
        for rid, pq in self._pending.items():
            if pq.status != "pending" and now - pq.created_at > _GC_MAX_AGE_SECONDS:
                to_remove.append(rid)
            elif pq.status == "pending" and now - pq.created_at > _GC_PENDING_MAX_AGE_SECONDS:
                to_remove.append(rid)

        for rid in to_remove:
            self._pending.pop(rid, None)

        # Hard cap
        if len(self._pending) > _GC_MAX_PENDING:
            sorted_oldest = sorted(
                self._pending.items(), key=lambda x: x[1].created_at,
            )
            for rid, _ in sorted_oldest[:len(self._pending) - _GC_MAX_PENDING]:
                self._pending.pop(rid, None)


def get_question_service() -> QuestionService:
    """Convenience accessor for the singleton."""
    return QuestionService.get_instance()
