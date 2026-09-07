# 首次可用交付实施任务书

## 背景

PolicyLens 已确认产品边界和 14 个页面的视觉方向。完整 V1 功能较多，因此第一次开发只实现“核心闭环 + Codex 草稿”，其余功能保留清楚的后续 V1 空状态。

## 目标

从当前文档项目建立一个可在浏览器访问、由 RunDock 托管且可测试的 Windows localhost 本地应用，并用纯合成资料跑通：

`导入两份文本型 PDF/手工资料 → 提取候选字段 → 人工核验 → 查看字段证据 → 两产品基础比较 → 预览白名单外发数据 → 生成 Codex 草稿 → 加密备份 → 跨机器恢复`

## 允许修改范围

- `apps/web/`：React/Vite 浏览器前端与同源 API 客户端。
- `services/research-api/`：本地 FastAPI 服务、数据库迁移和领域服务。
- `packages/contracts/`：OpenAPI/JSON Schema 与生成类型。
- `packages/ui/`：设计令牌和通用组件。
- `tests/`：单元、契约、集成、隐私、恢复和浏览器冒烟测试。
- `docs/`、根目录工程配置、RunDock 启动配置和纯合成 fixtures。

## 禁止修改或实现

- 任何真实家庭档案、电子保单、计划书、健康信息或完整保单号。
- `private/`、`data/`、`vault/`、`uploads/`、`backups/`、`exports/`、`work/` 中的用户资料。
- 图片 OCR、Excel 导入、官网采集、完整产品库、养老/XIRR/汇率计算、提醒和批量报告。
- 自动投保、付款、退保、理赔、联系代理人或绕过网站限制。
- Codex 的模型、提供商、登录、认证和全局配置。
- 将工作目录、提示词或只读沙箱表述为 Codex 保密边界。
- 未经用户在新会话中另行明确要求，不执行 GitHub Push、PR 或合并。

## 页面范围

首次交付启用：

- 01 Dashboard：最小摘要。
- 02 Policy Archive。
- 03 Policy Detail。
- 08 Product Detail & Evidence。
- 09 Comparison & Codex：仅两个本地产品版本的基础比较和 AI 草稿。
- 10 Import Verification：仅手工和文本型 PDF。
- 12 Source Center。
- 14 Settings, Privacy & Codex。

04、05、06、11、13 显示“后续 V1”可点击空状态；07 保持其他险种路线图占位。

## 数据与领域要求

- `VerificationStatus = UNVERIFIED | VERIFIED | CONFLICTING | STALE | REJECTED`。
- `ValueOrigin = MANUAL_ENTRY | STRUCTURED_IMPORT | RULE_EXTRACTION | AI_EXTRACTION | DETERMINISTIC_CALCULATION | USER_ASSUMPTION`。
- `SourceAuthority = CONTRACT_DOCUMENT | REGULATOR_PUBLICATION | INSURER_OFFICIAL_DISCLOSURE | INSURER_OFFICIAL_WEB | THIRD_PARTY_REFERENCE | UNATTRIBUTED`。
- 三个维度独立存储；AI 不是证据来源；`ESTIMATED` 不再是核验状态。
- AI 分析使用 `AnalysisStatus = DRAFT | ACCEPTED_AS_NOTE | REJECTED`，不能直接升级事实。
- 实现 `RenewalTerms`、`PremiumRate`、`RateAdjustmentRule` 和 `PolicyPremiumRecord`。
- 标准费率与实际缴费分离；保证续保绝不推导为保费固定。

## 本地浏览器安全与恢复

- 浏览器页面不拥有 Node、shell、任意路径读取或通用本地 HTTP 能力。
- FastAPI 只监听 `127.0.0.1`，端口由 RunDock 启动参数指定；页面与 API 同源。
- 每次服务启动生成签名会话，使用 HttpOnly、SameSite=Strict Cookie、严格 Origin 与 CSRF 校验。
- PDF/恢复包只通过浏览器文件上传；备份只通过下载返回，禁止客户端提供服务端绝对路径。
- 随机 256 位 DEK 加密家庭敏感字段和 vault。
- 本机日常解锁使用当前 Windows 用户的 DPAPI 包装 DEK。
- 便携备份要求至少 12 个字符的恢复密码；使用 Argon2id（基线 `m=65536 KiB, t=3, p=1`，每份备份新的 16 字节随机盐）派生 KEK，并以 AES-256-GCM 和新的 12 字节随机 nonce 包装 DEK。
- 新电脑恢复后，用新电脑当前用户的 DPAPI 重新包装 DEK。
- 错误密码、篡改备份或版本不兼容不得修改当前数据。
- 日志不记录请求体、证据原文、私人路径、AI 完整提示或认证信息。

## Codex CLI 要求

- 默认关闭，用户逐次主动触发并查看完整外发预览。
- 通过字段 allowlist 直接构造脱敏 JSON；禁止先序列化完整家庭对象再删除字段。
- 不传原始文件、完整提取文本、私人路径、vault ID、直接身份标识或密钥。
- 单个证据片段最多 600 字符，最多 12 条，总计最多 7,200 字符。
- 只使用当前 CLI 明确支持的 `--ephemeral`、`--json`、`--sandbox read-only`、`--output-schema` 等安全参数；不覆盖模型/Provider，不使用危险绕过参数。
- 一次性目录和只读沙箱仅是纵深防御，不是读取隔离保证。
- 非零退出、超时、取消、无效 JSON、Schema 失败或无效引用均失败关闭，不修改事实。

## 验收标准

1. 一条开发命令可启动同源 localhost 页面和 API；正式本机服务由 RunDock 托管，不生成桌面安装包。
2. RunDock 中可核对 PolicyLens 的准确记录、端口、服务 PID、父进程链、健康状态和自动重启配置。
3. 启用页面可用合成数据完成目标闭环；后续页面只显示明确空状态。
4. 扫描 PDF 明确提示暂不支持，不上传云端 OCR。
5. 任一事实字段可查看值来源、核验状态、证据权威性及页码/片段。
6. 续保条款、标准费率、调费规则和实际缴费分开展示。
7. Codex 外发载荷不含原文件、私人路径、身份信息、vault ID 或超限片段。
8. Codex 结果始终为草稿；失败不影响本地事实和基础比较。
9. 同机 DPAPI 自动解锁成功；另一 Windows 测试环境可凭恢复密码恢复。
10. 错误密码和篡改备份在修改当前数据前失败。
11. Git 跟踪文件、日志、构建和测试产物不含真实家庭资料或密钥。
12. lint、类型检查、单元、契约、集成、恢复和浏览器冒烟测试全部通过。

## 计划测试命令

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm test:contract
pnpm test:web-smoke
python -m pytest services/research-api/tests
python -m ruff check services/research-api
```

项目初始化后必须把这些逻辑命令映射到真实脚本；不得用空脚本或跳过测试假装通过。

## 返回格式

开发完成后报告：

- 已实现的首次交付闭环和明确未实现项；
- 关键架构、数据模型、密钥与 Codex 安全边界；
- 实际测试命令、通过/失败数量和 Windows 浏览器 + RunDock 运行证据；
- 敏感信息扫描、进程、端口、数据库和备份恢复证据；
- 当前 Git 分支与工作区状态，但不执行远程 Push、PR 或合并；
- 已知风险、回滚方法和需要用户人工验收的步骤。
