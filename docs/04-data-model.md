# 数据模型

## 建模原则

产品定义、产品版本、家庭保单、证据和比较案例分开。事实不直接“写死”在 UI 字段里，而是通过可版本化的 `Fact` 记录引用证据。金额、比例、日期、司法辖区和币种不得只存展示字符串。

## 主要实体

### Workspace

本地工作区设置：数据目录、默认地区、显示币种、备份策略、AI 开关。V1 只有一个本地工作区。

### Person

家庭成员的本地昵称、出生年月范围、居住地区、角色和可选保险条件。证件号、手机号、邮箱默认不建字段；确有必要时使用独立加密扩展字段。

### Pet

宠物昵称、种类、品种、出生年月范围、性别、绝育/免疫/芯片状态及已知既往情况。敏感描述使用加密字段，比较时只暴露必要标签。

### Insurer

发行主体、品牌、司法辖区、官方名称、监管标识和官方来源。品牌名与合同主体不能混用。

### Product 与 ProductVersion

`Product` 表示长期身份；`ProductVersion` 表示某一条款/费率/计划版本，包含市场、险种、币种、销售状态、适用地区、投保条件、生效范围和来源时间。

### Policy

家庭实际持有记录，关联成员或宠物、产品版本、角色、期间、缴费、状态、是否团险/赠险和脱敏标识。产品信息更新不能静默改写历史保单。

### Benefit 与 Limitation

`Benefit` 描述责任、限额、免赔、比例、共享额度和等待期；`Limitation` 描述医院、地区、职业、品种、既往症、除外责任及触发条件。复杂责任允许树形父子关系，避免把共享额度简单相加。

### CashflowSeries 与 CashflowItem

现金流序列记录情景、币种和估值日期；项目记录日期、金额、方向、保证属性和类型（缴费、领取、现金价值、身故利益、费用等）。同一金额不能同时算作可领取现金和现金价值。

### SourceDocument

来源类型、发行方、标题、版本日期、获取日期、URL 或本地 vault 引用、SHA-256、语言、页数、处理状态和许可备注。

### EvidenceAnchor

对原始来源的定位：页码、表格/段落、坐标、原文片段及内容哈希。一个事实可以有多个证据；一条证据也可支持多个事实。

### Fact

字段路径、规范化值、原始值、单位、保证属性、证据状态、核验人/时间和替代关系。事实更新采用新增版本，不覆盖历史。

### ComparisonCase

保存被保险条件、预算、期间、领取起点、币种、汇率、权重和选中产品版本。比较结果存输入快照与算法版本，便于重算。

### ReviewTask

关联保单、产品版本或来源，包含到期日、复查规则、优先级、状态、完成证据和下次日期。

### AiAnalysisRun

记录用户触发时间、脱敏输入哈希、证据 ID 列表、提示模板版本、命令版本、退出状态、输出 Schema 版本和草稿。不得默认保存完整敏感提示或认证信息。

## 关键枚举

```text
Jurisdiction: CN_MAINLAND | HK
LineOfBusiness: MEDICAL | ACCIDENT | CRITICAL_ILLNESS | ANNUITY |
                LIFE_SAVINGS | PET | AUTO | COMMERCIAL | OTHER
EvidenceStatus: UNVERIFIED | VERIFIED | CONFLICTING | STALE | ESTIMATED
GuaranteeType: CONTRACT_GUARANTEED | NON_GUARANTEED | UNKNOWN
RecordStatus: DRAFT | ACTIVE | EXPIRED | WITHDRAWN | ARCHIVED
SourceTier: CONTRACT | OFFICIAL_DISCLOSURE | OFFICIAL_WEB |
            USER_SUPPLIED | THIRD_PARTY_LEAD | AI_OUTPUT
```

AI 输出不是 `EvidenceStatus`，而是独立的 `AI_DRAFT` 工作流状态。只有人工核验并绑定非 AI 来源后，事实才可变为 `VERIFIED`。

## 约束

- 所有金额必须带 ISO 4217 币种。
- 百分比存十进制值及计算口径。
- `CONTRACT_GUARANTEED` 必须引用合同或正式利益演示中的保证栏。
- `VERIFIED` 至少关联一个允许核验的来源和一个核验事件。
- 删除被引用来源时只允许软删除，并提示受影响事实。
- 比较案例固定引用 `ProductVersion`，不跟随“最新版本”自动变化。
- 内容哈希相同的来源可复用，但保留每次导入事件。

## 迁移与审计

Alembic 迁移必须可从上一正式版本升级；破坏性迁移前生成本地备份。对事实、证据、比较假设和核验状态的修改记录审计事件，包括时间、动作和前后值，不记录系统用户名之外的多余身份信息。
