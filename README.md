# ❓ 问卷弹窗 (qwenpaw-ask-user-plugin)

> QwenPaw 2.x 插件 ｜ 插件 ID：`qwenpaw-ask-user-plugin`
> 让 Agent 在思考/回答中随时向用户弹出多页问卷（单选 / 多选 / 问答），并**阻塞等待**用户作答后继续推理。
> 适配 QwenPaw 2.x，参照 [会话增强 Pro](https://github.com/ccy-max/qwenpaw-session-tools-pro) 的仓库规范。

- **本项目基于 [ask-user-plugin](https://github.com/ccy-max/ask-user-plugin)（v1.0.0）适配重写**，保留全部能力，并补齐安全/健壮性与新版兼容。
- **适用版本**：QwenPaw 2.0.0 ~ 2.3.0
- **授权**：MIT

---

## 功能特性

| 能力 | 说明 |
|------|------|
| 多题型 | `single` 单选（含「其他」）/ `multi` 多选（含「其他」）/ `text` 自由文本 |
| 多页问卷 | 每页一题，步骤条显示进度，支持上一步/下一步 |
| 末页「其他意见」 | 与问题同级的独立文本框 |
| 跳过 | 用户点「跳过」或关闭 Modal → 返回 `{"skipped": true}` |
| 阻塞式回答 | Agent 调用后**最多阻塞 30 分钟**（可配）直到用户作答或被跳过/超时 |
| 提交密钥 | 每次问卷生成一次性 `secret`，仅前端持有，防止冒答 |
| 答案校验 | 后端按题型校验，非法提交被拒且不丢请求 |

## 架构

```
Agent 推理
  │  LLM 决定调用 qwenpaw_qwenpaw_ask_user(questions, title)
  ▼
register_middleware 的 on_acting 钩子拦截 qwenpaw_ask_user
  │  1) QuestionService.create() → request_id + 一次性 secret + asyncio.Future
  │  2) agent.print(Msg, metadata=agent_question)            ← 聊天气泡
  │  3) console_push_store.append(session, "ask_user_question:<rid>:<secret>") ← 即时推送
  │  4) await future（最多 30 分钟）
  ▼
前端 (React, overlay.global)
  │  push 通知 / 10s 轮询 → 拉 /api/ask-user/details → 渲染 Modal
  │  用户作答 → POST /api/ask-user/answer {request_id, session_id, secret, answers, other}
  │  或      → POST /api/ask-user/skip   {request_id, session_id, secret}
  ▼
QuestionService.submit_answer()/skip() → future.set_result() → 唤醒 Agent
  │
  ▼
答案作为 ToolResponse 回灌 Agent，继续推理
```

## 安装

### 前置要求
- QwenPaw ≥ 2.0.0
- Node.js ≥ 18（仅开发/构建需要，Release 包已含 `frontend/index.js`）

### 方式一：Release 安装包（推荐）
到 [Releases](https://github.com/ccy-max/qwenpaw-ask-user-plugin/releases) 下载
`qwenpaw-ask-user-plugin-v<版本>.zip`，解压后：

```bash
qwenpaw plugin install /path/to/qwenpaw-ask-user-plugin
```

### 方式二：从源码构建
```bash
cd qwenpaw-ask-user-plugin
npm install && npm run build     # 构建 frontend/index.js
qwenpaw plugin install . --force
```

### 启用工具
1. 重启 QwenPaw：`qwenpaw app`
2. 进入 Agent 设置 → 工具管理
3. 找到 ❓ `qwenpaw_ask_user` 工具，**启用**它

## 使用

向 Agent 发送消息，要求它用 `qwenpaw_ask_user` 工具提问，例如：

```
请调用 qwenpaw_ask_user，问我几个问题：
1. 你最喜欢哪个编程语言？（单选：Python, JavaScript, Rust, Go）
2. 你用过哪些框架？（多选：React, Vue, Django, Flask）
3. 请描述你的项目经验（问答题）
```

### Agent 调用格式
```python
qwenpaw_ask_user(
    title="问卷标题（可选）",
    questions=[
        {"type": "single", "title": "单选问题", "options": ["A", "B"]},
        {"type": "multi",  "title": "多选问题", "options": ["X", "Y"]},
        {"type": "text",   "title": "问答题"},
    ]
)
```

### 返回值
```json
// 用户提交：
{"answers": {"q0": {"type": "single", "value": "Python", "other": ""}, ...}, "other": "...", "skipped": false}
// 用户跳过/超时：
{"skipped": true}
```

## HTTP API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/ask-user/answer` | POST | 提交答案（需 `secret`） |
| `/api/ask-user/skip` | POST | 跳过（需 `secret`） |
| `/api/ask-user/pending` | GET | 列出 pending（可按 `session_id` 过滤，含 `secret`） |
| `/api/ask-user/details` | GET | 按 `request_id` 取完整问题定义（含 `secret`） |
| `/api/ask-user/cancel-session` | POST | 取消某会话全部 pending |

## 配置项

| 配置 | 位置 | 默认值 | 说明 |
|------|------|--------|------|
| 阻塞超时 | `backend/plugin.py` 的 `ASK_TIMEOUT_SECONDS` | 1800s (30min) | Agent 最长等待用户作答时间，超时自动 skip |

## 开发

```bash
# 前端
npm install
npm run build          # 产出 frontend/index.js

# 后端测试（无需 QwenPaw 运行时）
python -m pytest tests/ -v

# 打安装包
python scripts/build_release.py        # 用 plugin.json 的版本
python scripts/build_release.py 2.0.1  # 指定版本
```

## 自动构建

打 `v*` tag 推送到 GitHub 会自动：安装依赖 → 构建前端 → 打包 zip → 挂到 Release。
详见 `.github/workflows/release.yml`。

## 卸载
```bash
qwenpaw plugin uninstall qwenpaw-ask-user-plugin
```

## License
MIT
