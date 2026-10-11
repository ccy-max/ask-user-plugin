# 更新日志

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
- **答案超时**：Agent 阻塞默认 30 分钟（可配）后自动 skip，杜绝永久卡死
- **答案校验**：后端按题型校验 value/options/other，非法提交被拒（400）且不丢请求
- **状态机**：pending→answered/skipped/cancelled/expired 显式状态，GC 增强
- 清理死代码：`tools/__init__.py` 占位、前端未使用的 `getApiUrl`

### 前端
- 推送消息格式升级为 `ask_user_question:<rid>:<secret>`，前端解析并带 secret 提交
- 路径统一 `/api/ask-user/*`（相对路径，跟随宿主前缀）
- 单问卷串行交互保持，错误提示更清晰

## v1.0.0 (原始)
- 初版：多页问卷弹窗（single/multi/text），monkey-patch `_acting` 阻塞等待
