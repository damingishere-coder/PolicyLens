# PolicyLens 首次可用交付执行任务

## 背景

仓库当前只有已经确认的产品与工程文档，尚无生产代码。本任务在不改动现有 16 个未提交文档修改、不执行任何 Git 远程流程的前提下，实现 `docs/TASK_IMPLEMENTATION.md` 定义的首次可用交付。

## 目标

交付一个可在本机浏览器访问、由 RunDock 托管、可测试的 Windows 本地应用，并以明确标注的纯合成资料完成：文本型 PDF 或手工资料导入、候选提取、人工核验、字段证据、两个产品比较、Codex 白名单预览与 AI 草稿、本地加密备份、独立配置目录恢复。

## 允许修改范围

- `apps/web/`
- `services/research-api/`
- `packages/contracts/`
- `packages/ui/`
- `tests/`
- `scripts/`
- 根目录工程、依赖、测试与打包配置
- 本执行任务文件

## 禁止修改范围

- 根目录私人家庭档案及任何真实家庭、保单、健康、身份、联系资料
- `private/`、`data/`、`vault/`、`uploads/`、`backups/`、`exports/`、`work/` 中的用户资料与 UI 原图
- Codex 模型、Provider、登录、认证或全局配置
- 现有 16 个未提交文档修改
- Git 分支、提交、Push、PR、合并或 GitHub 设置

## 已确定实现要求

- React/Vite/TypeScript 浏览器前端与 FastAPI 使用同一 localhost Origin；不保留 Electron 或桌面安装包运行路径。
- Python 3.12 + FastAPI 单进程服务只监听 `127.0.0.1`，由 RunDock 托管进程、端口与自动重启。
- 浏览器会话使用 HttpOnly、SameSite=Strict Cookie 与逐请求 CSRF header；同时严格校验 Host、Origin、请求大小和安全响应头，不开放跨域。
- SQLAlchemy + Alembic 管理分离的 `research.db` 与 `family.db`。
- `VerificationStatus`、`ValueOrigin`、`SourceAuthority` 独立存储，且不互相推导。
- 分离实现 `RenewalTerms`、`PremiumRate`、`RateAdjustmentRule`、`PolicyPremiumRecord`；保证续保不表示保费固定。
- 文本 PDF 使用文件签名、大小、页数、加密与文本可提取性检查；扫描件失败关闭，不使用 OCR。
- 随机 32 字节 DEK；Windows DPAPI 只用于日常本机包装；敏感字段、证据摘录和 vault 使用 AES-256-GCM。
- 便携备份使用 Argon2id `m=65536 KiB, t=3, p=1` 和每份备份新的 16 字节盐派生 KEK，再以 AES-256-GCM 和新的 12 字节 nonce 包装同一 DEK。
- 恢复先验证版本、外层完整性、密码、payload、数据库和 vault，再展示摘要；用户确认后才创建安全快照、原子切换并以当前机器 DPAPI 重新包装 DEK。
- Codex 请求由白名单字段直接构造；单段不超过 600 字符、最多 12 段、总计不超过 7200 字符；发送前显示完整预览并要求逐次主动确认。
- Codex 使用固定参数数组调用当前配置，禁止模型/Provider 覆盖和危险参数；输出必须通过 Schema 与证据引用校验，只保存为 `AnalysisStatus=DRAFT` 或用户接受的笔记。
- 14 个页面入口全部保留；首发未实现能力显示清楚的“后续 V1”空状态。
- PDF 与恢复文件由浏览器上传，备份由服务端在受控目录生成后作为下载返回；HTTP API 不接收任意本地源/目标路径。
- Codex runner 移入本地 FastAPI 进程，浏览器只能提交严格白名单 DTO 与显式确认位，不能提交命令、参数、模型、Provider 或路径。

## 验收标准

- 合成文本 PDF 和手工资料均能生成候选字段；重复 PDF 不重复创建事实；扫描 PDF 明确不支持。
- 用户能接受、编辑、拒绝候选字段，并查看页码、摘录、值来源、核验状态和来源权威性。
- 两个本地产品版本可比较，续保、费率、调费和实际缴费独立展示。
- Codex 预览不含原始文件、完整正文、姓名、电话、证件号、完整保单号、私人路径、vault ID、密钥或数据库标识；失败不改变事实。
- 同机 DPAPI 解锁通过；独立配置目录以不同测试包装器模拟新机器恢复；错误密码、篡改和版本不兼容在当前数据切换前失败。
- Web 会话、CSRF、同源限制、路径安全和受控文件上传/下载通过测试。
- RunDock 管理唯一 PolicyLens 进程与固定 localhost 端口；验证管理记录、PID/祖先链、监听者、健康接口和真实浏览器页面。
- Git 跟踪文件、日志、测试及构建产物通过隐私扫描。

## 测试命令

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm test:contract
pnpm test:web-smoke
python -m pytest services/research-api/tests
python -m ruff check services/research-api
pnpm privacy:scan
python scripts/serve.py --host 127.0.0.1 --port <RunDock 分配端口>
```

## 返回格式

最终报告完整用户流程、后续 V1 项、关键文件与架构、测试/构建证据、RunDock 项目/PID/端口/数据目录、恢复与 Codex 隐私证据、Git 状态和完整修改范围、已知限制与下一步人工验收。
