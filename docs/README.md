# PolicyLens 开发文档

版本：V1.2 Draft

日期：2026-09-04

状态：UI、产品边界、首发工程边界及 localhost + RunDock 运行方式已确认

## 阅读顺序

当前家庭 V2 实现与边界见 [家庭工作区 V2](13-family-v2.md)；它更新早期文档中“研究优先、养老和提醒尚未实现”的状态描述，保留既有安全语义。[执行清单](V2_EXECUTION.md)记录交付范围。

1. [项目边界](00-project-boundary.md)
2. [产品需求](01-product-requirements.md)
3. [信息架构与 UI](02-information-architecture-and-ui.md)
4. [技术架构](03-technical-architecture.md)
5. [数据模型](04-data-model.md)
6. [来源、证据与导入](05-source-evidence-and-ingestion.md)
7. [比较与确定性计算](06-comparison-and-calculation.md)
8. [Codex CLI 集成](07-codex-cli-integration.md)
9. [隐私、安全与本地存储](08-privacy-security-and-local-storage.md)
10. [开源复用与许可证](09-open-source-reuse-and-licenses.md)
11. [路线图与里程碑](10-roadmap-and-milestones.md)
12. [测试与验收](11-testing-and-acceptance.md)
13. [运行、备份与恢复](12-operations-backup-and-recovery.md)
14. [首轮实施任务书](TASK_IMPLEMENTATION.md)

## 文档解释优先级

当文档之间出现冲突时，按以下顺序处理：

1. 用户最新明确确认的产品边界；
2. `00-project-boundary.md` 的安全与非目标；
3. `01-product-requirements.md` 的验收要求；
4. 技术架构和模块设计；
5. UI 概念图中的示例内容。

UI 图只表达视觉和交互方向，图中的产品名、数字和状态均视为合成示例，不是产品事实或家庭资料。
