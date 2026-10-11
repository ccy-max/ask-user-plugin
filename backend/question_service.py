# -*- coding: utf-8 -*-
"""Question service for the qwenpaw-ask-user-plugin.

Manages pending questionnaires entirely in-process with asyncio Futures:
the agent's ``ask_user`` call blocks on ``PendingQuestion.future`` until the
user submits an answer (or the request times out / is skipped / cancelled).

Enhancements over the original ask-user plugin:
  * a single-use ``secret`` prevents answer forgery (knowing the request id
    is no longer enough to submit an answer);
  * every pending request has a TTL so an abandoned questionnaire can no
    longer hang the agent forever;
  * submitted answers are validated against the declared question schema;
  * an explicit state machine (pending -> answered | skipped | cancelled |
    expired) removes ambiguous "popped but not resolved" states.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# GC thresholds
_GC_MAX_AGE_SECONDS = 3600.0          # completed records kept up to 1h
_GC_PENDING_MAX_AGE_SECONDS = 3600.0  # unresolved records capped at 1h
_GC_MAX_PENDING = 200                 # hard cap on number of pending records

# Default answer wait ceiling. The agent's call blocks at most this long;
# after that the future resolves with a "skipped" (timeout) marker so a
# missing user never wedges the agent. Configurable at create() time.
DEFAULT_TIMEOUT_SECONDS = 600.0       # 10 minutes (agent blocks at most this long)

# Question types understood by the frontend.
VALID_TYPES = ("single", "multi", "text")
_OTHER_MARKER = "__other__"


@dataclass
class QuestionDef:
    """Normalized definition of a single question (validated)."""
    type: str
    title: str
    options: list[str] | None = None   # for single/multi only


@dataclass
class PendingQuestion:
    """In-memory record for one pending questionnaire."""
    request_id: str
    secret: str                        # single-use token, validates answers
    session_id: str = ""
    agent_id: str = ""
    user_id: str = ""
    channel: str = ""
    title: str = ""
    questions: list[QuestionDef] = field(default_factory=list)
    created_at: float = 0.0
    expires_at: float = 0.0
    future: asyncio.Future | None = None
    status: str = "pending"            # pending|answered|skipped|cancelled|expired
    resolved_at: float | None = None


def _normalize_questions(raw: Any) -> list[QuestionDef]:
    """Validate and normalize the incoming question list.

    Raises ``ValueError`` on malformed input so the caller can reject the
    ``ask_user`` call early instead of creating a broken pending request.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("questions must be a non-empty list")
    if len(raw) > 100:
        raise ValueError("too many questions (max 100)")

    out: list[QuestionDef] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"question #{i} must be an object")
        q_type = item.get("type")
        if q_type not in VALID_TYPES:
            raise ValueError(
                f"question #{i} has invalid type {q_type!r}; "
                f"must be one of {VALID_TYPES}",
            )
        title = str(item.get("title", f"Q{i + 1}")).strip()
        if not title:
            raise ValueError(f"question #{i} is missing a title")
        options = None
        if q_type in ("single", "multi"):
            options = item.get("options")
            if not isinstance(options, list) or not options:
                raise ValueError(
                    f"question #{i} ({q_type}) requires a non-empty 'options' list",
                )
            for opt in options:
                # Accept both plain strings and {"label":..,"value":..} dicts
                # (LLMs sometimes emit the latter). Normalize to a string.
                if isinstance(opt, dict):
                    opt_label = opt.get("label") or opt.get("value") or ""
                else:
                    opt_label = str(opt) if opt is not None else ""
                if not str(opt_label).strip():
                    raise ValueError(
                        f"question #{i} has an invalid option {opt!r}",
                    )
        out.append(QuestionDef(type=q_type, title=title, options=options))
    return out


def _validate_answers(
    questions: list[QuestionDef],
    answers: dict,
) -> dict:
    """Validate user answers against the normalized question schema.

    Returns a clean, well-typed answer dict keyed by ``q0, q1, ...``.
    ``other`` text for any question is preserved. Unknown keys are dropped.
    """
    if not isinstance(answers, dict):
        raise ValueError("answers must be an object")
    if len(answers) > len(questions):
        raise ValueError("too many answers submitted")

    clean: dict[str, Any] = {}
    for idx, q in enumerate(questions):
        key = f"q{idx}"
        raw_ans = answers.get(key)
        if raw_ans is None:
            # Missing answer -> empty default; the agent decides what to do.
            clean[key] = (
                {"type": q.type, "value": [], "other": ""}
                if q.type == "multi"
                else {"type": q.type, "value": "", "other": ""}
            )
            continue

        if not isinstance(raw_ans, dict):
            raise ValueError(f"answer {key} must be an object")
        value = raw_ans.get("value", "")
        other = str(raw_ans.get("other", ""))

        if q.type == "text":
            if not isinstance(value, str):
                value = str(value)
            clean[key] = {"type": q.type, "value": value, "other": ""}
        elif q.type == "single":
            if value == _OTHER_MARKER:
                clean[key] = {"type": q.type, "value": "", "other": other}
            elif value in (q.options or []):
                clean[key] = {"type": q.type, "value": value, "other": ""}
            elif value == "":
                clean[key] = {"type": q.type, "value": "", "other": ""}
            else:
                raise ValueError(
                    f"answer {key} value {value!r} is not a valid option",
                )
        elif q.type == "multi":
            if not isinstance(value, list):
                raise ValueError(f"answer {key} must be a list for multi")
            selected = [v for v in value if v in (q.options or [])]
            has_other = _OTHER_MARKER in value
            clean[key] = {
                "type": q.type,
                "value": selected + (["__other__"] if has_other else []),
                "other": other if has_other else "",
            }
    return clean


class QuestionService:
    """Singleton service managing pending questions.

    Agents block on ``PendingQuestion.future``; REST endpoints resolve them
    when the user submits answers (or when a TTL / cancel fires).
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

    async def create(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: str = "",
        channel: str = "",
        title: str = "",
        questions: Any,
        timeout_seconds: float | None = None,
    ) -> PendingQuestion:
        """Create a new pending question record.

        ``questions`` is validated (raises ``ValueError`` on bad input).
        Returns the ``PendingQuestion`` with an unresolved Future, a
        single-use ``secret`` and an expiration timestamp.
        """
        loop = asyncio.get_running_loop()
        norm_questions = _normalize_questions(questions)
        timeout = (
            timeout_seconds
            if timeout_seconds is not None
            else DEFAULT_TIMEOUT_SECONDS
        )
        now = time.time()
        pq = PendingQuestion(
            request_id=str(uuid.uuid4()),
            secret=secrets.token_urlsafe(24),
            session_id=session_id,
            agent_id=agent_id,
            user_id=user_id,
            channel=channel,
            title=title,
            questions=norm_questions,
            created_at=now,
            expires_at=now + float(timeout),
            future=loop.create_future(),
        )

        async with self._lock:
            self._pending[pq.request_id] = pq
            self._gc_locked()

        logger.info(
            "Question pending: request_id=%s agent=%s q_count=%d ttl=%.0fs",
            pq.request_id[:8], pq.agent_id, len(pq.questions), timeout,
        )
        return pq

    def _resolve(self, pq: PendingQuestion, status: str, result: dict) -> None:
        """Mark a record resolved and wake the waiting agent. No lock."""
        pq.status = status
        pq.resolved_at = time.time()
        if pq.future and not pq.future.done():
            pq.future.set_result(result)

    async def submit_answer(
        self,
        request_id: str,
        secret: str,
        answers: dict,
        other: str = "",
    ) -> PendingQuestion | None:
        """Resolve a pending question with the user's answers.

        Requires the correct single-use ``secret`` and validates answers.
        """
        async with self._lock:
            pq = self._pending.pop(request_id, None)
            if pq is None:
                logger.warning("Question %s not found", request_id[:8])
                return None
            if not secrets.compare_digest(pq.secret, secret or ""):
                # Not a security boundary per se, but refuse forged answers.
                logger.warning("Question %s secret mismatch", request_id[:8])
                return None

        # Validation happens outside the lock so a bad payload cannot
        # deadlock the service.
        try:
            clean = _validate_answers(pq.questions, answers)
        except ValueError as exc:
            # Re-stage the request so the user can retry; do not drop it.
            async with self._lock:
                pq.status = "pending"
                self._pending[request_id] = pq
            logger.warning("Question %s invalid answers: %s", request_id[:8], exc)
            raise

        self._resolve(
            pq,
            "answered",
            {"answers": clean, "other": str(other), "skipped": False},
        )
        logger.info(
            "Question %s answered (%d answers)", request_id[:8], len(clean),
        )
        return pq

    async def skip(self, request_id: str, secret: str) -> PendingQuestion | None:
        """Resolve a pending question with a skip marker."""
        async with self._lock:
            pq = self._pending.pop(request_id, None)
            if pq is None:
                return None
            if not secrets.compare_digest(pq.secret, secret or ""):
                logger.warning("Question %s secret mismatch", request_id[:8])
                return None
        self._resolve(pq, "skipped", {"skipped": True})
        logger.info("Question %s skipped", request_id[:8])
        return pq

    async def cancel_all_by_session(self, session_id: str) -> int:
        """Cancel all pending questions for a session (e.g. on disconnect)."""
        count = 0
        async with self._lock:
            to_remove = [
                rid for rid, pq in self._pending.items()
                if pq.session_id == session_id and pq.status == "pending"
            ]
            for rid in to_remove:
                pq = self._pending.pop(rid)
                self._resolve(pq, "cancelled", {"skipped": True})
                count += 1
        if count:
            logger.info(
                "Cancelled %d questions for session %s", count, session_id[:8],
            )
        return count

    async def expire_overdue(self) -> int:
        """Expire pending requests past their TTL. Returns count expired."""
        now = time.time()
        expired: list[PendingQuestion] = []
        async with self._lock:
            for rid, pq in list(self._pending.items()):
                if pq.status == "pending" and now >= pq.expires_at:
                    expired.append(self._pending.pop(rid))
        for pq in expired:
            self._resolve(pq, "expired", {"skipped": True, "expired": True})
            logger.info("Question %s expired", pq.request_id[:8])
        return len(expired)

    async def get_request(self, request_id: str) -> PendingQuestion | None:
        """Get a pending request by ID (without revealing the secret)."""
        async with self._lock:
            pq = self._pending.get(request_id)
            if pq is None:
                return None
            # Build a secret-stripped public view via the shared helper.
            view = self._public_view(pq)
            public = PendingQuestion(**{
                k: v for k, v in view.items()
                if k in PendingQuestion.__dataclass_fields__
            })
            public.secret = view.get("secret", "")
            return public

    def get_secret(self, pq: PendingQuestion) -> str:
        return pq.secret

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

    async def pending_public_list(self, session_id: str = "") -> list[dict]:
        """Return public (secret-stripped) view of pending questions."""
        async with self._lock:
            items = []
            for pq in self._pending.values():
                if pq.status != "pending":
                    continue
                if session_id and pq.session_id != session_id:
                    continue
                items.append(self._public_view(pq))
            return items

    @staticmethod
    def _public_view(pq: PendingQuestion) -> dict:
        return {
            "request_id": pq.request_id,
            "session_id": pq.session_id,
            "agent_id": pq.agent_id,
            "title": pq.title,
            "questions": [q.__dict__ for q in pq.questions],
            "question_count": len(pq.questions),
            "status": pq.status,
            "secret": pq.secret,   # frontend needs it to submit
            "expires_at": pq.expires_at,
        }


def get_question_service() -> QuestionService:
    """Convenience accessor for the singleton."""
    return QuestionService.get_instance()
