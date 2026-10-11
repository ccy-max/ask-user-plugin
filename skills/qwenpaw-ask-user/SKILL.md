---
name: qwenpaw-ask-user
description: "When you need interactive input from the user during a turn, call the qwenpaw_ask_user tool to pop a multi-page questionnaire (single/multi/text) and block until answered. Use this instead of guessing or ending the turn. Load this skill when you are about to ask the user anything that needs a choice or free-form answer."
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    emoji: "❓"
    requires: {}
---

# qwenpaw_ask_user — Ask the user a questionnaire

Use this tool when the user's answer is required to continue: a choice
(single/multi select), a confirmation, or free-form input. The tool pops a
modal in the user's console, blocks the current turn, and returns the answer
as the tool result so you can proceed.

## When to use
- You need the user to **pick from options** (single or multi choice).
- You need a **free-text answer** that you cannot safely infer.
- You want to **batch several questions** into one modal instead of many turns.

## When NOT to use
- You can answer from context already available. Then just answer.
- A plain reply is enough. Don't ask just to ask.

## CRITICAL: parameter format (violations make the tool error out)
`questions` is a list of dicts. `type` ∈ `single` | `multi` | `text`.

- single: `{"type":"single","title":"问题","options":["选项A","选项B"]}`
- multi:  `{"type":"multi","title":"问题","options":["选项A","选项B"]}`
- text:   `{"type":"text","title":"问题"}`

Rules (the tool rejects anything else and tells you the reason — fix and retry):
1. `options` MUST be a **plain string array**: `["A","B"]`. Never
   `{"label":..,"value":..}`, never mixed objects.
2. `title` is required and non-empty.
3. Up to 20 questions per call.
4. `title` (top-level) is optional.

## Behavior notes
- The call **blocks the session** until the user submits or skips. While a
  questionnaire is open, do not start another chat in the same session.
- If the user skips or the 10-minute timeout fires, you get
  `{"skipped": true, "error": "..."}`. Handle it (ask differently, or proceed
  with a default).
- The returned `answers` keys are `q0, q1, ...` matching question order.
  Each is `{"type":..,"value":..,"other":""}`. `other` holds the "其他" text
  when the user picked 其他. The top-level `other` is the final free-text box.
- If you receive `{"skipped": true, "error": "invalid questions: ..."}`, the
  error text tells you exactly what to fix in `questions`. Correct it and call
  again.

## Minimal example
```
qwenpaw_ask_user(
    title="偏好调查",
    questions=[
        {"type":"single","title":"你最常用哪类 AI 工具？","options":["聊天助手","编程助手","图像生成","数据分析"]},
        {"type":"multi","title":"希望插件支持哪些能力？","options":["定时任务","文件处理","网页抓取","邮件收发"]},
        {"type":"text","title":"其他建议"},
    ],
)
```
