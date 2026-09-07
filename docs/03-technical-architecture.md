# 技术架构

## 架构决策

V1 采用 **React/TypeScript 浏览器前端、Python/FastAPI localhost 本地服务、SQLite 本地数据库**，由 RunDock 托管服务进程和端口参数，不制作桌面安装包。

选择理由：React 适合实现已确认的复杂页面；浏览器原生文件选择和下载足以承载首次交付；FastAPI 可同时提供静态页面、API、PDF 解析和 Codex 子进程管理；Python 在 PDF、OCR、表格解析和金融现金流计算方面生态成熟。RunDock 统一负责 Windows 本机服务的启动、自动重启和端口状态，避免 Electron、sidecar 与安装包的额外生命周期。

当前在首次交付骨架上启用香港储蓄/年金主动研究：独立 Codex 搜索 runner 只发现公开线索，受限抓取器只访问预置官方 HTTPS 域名，证据匹配后复用人工核验流程。OCR、金融计算、提醒和其他市场完整产品库仍不进入当前运行路径。

## 组件关系

```text
系统浏览器（React）
        │ same-origin HTTP + HttpOnly 会话 Cookie + CSRF
FastAPI on 127.0.0.1:RunDock 分配端口 ── Codex CLI（比较草稿 + 公开搜索，均逐次确认）
        ├─ 导入与本地解析
        ├─ 官方域名抓取、robots/SSRF 门禁与来源修订
        ├─ 证据/版本服务
        ├─ 比较与确定性计算
        ├─ 静态页面与备份下载/恢复上传
        └─ SQLite + encrypted private vault
        ▲
        └─ RunDock 进程托管、自动重启与健康检查
```

## 建议目录

```text
apps/
  web/                     # React/Vite 浏览器前端
services/
  research-api/            # FastAPI 与领域服务
packages/
  contracts/               # OpenAPI/JSON Schema 与生成类型
  ui/                      # 设计令牌和通用组件
tests/
  fixtures/synthetic/      # 只允许合成资料
docs/
scripts/                   # localhost 启动、构建、隐私扫描和诊断
```

运行时数据不位于仓库内。默认写入 Windows 当前用户的应用数据目录，并在设置中显示真实路径。

## 浏览器与本地 API 安全边界

- 页面不包含 Node、shell、任意路径读取或通用本地 HTTP 能力。
- PDF 与备份恢复只通过浏览器文件选择上传；备份只通过浏览器下载，不接受客户端提供的服务端绝对路径。
- FastAPI 只监听 `127.0.0.1`，端口由 RunDock 启动参数指定；页面、静态资源和 API 使用同一 Origin。
- 每次服务启动生成高熵签名会话；Cookie 设置 `HttpOnly`、`SameSite=Strict`，修改请求还必须通过同源 Origin 与 CSRF 校验。
- API 拒绝非 loopback Host、非同源 Origin 和超限请求；页面使用严格 CSP，响应默认不缓存。
- 这些措施防御浏览器跨站请求和误暴露，不声称阻止已控制当前 Windows 用户的本地进程。

## 前后端契约

FastAPI 生成 OpenAPI；类型生成任务从 OpenAPI 生成 TypeScript 类型并检查工作区无漂移。金额在 API 中使用字符串十进制定点表示，禁止用 JavaScript 浮点数作为持久化财务值。日期使用 ISO 8601；地区、币种使用封闭枚举。每个事实分别传输 `VerificationStatus`、`ValueOrigin`，每个证据来源传输 `SourceAuthority`，三个字段不得合并或互相推导。

## 数据分区

- `research`：公开产品元数据、来源索引、条款版本和通用比较模板。
- `family`：家庭成员、保单、私人目标、复盘任务和本地 AI 草稿。
- `vault`：原始文件、提取文本和敏感附件，使用内容哈希引用。

三者使用不同服务接口。研究资料导出不得隐式带出家庭关系或私有文件路径。

## 密钥与便携恢复

- 家庭敏感数据与 vault 使用随机 256 位数据加密密钥（DEK）加密。
- 日常本机解锁由 Windows 当前用户的 DPAPI 包装 DEK；DPAPI 不承担跨机器恢复。
- 手工便携备份要求用户设置恢复密码。恢复密码通过 Argon2id 派生密钥加密密钥（KEK），再以 AES-256-GCM 包装同一个 DEK。
- 备份清单保存版本化 KDF 参数、盐、nonce、加密后的 DEK、数据哈希和 Schema 版本，不保存密码。
- 新电脑使用恢复密码解开 DEK，完成校验与恢复后，再由新电脑当前用户的 DPAPI 重新包装。
- 错误密码、完整性失败或不支持的版本必须在切换当前数据前失败。

## 任务与并发

导入、后续 OCR、来源检查和报告生成作为本地后台任务执行，状态为 `queued / running / waiting_review / completed / failed / cancelled`。任务必须可取消、可恢复或安全重跑；内容哈希和幂等键防止重复写入。

V1 不引入 Redis、Celery 或云队列。单机任务由本地服务内部队列调度，持久化必要的检查点。

## 技术选型基线

- Web：React、TypeScript、Vite；只通过系统浏览器访问 localhost。
- UI：自有 design tokens + 可访问性优先的无样式/轻样式组件库。
- API：Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic。
- 解析：首次交付使用 PyMuPDF/pdfplumber/pypdf 处理文本型 PDF；OCR 作为后续可选本地组件。
- 计算：Python `decimal`、日期函数和经验证的求根实现；必要时与独立库交叉测试。
- 数据：SQLite，WAL 与外键开启；敏感字段和文件采用应用层认证加密；本机密钥使用 DPAPI 包装，便携备份使用恢复密码包装。
- 运行：RunDock 使用项目虚拟环境中的 Python 启动 `scripts/serve.py`，显式传入 loopback 端口并启用自动重启；不生成 Windows 安装包。

具体依赖版本在实施变更中锁定，并通过许可证与漏洞检查后才进入项目。若未来恢复 PR 工作流，同样的检查必须成为合并门槛。

## 故障降级

- 本地服务启动失败：RunDock 显示失败状态；通过受限事件日志和健康端点诊断，不静默切换端口或无限重启。
- 扫描 PDF：首次交付明确提示暂不支持，并允许改用手工录入；不得自动上传云端 OCR。
- 网络不可用：本地档案、证据、比较和计算继续工作；官网更新和 Codex 按钮显示不可用原因。
- Codex 失败或输出无效：保留确定性结果，不修改已核验数据。
- 数据库迁移失败：恢复迁移前备份并进入只读恢复模式。
