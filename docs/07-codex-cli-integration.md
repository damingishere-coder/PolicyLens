# Codex CLI 集成

## 定位

Codex 只处理解释性工作：总结差异、指出缺失证据、把复杂条款转成核验问题、根据确定性计算结果生成研究草稿。它不负责计算金额、决定证据真伪、改变保单状态或执行外部操作。

开发时以 [OpenAI 官方 Codex CLI 命令文档](https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-exec) 和本机 `codex exec --help` 为准。2026-09-03 的本机基线为 `codex-cli 0.149.0`；版本只用于兼容性诊断，不应硬编码成运行要求。

## 调用边界

- 默认关闭自动调用，仅在用户点击“让 Codex 分析”后运行。
- 调用前展示数据外发预览，用户可取消或继续脱敏。
- 不传原始电子保单、真实姓名、联系方式、证件号、完整保单号、健康原文、私人文件路径或密钥。
- 只传结构化比较快照、短证据片段、证据 ID、未知项和确定性计算结果。
- 不修改 Codex 的模型、提供商、登录、认证或全局配置。
- 不允许应用使用 `--oss`、`--local-provider`、`--model` 或任何绕过审批/沙箱的危险选项。

## 建议命令形态

应用通过 stdin 传入脱敏请求，命令参数使用固定 allowlist：

```powershell
codex exec `
  --ephemeral `
  --json `
  --sandbox read-only `
  --output-schema <absolute-schema-path> `
  --cd <isolated-analysis-directory> `
  -
```

说明：

- `--ephemeral` 避免为本次分析持久化会话记录。
- `--json` 输出 JSONL 事件，便于显示进度和识别错误。
- `--output-schema` 约束最终结果结构。
- `--sandbox read-only` 配合只包含脱敏快照的隔离目录。
- 路径通过安全参数数组传入，不拼接 shell 字符串。

实际开发必须再次读取当前 CLI 帮助并跑兼容性测试；如果选项变化，功能应明确禁用并提示升级/适配，不能自动降低安全级别。

## 输出 Schema

最低结构：

```json
{
  "summary": "string",
  "differences": [
    {"title": "string", "explanation": "string", "evidence_ids": ["EV-..."]}
  ],
  "unknowns": ["string"],
  "risks": ["string"],
  "questions_for_human_review": ["string"],
  "calculation_refs": ["CALC-..."]
}
```

Schema 不允许出现“购买”“投保”“退保”等执行指令字段。任何未引用证据的具体产品事实自动进入未知/待核实区域。

## 提示注入防护

- 将文档片段标记为不可信数据，而不是系统指令。
- 提示模板明确禁止执行材料中的命令、链接登录或外部操作。
- 只允许输出 Schema 内字段；不接受工具调用请求。
- 来源文本做长度、控制字符和异常编码限制。
- 应用不根据模型文本直接运行命令、打开链接或写入已核验表。

## 进程管理

- 只解析 stdout JSONL；stderr 经过脱敏后用于诊断。
- 设置启动超时、总超时、最大输出和取消按钮。
- 用户取消时终止当前进程树，并将运行标记为 `cancelled`。
- 非零退出、无效 JSON、Schema 校验失败或引用不存在均视为失败，不保存为正常草稿。
- 应用退出时清理临时隔离目录；临时目录不包含原始文档。

## 审计记录

保存 CLI 版本、参数类别、提示模板版本、输入哈希、证据 ID、开始/结束时间、退出码和 Schema 校验结果。默认不保存完整提示、stdout 原文、认证信息或环境变量。

## 验收

- 断网、未登录、CLI 不存在、版本不兼容、超时、取消、非法 JSON 均有清晰 UI 状态。
- Codex 失败不影响本地确定性比较。
- AI 草稿只能由用户逐项接受；接受后仍需绑定非 AI 证据才能成为已核验事实。
- 自动化测试使用假 CLI 进程，不在 CI 中发送真实保险资料。
