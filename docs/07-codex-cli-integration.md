# Codex CLI 集成

## 定位

Codex 有两个彼此隔离的固定 profile：一是总结已核验产品差异；二是通过实时网页搜索发现公开的香港储蓄/年金产品线索。它不负责数值计算、决定证据真伪、改变保单状态或执行外部操作；搜索输出还必须经过官方域名抓取和证据摘录匹配。

Codex 草稿属于首次交付，但必须依赖已经完成的导入、人工核验和基础比较。开发时以 [OpenAI 官方 Codex CLI 命令文档](https://learn.chatgpt.com/docs/developer-commands?surface=cli#cli-codex-exec)、[Agent approvals & security](https://learn.chatgpt.com/docs/agent-approvals-security) 和本机 `codex exec --help` 为准。CLI 版本只用于兼容性诊断，不硬编码为长期要求。

## 真实安全边界

Codex CLI 是以当前 Windows 用户权限运行的独立本地代理。PolicyLens 必须假设它可能读取当前用户有权读取的文件；不能把工作目录、提示词或 `--sandbox read-only` 描述为保密边界。

安全边界由“最小化输入 + 用户逐次确认 + 禁止直接文件引用”构成：

- 默认关闭自动调用，只在用户点击“让 Codex 分析”后运行。
- 调用前展示完整数据外发预览；取消后不创建进程。
- 只发送字段白名单生成的脱敏 JSON、短证据片段和确定性计算结果。
- 不传原始电子保单、完整提取文本、真实姓名、联系方式、证件号、完整保单号、健康原文、私人路径、vault ID 或密钥。
- Codex 永远不接收原始资料目录、私人文件路径或 `--add-dir`。
- 不修改 Codex 的模型、提供商、登录、认证或全局配置。
- 不使用 `--oss`、`--local-provider`、`--model` 或任何绕过审批/沙箱的危险选项。

首次交付不承诺对 Codex 子进程提供强操作系统级读取隔离。如果家庭需要这种保证，必须在后续单独评估 AppContainer、独立 Windows 账户或虚拟机；未完成验证前不得用“完全隔离”宣传该功能。

## 白名单输入契约

允许发送的字段类别只有：

- 公开产品标识与版本；
- 用户在本次比较中明确选择的情景参数；
- 规范化事实值、单位、币种和保证属性；
- `VerificationStatus`、`ValueOrigin` 与证据引用 ID；
- 不含身份信息的短证据片段；
- 确定性计算模块已经生成的结果和计算引用 ID。

单个证据片段最多 600 字符，最多 12 条，总长度最多 7,200 字符。超限时要求用户主动删减，不静默截断关键上下文。构造载荷时采用字段 allowlist，不能用“先序列化完整对象，再删除敏感字段”的 denylist 方式。

## 建议命令形态

应用通过 stdin 传入脱敏请求，命令参数使用固定 allowlist：

```powershell
codex exec `
  --ephemeral `
  --json `
  --sandbox read-only `
  --output-schema <absolute-schema-path> `
  --cd <disposable-working-directory> `
  -
```

这些参数都是纵深防御和运行卫生措施：

- `--ephemeral` 避免为本次分析持久化会话记录。
- `--json` 输出 JSONL 事件，便于显示进度和识别错误。
- `--output-schema` 约束最终结果结构。
- `--sandbox read-only` 用于限制写入，但不保证文件不可读。
- 一次性工作目录只包含输出 Schema 和脱敏载荷，不是保密边界。
- 路径通过安全参数数组传入，不拼接 shell 字符串。

实际开发必须读取当前 CLI 帮助并跑兼容性测试；选项变化时禁用功能并提示适配，不能自动降低安全级别。

公开研究使用单独 runner，并把全局 `--search` 放在 `exec` 之前：

```powershell
codex --search exec `
  --skip-git-repo-check `
  --ephemeral `
  --json `
  --sandbox read-only `
  --output-schema <absolute-schema-path> `
  --cd <disposable-working-directory> `
  -
```

研究 prompt 只包含固定公开主题、三家公司名称和预置域名，不包含家庭对象、本地文件内容或私人路径。第三方搜索结果只能作为线索；结构化产品候选仍需由本地抓取器重新取得官方原文并逐字匹配证据。

两个 runner 都在一次性非 Git 目录中运行，因此必须携带 `--skip-git-repo-check`，同时继续使用 `--sandbox read-only`。缺少该参数时，CLI 会在研究开始前报 `Not inside a trusted directory and --skip-git-repo-check was not specified.`。

公开研究使用 `LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V3` 参数类别，预览与实际 runner 共用常量。发送给 CLI 的 Schema 递归声明所有属性为 required，未知可选值使用 null，并禁止额外属性；返回后仍执行本地 Pydantic 和证据校验。参见 [OpenAI 非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode) 和 [结构化输出要求](https://developers.openai.com/api/docs/guides/structured-outputs)。

公开研究失败只保存预定义错误码（例如 `CODEX_TIMEOUT`、`CODEX_INVALID_SCHEMA`、`CODEX_RATE_LIMIT`），不保存原始 stderr、JSONL、认证或私人诊断内容。失败、取消和中断不能显示为搜索零结果；只有搜索已完成且该公司没有返回线索时才使用 `NO_RESULT_RETURNED`。旧 `CODEX_FAILED` 记录无法还原具体原因，页面说明这一限制，不改写历史记录或自动重跑。

Codex 阶段总时限为 900 秒（15 分钟），随后进入独立的官方来源抓取与核验阶段。每 5 秒持久化一次安全进度：阶段枚举、已用秒数、总时限、事件计数、网页活动计数及最近活动时间。CLI 版本和参数类别在进程开始时写入，不必等成功后才有诊断信息。输出大小在运行中检查，超时或取消后终止并回收进程，再清除原始临时输出；不按“暂时没有新事件”判断卡死，也不自动重试。

官方抓取兼容本机 TUN fake-IP：仅当预置官网全部解析到 `198.18.0.0/15` 或 `fdfe:dcba:9876::/48` 时，向固定 HTTPS DNS 服务 `https://1.1.1.1/dns-query` 查询该官网的 A 记录（只传域名，不传路径和家庭数据）。返回 IP 仍须是公网地址。默认抓取客户端实际连接已验证 IP，同时保留官方 Host、TLS SNI 和证书验证，禁用环境 HTTP 代理；每次重定向继续校验域名和地址。其他私网解析、私有 DNS 返回、跨域重定向和证书错误继续拒绝。参见 [Cloudflare DNS JSON](https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/dns-json/) 和 [HTTPCore SNI 扩展](https://www.encode.io/httpcore/extensions/)。

只有官方链接但没有可核验字段的结果显示为“待核验线索”，单列官方线索数量。证据摘录必须是至少 12 个可见字符的完整上下文；短值不得用不可见字符填充。不能逐字匹配的产品继续拒绝，联网返回资料不等于已经产生可信候选。

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

Schema 不允许出现“购买”“投保”“退保”等执行指令字段。任何未引用证据的具体产品事实自动进入未知/待核实区域。分析记录使用 `AnalysisStatus: DRAFT / ACCEPTED_AS_NOTE / REJECTED`；接受为笔记也不能升级事实核验状态。

## 提示注入防护

- 将所有证据片段标记为不可信数据，而不是系统指令。
- 提示模板明确禁止执行材料中的命令、登录链接或外部操作。
- 只允许输出 Schema 内字段；应用不响应模型提出的工具调用。
- 来源文本做长度、控制字符和异常编码限制。
- 应用不根据模型文本直接运行命令、打开链接或写入已核验表。

提示注入防护只减少模型被材料误导的风险，不能替代输入最小化或操作系统权限控制。

## 进程管理

- 只解析 stdout JSONL；stderr 经过脱敏后用于诊断。
- 设置启动超时、总超时、最大输出和取消按钮。
- 用户取消时终止当前进程树，并将运行标记为 `cancelled`。
- 非零退出、无效 JSON、Schema 校验失败或引用不存在均视为失败，不保存为正常草稿。
- 应用退出时清理一次性目录；目录中不得出现原始文档或私人路径。

## 审计记录

保存 CLI 版本、参数类别、提示模板版本、输入哈希、证据 ID、开始/结束时间、退出码和 Schema 校验结果。默认不保存完整提示、stdout 原文、认证信息或环境变量。

## 验收

- 外发载荷不含姓名、私人路径、原始文件、完整保单号、vault ID 或超限片段。
- 断网、未登录、CLI 不存在、版本不兼容、超时、取消、非法 JSON 均有清晰状态。
- Codex 失败不影响本地事实和基础比较。
- AI 草稿只能接受为笔记；若要形成事实，必须另走人工核验并绑定非 AI 证据。
- 自动化测试使用假 CLI 进程；本地测试和未来 CI 都不得发送真实保险资料。
- UI 和文档不再声称一次性目录或只读沙箱能阻止 Codex 读取其他用户文件。
