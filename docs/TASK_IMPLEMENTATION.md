# 首轮实施任务书

## 背景

PolicyLens 已完成 V1 产品边界和 14 个页面的视觉确认。下一阶段需要从空仓库建立可运行的 Windows 本地应用骨架，同时先落实隐私隔离、证据状态和确定性计算边界。

## 目标

建立一个可启动、可测试、无真实家庭数据的最小工程骨架，并完成 Dashboard、保单档案、来源证据和设置四个基础模块的端到端假数据闭环。

## 允许修改范围

- `apps/desktop/`：Electron 主进程、预加载层和 React 渲染层。
- `services/research-api/`：本地 FastAPI 服务、数据库迁移和领域服务。
- `packages/contracts/`：前后端共享的 JSON Schema/OpenAPI 生成物。
- `packages/ui/`：设计令牌和通用组件。
- `tests/`：单元、契约、集成和桌面冒烟测试。
- `docs/`、根目录工程配置、CI、`.gitignore` 和合成 fixtures。

## 禁止修改或纳入版本控制的范围

- 任何真实家庭档案、电子保单、计划书、健康信息或完整保单号。
- `private/`、`data/`、`vault/`、`uploads/`、`backups/`、`exports/`、`work/`。
- Codex 的模型、提供商、登录、认证、全局配置和密钥。
- 自动投保、付款、退保、理赔、联系代理人或绕过网站访问限制的功能。
- 未确认许可证的第三方代码。

## 已确定实现要求

- Windows 本地优先；渲染层不得直接访问文件系统或启动进程。
- 本地 API 仅监听 `127.0.0.1` 的随机端口，并使用每次启动生成的会话令牌。
- 家庭私有数据与产品研究数据逻辑分区；样例和测试只能使用合成数据。
- 所有提取字段支持证据引用和 `unverified / verified / conflicting / stale / estimated` 状态。
- AI 输出固定为 `ai_draft`，不能覆盖已核验事实；数值计算不用 AI。
- 审批后的 UI 风格使用蓝白、克制留白、清晰层级、圆角卡片和高可读性状态标签。
- 宠物险是 V1 正式模块；车险、企业险等只实现占位入口。

## 验收标准

1. 开发模式下一条命令启动桌面端和本地 API，关闭桌面端后无残留监听进程。
2. 四个基础页面能用合成数据完成新增、查看、编辑、删除和状态筛选。
3. 任一事实字段可打开对应来源、页码/片段、版本和核验记录。
4. 未核验或冲突字段不会显示为确定事实。
5. Git 跟踪文件和构建日志不包含真实家庭文件名、个人身份信息、密钥或本地数据库。
6. 离线时基础档案、证据查看和确定性计算可用。
7. 测试、lint、类型检查和桌面冒烟测试全部通过。

## 计划测试命令

具体包管理器在工程初始化时锁定；默认目标命令如下：

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm test:contract
pnpm test:desktop-smoke
python -m pytest services/research-api/tests
python -m ruff check services/research-api
```

## 实施返回格式

每个实施 PR 必须报告：

- 改动摘要与明确非目标；
- 数据库迁移和隐私影响；
- 实际执行的测试命令及结果；
- 已知风险与回滚方法；
- 分支、提交 SHA、远端 SHA、PR 地址、CI 状态和是否已合并。
