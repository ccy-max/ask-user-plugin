# Ask-User Plugin ❓

让 QwenPaw Agent 可以在思考/回答中随时向用户弹出多页问卷（单选 / 多选 / 问答题），并等待回答。

## 效果

当 Agent 调用 `ask_user` 工具时，用户屏幕上会弹出一个多页问卷 Modal：

- 每页一个问题，步骤条显示进度
- 支持 **单选**（single）— 含"其他"文本框
- 支持 **多选**（multi）— 含"其他"文本框
- 支持 **问答**（text）— 自由文本输入
- 最后一页"其他意见"（与问题同级）
- **跳过**按钮 → 返回 `{"skipped": true}`
- **提交**按钮 → 提交所有答案

## 安装

### 前置要求

- QwenPaw ≥ 1.1.5
- Node.js ≥ 18（仅开发/构建需要，运行时不需要）

### 快速安装

```bash
# 从本地目录安装
qwenpaw plugin install /path/to/ask-user-plugin
```

### 从源码构建

```bash
# 构建前端
cd ask-user-plugin
npm install && npm run build

# 安装插件
qwenpaw plugin install . --force
```

### 启用工具

1. 重启 QwenPaw：`qwenpaw app`
2. 进入 Agent 设置 → 工具管理
3. 找到 ❓ `ask_user` 工具，**启用**它

## 使用

向 Agent 发送消息，要求它用 `ask_user` 工具提问。例如：

```
请调用 ask_user，问我几个问题：
1. 你最喜欢哪个编程语言？（单选：Python, JavaScript, Rust, Go）
2. 你用过哪些框架？（多选：React, Vue, Django, Flask）
3. 请描述你的项目经验（问答题）
```

Agent 会弹出问卷 Modal，用户逐页回答后提交。

## Agent 调用格式

```python
ask_user(
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
# 用户提交：
{"answers": {"q0": {"type": "single", "value": "Python", "other": ""}, ...}, "other": "...", "skipped": false}

# 用户跳过：
{"skipped": true}
```

## 架构

```
┌──────────────────────────────────────────┐
│  Agent 执行流程                            │
│                                          │
│  LLM → ask_user()  → _acting() 拦截        │
│      → QuestionService (Future)           │
│      → self.print(msg, metadata)          │
│      → console_push_store.append()        │
│      → await future (阻塞等待)              │
│      → Future resolved → 继续执行           │
└────────────────────┬─────────────────────┘
                     │
          ┌──────────┴──────────┐
          │  Frontend (React)    │
          │                     │
          │  slot.fill overlay  │
          │  → 推送通知 / 轮询兜底 │
          │  → Modal 多页表单    │
          │  → 提交 / 跳过       │
          └─────────────────────┘
```

## 技术细节

- **通信**：Agent 通过 SSE 发送消息；前端通过 `console_push_store` 推送通知 + 10s 兜底轮询
- **无超时**：无限等待用户回答
- **不修改核心**：纯插件实现，通过 monkey-patch `QwenPawAgent._acting()` 拦截 `ask_user` 调用
- **热安装**：支持 `qwenpaw plugin install --force` 热更新

## 文件结构

```
ask-user-plugin/
├── plugin.json              # 插件清单
├── plugin.py                # 后端入口（工具注册 + acting patch + REST API）
├── question_service.py      # 待回答问题管理（asyncio.Future）
├── tools/__init__.py        # 工具函数定义
├── src/
│   └── index.tsx            # 前端（React + antd Modal）
├── dist/
│   └── index.js             # 构建产物
├── package.json             # 前端依赖
├── vite.config.ts           # Vite 构建配置
├── tsconfig.json            # TypeScript 配置
└── README.md
```

## 卸载

```bash
qwenpaw plugin uninstall ask-user
```

## License

MIT
