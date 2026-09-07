# 开源复用与许可证

## 原则

PolicyLens 可以借鉴多个 GitHub 项目的架构和交互，但“公开可见”不等于“允许复制”。只有在许可证、版本、版权声明和兼容性核验完成后，才可引入代码或数据。

当前阶段没有复制下列项目的代码；表格只记录可继续评估的方向。

## 已核验候选（2026-09-03）

| 项目 | GitHub 识别到的许可证 | 可研究方向 | 当前决定 |
|---|---|---|---|
| [qd-maker/insurance-rag](https://github.com/qd-maker/insurance-rag) | MIT | 保险资料提取与 RAG 流程 | 仅做设计参考，实施前逐文件审计 |
| [himiaocc/himiao-hk-insurance-audit](https://github.com/himiaocc/himiao-hk-insurance-audit) | MIT | 香港产品审核、管理与 FastAPI 工作流 | 可评估复用独立模块，保留声明 |
| [FDU-INS/Insurance-Skills](https://github.com/FDU-INS/Insurance-Skills) | Apache-2.0 | 保险研究任务与评估方法 | 可研究提示/评估思路，核验内容许可 |
| [CUFEInse/CUFEInse](https://github.com/CUFEInse/CUFEInse) | Apache-2.0 | 保险评测与数据集方法 | 代码与数据许可分别核验 |
| [dxianjun/hk-insurance-web](https://github.com/dxianjun/hk-insurance-web) | 未识别到许可证 | 香港产品展示、IRR 交互方向 | 只能观察公开行为，不复制代码/素材 |
| [andre4life/insurance-compare](https://github.com/andre4life/insurance-compare) | 未识别到许可证 | 多险种对比与报告方向 | 许可证澄清前不复制代码 |

GitHub 的自动识别结果只是初筛。真正引入前还要打开目标版本的许可证正文，确认仓库内子目录、图片、数据和模型是否使用不同许可证。

## 引入流程

1. 记录仓库 URL、固定 commit SHA、目标文件和用途。
2. 核对根许可证、文件头、NOTICE、数据/模型/字体/图标的独立条款。
3. 检查许可证与 PolicyLens 最终许可证、分发方式和依赖许可证是否兼容。
4. 优先通过包管理器使用成熟上游依赖；避免复制后失去安全更新。
5. 若复制或改写代码，保留版权/许可证声明，并在 `THIRD_PARTY_NOTICES.md` 登记。
6. 运行安全、隐私和行为测试；上游代码不得扩大文件、网络或进程权限。
7. 在变更说明中记录来源、修改、许可证义务、升级与移除方案；若未来使用 PR，则同步写入 PR 描述。

## 禁止项

- 从无许可证、来源不明或仅在 README 口头宣称许可的项目复制代码。
- 把第三方产品数据库、条款全文、品牌素材或爬取结果当作自由数据再发布。
- 删除版权头、NOTICE 或归属信息。
- 为了“组合项目”直接拼接多个应用、数据库和认证系统。
- 引入会把本地家庭资料上传到云端的默认遥测、分析或错误报告依赖。

## 本仓库许可证决策

当前仓库暂不授予开源许可证。正式发布可复用代码前，由项目所有者在 MIT、Apache-2.0 或其他方案中明确选择，再新增 `LICENSE`。在此之前，第三方只能查看代码，不能据此推定复用权利。

## 依赖清单

构建阶段生成软件物料清单（SBOM）和许可证报告。至少记录包名、版本、来源、直接/间接依赖、许可证、用途和已知限制。CI 对未知许可证、禁止许可证和新增网络上传能力进行阻断。
