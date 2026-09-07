# PolicyLens 香港储蓄/年金主动研究执行任务

## 背景

当前页面已具备本地导入、人工核验、字段证据、基础对比、Codex 草稿和加密备份的技术闭环，但产品研究入口仍是空状态，无法主动发现公开产品资料。用户已确认把产品主线调整为香港储蓄/年金主动研究，并先覆盖友邦、保诚、宏利。

## 目标

交付一个可用的第一版公开资料研究闭环：

1. 用户先查看固定研究范围、联网行为和 Codex 用量提示，再逐次确认启动。
2. 复用当前 Codex CLI 登录，通过一次性 `--search` 研究运行发现公开线索。
3. 只抓取预置保险公司官方 HTTPS 域名，验证证据摘录后生成待人工核验字段。
4. 用户逐字段核验后才能发布产品版本，并可进行带证据状态的并排比较。
5. 主导航突出研究首页、香港储蓄/年金、证据对比、来源证据和本地搜索；未实现模块统一降级到“规划中”。

## 允许修改范围

- `services/research-api/src/policylens_api/`
- `services/research-api/alembic/versions/research/`
- `services/research-api/tests/`
- `services/research-api/pyproject.toml`
- `apps/web/src/`
- `tests/contract/`、`tests/web-smoke/`、`tests/python/`
- 与本任务直接相关的 `docs/`、契约生成文件和依赖锁文件

## 禁止修改范围

- 真实家庭资料和任何被 `.gitignore` 排除的家庭档案
- Codex 的模型、Provider、登录方式、认证配置或凭据
- 远程服务器、生产数据库和既有用户数据
- 购买、投保、退保、付款、联系保险公司或其他外部业务动作
- 未经人工核验把第三方线索或 AI 输出标记成已核验事实

## 已确定实现要求

- 首批公司固定为 `AIA Hong Kong`、`Prudential Hong Kong`、`Manulife Hong Kong`。
- Codex 发现命令必须使用 `codex --search exec --ephemeral --json --sandbox read-only --output-schema ...`，不得传入模型、Provider 或认证覆盖参数。
- 每次运行必须有可审阅预览哈希和 `confirmed: true`；不保存完整 prompt、家庭 ID 或家庭自由文本。
- 第三方页面只作为线索；只有预置官方域名中的 HTTPS 页面或 PDF 可以成为产品证据。
- 抓取器必须拒绝 userinfo、IP 字面量、非 443 端口、私网/环回/链路本地/保留地址和跨域重定向，并限制重定向、超时、响应类型和 25 MiB 内容大小。
- 官方原文使用现有 DEK 加密后保存到 `vault/*.vault`；所有新表只进入 `research.db`。
- 新增显式 `research_0002` 迁移；`family.db` 保持 `family_0001`。备份恢复必须按分库 revision 校验，并兼容旧的 research v1 备份。
- 研究结果先进入 `WAITING_REVIEW`；产品只有在必需身份字段完整且均来自可信官方来源并经人工接受后才可 `ACTIVE`。
- 缺失金额和未知值必须显示为“未知/—”，不得伪装为 0。
- 自动化测试只能使用合成网页、合成 PDF、假 Codex runner 和假 HTTP transport，不得访问真实官网。

## 验收标准

- 新安装和 research v1 数据库均可迁移到 `research_0002`，原有产品/事实不丢失。
- 研究预览明确列出三家公司、公开查询、用量提示、发送内容和不会发送的内容。
- 未确认或预览哈希不匹配时不得启动研究。
- 假 Codex 结果中的第三方 URL、越权域名、私网解析、跨域重定向、证据不匹配和超限响应均被拒绝或仅保留为线索。
- 合格官方来源生成待核验导入记录；人工未完整接受必需身份字段时产品保持 `DRAFT`。
- 香港研究页能查看最近运行、研究候选、官方来源和已发布产品；全局搜索可搜索本地产品和来源。
- 证据对比按字段展示每个产品的值、核验状态和证据数量，不生成“最佳产品”或综合分数。
- 原有导入、Codex 草稿、保单、备份/恢复和浏览器安全测试继续通过。

## 验证命令

```powershell
corepack pnpm lint
corepack pnpm typecheck
corepack pnpm test
corepack pnpm test:contract
corepack pnpm test:web-smoke
corepack pnpm privacy:scan
```

## 返回格式

最终报告需包含：实际业务闭环、未执行的真实联网动作、安全边界、测试结果、Git 初始状态与最终状态、任务分支、提交/远端/PR/CI 状态，以及仍需用户手动确认的下一步。
