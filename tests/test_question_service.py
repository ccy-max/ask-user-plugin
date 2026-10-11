# -*- coding: utf-8 -*-
"""Unit tests for the question service (no QwenPaw runtime required)."""
import asyncio
import sys
from pathlib import Path

import pytest

# Allow importing backend/ as a package-less module.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from question_service import (  # noqa: E402
    QuestionService,
    _validate_answers,
    _normalize_questions,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_normalize_valid():
    qs = _normalize_questions([
        {"type": "single", "title": "A", "options": ["x", "y"]},
        {"type": "text", "title": "B"},
    ])
    assert len(qs) == 2
    assert qs[0].type == "single"
    assert qs[0].options == ["x", "y"]


def test_normalize_invalid_type():
    with pytest.raises(ValueError):
        _normalize_questions([{"type": "weird", "title": "A"}])


def test_normalize_empty_options():
    with pytest.raises(ValueError):
        _normalize_questions([{"type": "single", "title": "A", "options": []}])


def test_validate_single_ok():
    qs = _normalize_questions([
        {"type": "single", "title": "A", "options": ["x", "y"]},
    ])
    clean = _validate_answers(qs, {"q0": {"value": "x", "other": ""}})
    assert clean["q0"]["value"] == "x"


def test_validate_single_other():
    qs = _normalize_questions([
        {"type": "single", "title": "A", "options": ["x", "y"]},
    ])
    clean = _validate_answers(qs, {"q0": {"value": "__other__", "other": "z"}})
    assert clean["q0"]["value"] == ""
    assert clean["q0"]["other"] == "z"


def test_validate_single_bad_option():
    qs = _normalize_questions([
        {"type": "single", "title": "A", "options": ["x", "y"]},
    ])
    with pytest.raises(ValueError):
        _validate_answers(qs, {"q0": {"value": "nope", "other": ""}})


def test_validate_multi():
    qs = _normalize_questions([
        {"type": "multi", "title": "A", "options": ["x", "y"]},
    ])
    clean = _validate_answers(qs, {"q0": {"value": ["x", "__other__"], "other": "z"}})
    assert clean["q0"]["value"] == ["x", "__other__"]
    assert clean["q0"]["other"] == "z"


def test_validate_text():
    qs = _normalize_questions([{"type": "text", "title": "A"}])
    clean = _validate_answers(qs, {"q0": {"value": "hello", "other": "ignored"}})
    assert clean["q0"]["value"] == "hello"
    assert clean["q0"]["other"] == ""


def test_validate_missing_answer_defaults():
    qs = _normalize_questions([
        {"type": "text", "title": "A"},
        {"type": "multi", "title": "B", "options": ["x"]},
    ])
    clean = _validate_answers(qs, {})
    assert clean["q0"]["value"] == ""
    assert clean["q1"]["value"] == []


def test_full_create_submit_flow():
    svc = QuestionService.get_instance()
    pq = run(svc.create(
        session_id="s1", agent_id="a1", title="T",
        questions=[{"type": "single", "title": "A", "options": ["x"]}],
        timeout_seconds=1.0,
    ))
    assert pq.status == "pending"
    secret = svc.get_secret(pq)

    async def waiter():
        return await pq.future

    task = asyncio.ensure_future(waiter())
    run(asyncio.sleep(0))
    resolved = run(svc.submit_answer(
        pq.request_id, secret,
        {"q0": {"value": "x", "other": ""}}, other="note",
    ))
    assert resolved is not None
    result = run(task)
    assert result["skipped"] is False
    assert result["answers"]["q0"]["value"] == "x"
    assert result["other"] == "note"


def test_submit_wrong_secret_rejected():
    svc = QuestionService.get_instance()
    pq = run(svc.create(
        session_id="s1", agent_id="a1", title="T",
        questions=[{"type": "text", "title": "A"}],
    ))
    resolved = run(svc.submit_answer(
        pq.request_id, "wrong-secret", {"q0": {"value": "x"}},
    ))
    assert resolved is None
    assert pq.status == "pending"  # re-staged after bad validate? no, secret fails first


def test_skip_flow():
    svc = QuestionService.get_instance()
    pq = run(svc.create(
        session_id="s1", agent_id="a1", title="T",
        questions=[{"type": "text", "title": "A"}],
    ))
    secret = svc.get_secret(pq)

    async def waiter():
        return await pq.future

    task = asyncio.ensure_future(waiter())
    run(asyncio.sleep(0))
    run(svc.skip(pq.request_id, secret))
    result = run(task)
    assert result["skipped"] is True


def test_session_cancel():
    svc = QuestionService.get_instance()
    pq = run(svc.create(
        session_id="sessX", agent_id="a1", title="T",
        questions=[{"type": "text", "title": "A"}],
    ))
    secret = svc.get_secret(pq)

    async def waiter():
        return await pq.future

    task = asyncio.ensure_future(waiter())
    run(asyncio.sleep(0))
    count = run(svc.cancel_all_by_session("sessX"))
    assert count == 1
    result = run(task)
    assert result["skipped"] is True
    # secret still valid for an already-cancelled request? it's removed.
    assert run(svc.skip(pq.request_id, secret)) is None


def test_expire_overdue():
    svc = QuestionService.get_instance()
    pq = run(svc.create(
        session_id="s2", agent_id="a1", title="T",
        questions=[{"type": "text", "title": "A"}],
        timeout_seconds=0.01,
    ))

    async def waiter():
        return await pq.future

    task = asyncio.ensure_future(waiter())
    run(asyncio.sleep(0.05))
    n = run(svc.expire_overdue())
    assert n >= 1
    result = run(task)
    assert result.get("expired") is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
