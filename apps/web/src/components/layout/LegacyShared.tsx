import { Card } from "@policylens/ui";
import {
CircleAlert
} from "lucide-react";
import { type ReactNode } from "react";
export const fieldLabels: Record<string, string> = {
  "product.display_name": "产品名称",
  "product.version_label": "产品版本",
  "product.jurisdiction": "司法辖区",
  "product.line_of_business": "险种",
  "product.currency": "币种",
  "product.insurer_id": "保险公司",
  "product.sale_status": "销售状态",
  "product.payment_term": "缴费期",
  "product.issue_age": "投保年龄",
  "product.benefit_term": "保障/利益期",
  "product.available_currencies": "可选币种",
  "product.participating_type": "分红类型",
  "product.guarantee_summary": "保证利益摘要",
  "product.non_guaranteed_summary": "非保证利益摘要",
  "product.withdrawal_options": "提取方式",
  "product.policy_loan": "保单贷款",
  "product.currency_switch": "币种转换",
  "product.policy_split": "保单拆分",
  "product.change_of_insured": "更换受保人",
  "product.change_of_owner": "更换持有人",
  "risk.surrender": "退保风险",
  "risk.exchange_rate": "汇率风险",
  "risk.non_guaranteed": "非保证风险",
  "fulfillment_ratio.disclosure": "分红实现率披露",
  "premium_rate.amount": "标准年费率",
  "renewal_terms.renewal_mode": "续保模式",
  "renewal_terms.guarantee_period_years": "保证续保期间",
  "renewal_terms.maximum_renewal_age": "最高续保年龄",
  "rate_adjustment_rule.scope": "费率调整范围",
  "benefit.limit": "责任限额"
};

export function asError(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请稍后重试。";
}

export function money(value: string | null | undefined, currency = "CNY"): string {
  if (value === null || value === undefined || value.trim() === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const symbol = currency === "CNY" ? "¥" : currency;
  return `${symbol} ${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{subtitle}</p></div>{actions && <div className="page-actions">{actions}</div>}</header>;
}

export function Loading() {
  return <div className="loading" role="status"><span className="spinner" />正在读取本地数据…</div>;
}

export function ContractCard({ title, value }: { title: string; value: Record<string, unknown> | null }) { return <Card><h2>{title}</h2>{value ? <KeyValue data={Object.fromEntries(Object.entries(value).filter(([key]) => !["id", "product_version_id"].includes(key)))} /> : <p className="muted">暂无记录</p>}</Card>; }

const contractLabels: Record<string,string> = {renewal_mode:"续保方式",guarantee_period_years:"保证续保年数",maximum_renewal_age:"最高续保年龄",requires_reunderwriting:"是否重新核保",reassesses_health:"是否重新评估健康",waiting_period_days:"等待期（天）",continuity_conditions:"连续投保条件",discontinuation_treatment:"停售后的处理",termination_conditions:"终止条件",version_label:"版本",valid_from:"适用起日",valid_to:"适用止日",currency:"币种",frequency:"频率",amount:"标准费率金额",pricing_dimensions_json:"费率适用条件",pricing_dimensions:"费率适用条件",scope:"调费范围",trigger_conditions:"调费触发条件",notice_days:"通知期（天）",cap:"上限",floor:"下限",effective_from:"生效日期"};
export const semanticLabels: Record<string,string> = {UNKNOWN:"未知",VERIFIED:"已核验",UNVERIFIED:"待核验",CONFLICTING:"存在冲突",STALE:"依据待更新",REJECTED:"已拒绝",ACTIVE:"已核验版本",DRAFT:"草稿",GUARANTEED_RENEWAL:"保证续保",CONDITIONAL_RENEWAL:"有条件续保",NON_GUARANTEED_RENEWAL:"不保证续保",NON_RENEWABLE:"不可续保",COHORT:"同一投保群体",PORTFOLIO:"产品组合",INDIVIDUAL:"个别调整",REGULATORY:"监管规定",ANNUAL:"每年",MONTHLY:"每月",SINGLE:"一次性",ANNUAL_REVIEW:"年度评估",GUARANTEED:"保证",NON_GUARANTEED:"非保证",NOT_APPLICABLE:"不适用",MANUAL_ENTRY:"手工记录",RULE_EXTRACTION:"规则提取",AI_EXTRACTION:"AI 提取",DETERMINISTIC_CALCULATION:"确定性计算",USER_ASSUMPTION:"用户假设",CONTRACT_DOCUMENT:"正式合同／条款",REGULATOR_PUBLICATION:"监管披露",INSURER_OFFICIAL_DISCLOSURE:"保险公司正式披露",INSURER_OFFICIAL_WEB:"保险公司官网",THIRD_PARTY_REFERENCE:"第三方线索",UNATTRIBUTED:"来源不明"};

export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未知";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "string") return semanticLabels[value] ?? value;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") return String(value);
  return "不支持的值";
}

export function KeyValue({ data }: { data: Record<string, unknown> }) { return <dl className="key-value">{Object.entries(data).map(([key, value]) => <div key={key}><dt>{contractLabels[key] ?? key.replaceAll("_", " ")}</dt><dd>{displayValue(value)}</dd></div>)}</dl>; }

export function KeyRow({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }

export function ErrorPanel({ message }: { message: string }) { return <div className="error-panel" role="alert"><CircleAlert /><div><strong>操作未完成</strong><p>{message}</p></div></div>; }
