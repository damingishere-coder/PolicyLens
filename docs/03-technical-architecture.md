# 技术架构

## 架构决策

V1 采用 **Electron + React/TypeScript 桌面端，Python/FastAPI 本地研究服务，SQLite 本地数据库**。

选择理由：Electron 便于实现 Windows 安装、自动化测试、文件选择和 Codex 子进程管理；React 适合实现已确认的复杂桌面页面；Python 在 PDF、OCR、表格解析和金融现金流计算方面生态成熟。代价是安装包同时包含 Node/Electron 和 Python sidecar，因此进程生命周期、体积、签名和升级必须进入验收，而不能只验证浏览器页面。

## 组件关系

```text
Electron renderer (React)
        │ typed IPC
Electron main/preload ────── Codex CLI（仅用户主动触发）
        │ loopback token
FastAPI sidecar on 127.0.0.1:随机端口
        ├─ 导入与本地解析
        ├─ 证据/版本服务
        ├─ 比较与确定性计算
        ├─ 本地提醒任务
        └─ SQLite + encrypted private vault
```

## 建议目录

```text
apps/
  desktop/                 # Electron main, preload, renderer
services/
  research-api/            # FastAPI 与领域服务
packages/
  contracts/               # OpenAPI/JSON Schema 与生成类型
  ui/                      # 设计令牌和通用组件
tests/
  fixtures/synthetic/      # 只允许合成资料
docs/
scripts/                   # 构建、隐私扫描、打包和诊断
```

运行时数据不位于仓库内。默认写入 Windows 当前用户的应用数据目录，并在设置中显示真实路径。

## 桌面安全边界

- Renderer 启用 `contextIsolation`，关闭 `nodeIntegration`。
- Preload 只暴露带类型的最小 IPC，不暴露任意路径读取、shell 或通用 HTTP。
- 主进程校验文件选择、扩展名、大小和允许的 IPC 消息。
- FastAPI 只监听 `127.0.0.1`，使用系统分配端口；每次启动生成高熵会话令牌。
- API 拒绝非 loopback Host/Origin，请求体设大小上限。
- 桌面退出时先停止任务，再终止 sidecar；冒烟测试确认无残留监听端口。

## 前后端契约

FastAPI 生成 OpenAPI；CI 从 OpenAPI 生成 TypeScript 类型并检查工作区无漂移。金额在 API 中使用字符串十进制定点表示，禁止用 JavaScript 浮点数作为持久化财务值。日期使用 ISO 8601；地区、币种和证据状态使用封闭枚举。

## 数据分区

- `research`：公开产品元数据、来源索引、条款版本和通用比较模板。
- `family`：家庭成员、保单、私人目标、复盘任务和本地 AI 草稿。
- `vault`：原始文件、提取文本和敏感附件，使用内容哈希引用。

三者使用不同服务接口。研究资料导出不得隐式带出家庭关系或私有文件路径。

## 任务与并发

导入、OCR、来源检查和报告生成作为本地后台任务执行，状态为 `queued / running / waiting_review / completed / failed / cancelled`。任务必须可取消、可恢复或安全重跑；内容哈希和幂等键防止重复写入。

V1 不引入 Redis、Celery 或云队列。单机任务由 sidecar 内部队列调度，持久化必要的检查点。

## 技术选型基线

- Desktop：Electron、React、TypeScript、Vite。
- UI：自有 design tokens + 可访问性优先的无样式/轻样式组件库。
- API：Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic。
- 解析：PyMuPDF/pdfplumber/pypdf；OCR 作为可选本地组件，首选能离线安装的方案。
- 计算：Python `decimal`、日期函数和经验证的求根实现；必要时与独立库交叉测试。
- 数据：SQLite，WAL 与外键开启；敏感字段和文件采用应用层认证加密。
- 打包：Electron Builder + PyInstaller sidecar，生成 Windows 安装包和校验值。

具体依赖版本在实施 PR 中锁定，并通过许可证与漏洞检查后才进入仓库。

## 故障降级

- Sidecar 启动失败：桌面显示诊断信息和日志位置，不无限重启。
- OCR 缺失：保留 PDF 文本提取与手工录入。
- 网络不可用：本地档案、证据、比较和计算继续工作；官网更新和 Codex 按钮显示不可用原因。
- Codex 失败或输出无效：保留确定性结果，不修改已核验数据。
- 数据库迁移失败：恢复迁移前备份并进入只读恢复模式。
