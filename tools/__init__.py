# -*- coding: utf-8 -*-
"""Dummy ask_user tool function.

This function is registered with the toolkit so the LLM can discover
and call it.  The actual blocking / popup logic runs in the agent's
``_acting()`` patch installed by the plugin's startup hook.
"""


async def ask_user(questions: list[dict], title: str = "") -> str:
    """向用户弹出一个多页问卷并等待回答。

    调用后会在屏幕上弹出问卷窗口，用户可以逐页回答。
    支持单选（single）、多选（multi）、问答题（text）。
    所有选择题均附带"其他"文本框。
    问卷最后一页有一个与问题同级的"其他意见"文本框。

    Args:
        title: 问卷标题（可选）
        questions: 问题列表，每项为：
            {"type": "single", "title": "...", "options": ["A", "B", ...]}
            {"type": "multi",  "title": "...", "options": ["A", "B", ...]}
            {"type": "text",   "title": "..."}

    Returns:
        JSON 字符串，格式为：
        {"answers": {qN: {type, value, other}, ...}, "other": "...", "skipped": false}
        或 {"skipped": true}（用户跳过）
    """
    return '{"skipped": false, "message": "This tool is intercepted by the plugin."}'
