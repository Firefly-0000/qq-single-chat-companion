# QQ 单会话陪聊助手

当前版本：`1.2.0`

本项目按 `docs/acceptance/single-private-chat-companion-v1.md` 实现。

核心约束：

- 只服务一个固定 QQ 私聊会话。
- GUI 必须输入目标用户名称，并通过 QQ 当前聊天标题校验。
- 只通过屏幕识别和键鼠输入操作 QQ，不读取 QQ 数据库、不注入进程、不逆向协议。
- 不识别表情包或图片含义，但检测非文字消息事件。
- 使用独立 DeepSeek API Key，通过官方兼容接口生成回复。
- 通过 Windows UI Automation 写入并发送，不抢当前前台焦点。
- 内置狗头军师 Skill，并在 GUI 中提供候选项、理由、代价和人工填入。
- 默认不自动发送；用户绑定目标会话并启用自动发送后才执行。

## 环境

- Windows 10/11
- Python 3.12
- QQ 桌面客户端已由用户手动登录
- DeepSeek API Key

## 安装

```powershell
uv sync --extra test
```

## 运行

```powershell
uv run qq-autoreply
```

或：

```powershell
uv run python -m qq_autoreply
```

## 测试

```powershell
uv run pytest -q
```

## 首次使用

1. 在 QQ 中手动打开唯一目标私聊。
2. 在 GUI 输入目标用户名称。
3. 点击“绑定当前对话”。
4. 在设置页填写 DeepSeek API Key、Base URL 和模型。
5. 保持自动发送关闭，先观察检测和草稿。
6. 确认无误后再启用自动发送并点击“开始”。

## 安全边界

- 不保证适用于所有 QQ 版本和缩放比例。
- QQ 窗口被遮挡、锁屏、标题变化或识别置信度过低时，程序会暂停。
- 发送结果无法确认时不会自动重试。
- 自动聊天的回复可能包含错误，高风险内容必须人工接管。
