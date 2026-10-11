# 更新日志

## v2.0.1 (2026-10-11) — 调用体验优化 + bug 修复

真机调试后修复 3 个 QwenPaw 2.x 适配崩溃，并优化调用过程体验。

### Bug 修复（真机实测发现）
- **`tool_call.input` 崩溃**：QwenPaw 2.x 传 JSON 字符串而非 dict → 加 `json.loads` 兼容两种形态
- **`Msg()` 位置参数崩溃**：2.x 的 Msg 是 pydantic 模型只收关键字参数 → 改 `Msg(name=, content=, role=)`
- **options 对象数组被拒**：模型有时传 `{label,value}` → 归一化为 label 字符串
- **`get_request` secret 剥离崩溃**：改用 `_public_view` 统一构造

### 调用体验优化
- **错误可见化**：格式校验失败返回清晰可操作错误文本（如"第 N 题 options 必须是纯字符串数组，禁止对象"），
  Agent 可据此自我修正后重试，不再只在后端日志偷偷报错
- **参数 schema 收紧**：工具 docstring/description 写死规范（options 必须纯字符串数组、type 限定、最多20题），
  从源头减少模型畸形传参
- **超时缩短**：阻塞超时 1800s → 600s（10分钟），废弃问卷不再长时间卡住会话
- **删除 requirements.txt**：空文件触发 QwenPaw 2.2.2b4 热装 bug（`invalidate_caches` 崩溃），删除即修复

### 配套 Skill
- 新增 `skills/qwenpaw-ask-user/SKILL.md`：教 Agent 正确调用工具（参数格式、重试策略、何时用/不用）
- `register()` 时通过 `register_workspace_created_hook(reload_safe=True)` 自动注入到 workspace skills 目录

## v2.0.0 (2026-10-11) — qwenpaw-ask-user-plugin

适配 QwenPaw 2.x 全面重写，参照会话增强 Pro（session-tools-pro）的仓库规范。

### 架构适配（破坏性）
- 移除对 `QwenPawAgent._acting` 的 monkey-patch（QwenPaw 2.x 已无此方法）
- 改用官方 `PluginApi.register_tool` 注册 `ask_user` 工具
- 改用官方 `register_middleware` 的 `on_acting` 钩子拦截 `ask_user` 调用并阻塞等待
- `plugin.json` 增加 `qwenpaw_version`（`2.0.0 ~ 2.3.0`），`id` 改为 `qwenpaw-ask-user-plugin`

### 仓库规范化（对齐 session-tools-pro）
- 目录结构改为 `backend/`（后端）、`frontend/`（构建产物）、`src/`（前端源码）、
  `scripts/`、`tests/`、`.github/workflows/`、`CHANGELOG.md`
- 新增 `scripts/build_release.py`：产出 `dist/qwenpaw-ask-user-plugin-v<版本>.zip`
- 新增 `.github/workflows/release.yml`：打 `v*` tag 自动构建前端 + 打包挂 Release
- 新增 `scripts/extract_release_notes.py`：从 CHANGELOG 提取当前版本说明
- 新增 `tests/test_question_service.py` 单元测试（无需 QwenPaw 运行时）

### 安全与健壮性
- **提交密钥**：每个 pending 请求生成一次性 `secret`，`/answer`、`/skip` 必须携带，
  仅知道 request_id 无法冒答（修复原版无鉴权风险）
- **答案超时**：Agent 阻塞默认 30 分钟（v2.0.1 改为 10 分钟）后自动 skip，杜绝永久卡死
- **答案校验**：后端按题型校验 value/options/other，非法提交被拒（400）且不丢请求
- **状态机**：pending→answered/skipped/cancelled/expired 显式状态，GC 增强
- 清理死代码：`tools/__init__.py` 占位、前端未使用的 `getApiUrl`

### 前端
- 推送消息格式升级为 `ask_user_question:<rid>:<secret>`，前端解析并带 secret 提交
- 路径统一 `/api/ask-user/*`（相对路径，跟随宿主前缀）
- 单问卷串行交互保持，错误提示更清晰

## v1.0.0 (原始)
- 初版：多页问卷弹窗（single/multi/text），monkey-patch `_acting` 阻塞等待
