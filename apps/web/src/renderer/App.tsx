import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import {
  Archive,
  BadgeCheck,
  BarChart3,
  Bell,
  BookOpen,
  Bot,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  Database,
  FileCheck2,
  FileSearch,
  FolderOpen,
  Home,
  Import,
  Info,
  KeyRound,
  Laptop,
  LockKeyhole,
  PawPrint,
  Plus,
  RotateCcw,
  Scale,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  WalletCards
} from "lucide-react";
import { Card, StatusBadge } from "@policylens/ui";
import type { CodexAnalysis } from "@policylens/contracts";
import { policyLens } from "../api";

type Page =
  | "dashboard"
  | "search"
  | "policies"
  | "policy-detail"
  | "mainland"
  | "hong-kong"
  | "pet"
  | "other-lines"
  | "product-detail"
  | "comparison"
  | "import"
  | "retirement"
  | "sources"
  | "reminders"
  | "settings";

interface ResearchDashboardData {
  insurers: Array<{ id: string; brand_name: string }>;
  research_runs: number;
  waiting_review: number;
  hk_products: number;
  active_hk_products: number;
  recent_runs: ResearchRunView[];
}
interface ResearchReadinessView {
  ready: boolean;
  manual_confirmation_required: true;
  active_run_id: string | null;
  checks: Array<{ id: string; ready: boolean; message: string }>;
}
interface ResearchPreviewView {
  scope: { jurisdiction: "HK"; categories: string[]; insurer_ids: string[]; max_products_per_insurer: number };
  insurers: Array<{ id: string; brand_name: string; legal_name: string; official_hosts: string[] }>;
  query_summary: string;
  will_send: string[];
  will_not_send: string[];
  usage_notice: string;
  argument_profile: string;
  requires_confirmation: true;
  preview_hash: string;
}

interface ResearchLeadView {
  id: string;
  insurer_id: string;
  title: string;
  url: string;
  channel: "OFFICIAL_SEARCH" | "THIRD_PARTY_LEAD";
  authority: string;
  status: string;
  rejection_code: string | null;
  import_id: string | null;
}

interface ResearchRunView {
  id: string;
  status: string;
  summary: {
    discovered_products?: number; waiting_review?: number; rejected_products?: number; lead_only?: number;
    execution?: {
      phase: string; elapsed_seconds: number; timeout_seconds: number;
      events_observed: number; web_searches: number; last_event_elapsed_seconds: number | null;
    };
  };
  error_code: string | null;
  cancel_requested: boolean;
  created_at: string;
  leads: ResearchLeadView[];
  insurer_outcomes: Array<{
    insurer_id: string;
    brand_name: string;
    status: string;
    official_candidates: number;
    official_leads?: number;
    waiting_review: number;
    published: number;
    rejected: number;
    lead_only: number;
    error_codes: string[];
  }>;
}

interface ResearchCandidateView {
  import_id: string;
  run_id: string;
  review_status: string;
  verification_label: "UNVERIFIED_CANDIDATE" | "REVIEW_COMPLETED";
  display_name: string;
  version_label: string;
  insurer_id: string;
  jurisdiction: string | null;
  line_of_business: string | null;
  currency: string | null;
  sale_status: string | null;
  missing_fields: string[];
  field_count: number;
  published_product_version_id: string | null;
  source: ImportView["source"] & { canonical_url?: string | null; fetched_at?: string | null };
  fields: CandidateView[];
}

interface CandidateComparisonView {
  candidates: Array<{
    import_id: string;
    display_name: string;
    version_label: string;
    insurer_id: string;
    review_status: string;
    verification_label: string;
  }>;
  rows: Array<{
    field_path: string;
    cells: Array<{
      import_id: string;
      candidate_id: string | null;
      value: string | null;
      unit: string | null;
      verification_status: string;
      guarantee_type: string;
      source_authority: string | null;
      page_number: number | null;
      excerpt: string | null;
      source_url: string | null;
    }>;
  }>;
  notice: string;
}

interface EvidenceComparisonView {
  products: Array<{ version_id: string; display_name: string; version_label: string; insurer_id: string | null }>;
  rows: Array<{
    field_path: string;
    cells: Array<{ version_id: string; value: string | null; unit: string | null; verification_status: string; guarantee_type: string; evidence_count: number; evidence_ids: string[] }>;
  }>;
  notice: string;
}

interface SearchResultView {
  query: string;
  products: ProductSummary[];
  candidates: ResearchCandidateView[];
  sources: SourceView[];
}

interface CandidateView {
  id: string;
  field_path: string;
  value: string;
  raw_value: string;
  unit: string | null;
  page_number: number | null;
  excerpt: string;
  excerpt_hash: string;
  verification_status: string;
  value_origin: string;
  source_authority: string;
  guarantee_type: string;
  decision: string | null;
}

interface ImportView {
  id: string;
  status: string;
  duplicate: boolean;
  source: {
    id: string;
    title: string;
    document_type: string;
    authority: string;
    page_count: number;
    sha256: string;
  };
  candidates: CandidateView[];
}

interface ProductSummary {
  id: string;
  display_name: string;
  jurisdiction: string;
  line_of_business: string;
  currency: string;
  version_id: string;
  version_label: string;
  record_status: string;
  verified_facts: number;
  insurer_id: string | null;
  product_category: string | null;
  sale_status: string | null;
}

interface EvidenceView {
  id: string;
  page_number: number | null;
  excerpt: string;
  excerpt_hash: string;
  authority: string;
}

interface ProductDetail extends ProductSummary {
  facts: Array<{
    id: string;
    field_path: string;
    normalized_value: string;
    unit: string | null;
    guarantee_type: string;
    verification_status: string;
    value_origin: string;
    evidence: EvidenceView[];
  }>;
  renewal_terms: (Record<string, unknown> & {
    renewal_mode?: string;
    guarantee_period_years?: number | null;
    maximum_renewal_age?: number | null;
  }) | null;
  premium_rate: (Record<string, unknown> & { amount?: string; currency?: string }) | null;
  rate_adjustment_rule: (Record<string, unknown> & { scope?: string }) | null;
}

interface PolicyView {
  id: string;
  member_nickname: string;
  category: string;
  status: string;
  product: ProductDetail;
  premium_records: Array<Record<string, string | null>>;
}

interface SourceView {
  id: string;
  title: string;
  document_type: string;
  authority: string;
  page_count: number;
  sha256: string;
  status: string;
  evidence_count: number;
  imported_at: string;
  canonical_url: string | null;
  fetched_at: string | null;
  content_type: string | null;
}

interface PreviewView {
  payload: Record<string, unknown> & {
    comparison: {
      evidenceExcerpts: Array<{ evidenceId: string; text: string; authority: string }>;
    };
  };
  preview_hash: string;
  excerpt_count: number;
  excerpt_characters: number;
  warnings: string[];
}

interface PreviewSelectionView {
  requires_selection: true;
  evidence_options: Array<{
    evidenceId: string;
    text: string;
    authority: string;
    field: string;
    product: string;
  }>;
  limits: { max_excerpts: number; max_each_characters: number; max_total: number };
  message: string;
}

interface AnalysisView {
  id: string;
  status: "DRAFT" | "ACCEPTED_AS_NOTE" | "REJECTED";
  result: CodexAnalysis;
  fact_verification_changed: false;
}

interface RestorePreview {
  restore_token: string;
  source_count: number;
  product_count: number;
  policy_count: number;
  backup_created_at: string;
  current_data_unchanged: boolean;
}

const fieldLabels: Record<string, string> = {
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

const navItems: Array<{ page: Page; label: string; icon: typeof Home }> = [
  { page: "dashboard", label: "研究首页", icon: Home },
  { page: "hong-kong", label: "香港储蓄/年金", icon: Search },
  { page: "comparison", label: "证据对比", icon: Scale },
  { page: "sources", label: "来源证据", icon: BookOpen },
  { page: "policies", label: "家庭保单", icon: Archive },
  { page: "mainland", label: "规划中", icon: Clock3 },
  { page: "settings", label: "设置", icon: Settings }
];

function asError(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请稍后重试。";
}

function money(value: string | null | undefined, currency = "CNY"): string {
  if (value === null || value === undefined || value.trim() === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  const symbol = currency === "CNY" ? "¥" : currency;
  return `${symbol} ${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}`;
}

function PageHeader({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{subtitle}</p></div>{actions && <div className="page-actions">{actions}</div>}</header>;
}

function EmptyV1({ icon, title, description }: { icon: ReactNode; title: string; description: string }) {
  return <Card className="empty-v1"><div className="empty-v1__icon">{icon}</div><StatusBadge tone="info">后续 V1</StatusBadge><h2>{title}</h2><p>{description}</p><div className="notice"><Info size={18} />当前页面保留入口，不展示虚构产品、计算结果或伪功能。</div></Card>;
}

function Loading() {
  return <div className="loading" role="status"><span className="spinner" />正在读取本地数据…</div>;
}

function DashboardPage({ go }: { go: (page: Page) => void }) {
  const [data, setData] = useState<ResearchDashboardData | null>(null);
  const [readiness, setReadiness] = useState<ResearchReadinessView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    Promise.all([policyLens.getResearchDashboard(), policyLens.getResearchReadiness()])
      .then(([dashboard, ready]) => {
        setData(dashboard as ResearchDashboardData);
        setReadiness(ready as ResearchReadinessView);
      })
      .catch((reason) => setError(asError(reason)));
  }, []);
  if (error) return <ErrorPanel message={error} />;
  if (!data || !readiness) return <Loading />;
  const cards: Array<[string, string, ReactNode]> = [
    ["首批保险公司", String(data.insurers.length), <ShieldCheck size={24} key="insurer" />],
    ["研究运行", String(data.research_runs), <FileSearch size={24} key="run" />],
    ["待核验产品", String(data.waiting_review), <CircleAlert size={24} key="review" />],
    ["已核验港险", String(data.active_hk_products), <BadgeCheck size={24} key="active" />]
  ];
  return <>
    <PageHeader title="香港保险公开研究台" subtitle="主动发现公开产品资料，官方来源核验后再进入你的本地产品库" actions={<button className="button primary" onClick={() => go("hong-kong")}><Search size={18} />开始一次研究</button>} />
    <Card className="readiness-panel"><div><div className="card-title"><h2><Laptop />研究准备度</h2><StatusBadge tone={readiness.ready ? "success" : "warning"}>{readiness.ready ? "可以开始" : "需要处理"}</StatusBadge></div><p>每次研究仍需先查看范围和用量预览，再由你单独确认；不会后台定时运行。</p></div><div className="readiness-checks">{readiness.checks.map((check) => <div key={check.id} className={check.ready ? "ready" : "blocked"}>{check.ready ? <Check /> : <CircleAlert />}<span>{check.message}</span></div>)}</div></Card>
    <div className="metric-grid">{cards.map(([label, value, icon]) => <Card className="metric" key={String(label)}><div className="metric__icon">{icon}</div><div><span>{label}</span><strong>{value}</strong></div></Card>)}</div>
    <div className="two-column">
      <Card><div className="card-title"><h2>真实研究闭环</h2><StatusBadge tone="success">公开资料优先</StatusBadge></div><ol className="flow-list"><li><Search />全网发现产品线索</li><li><ShieldCheck />只抓取预置官方域名</li><li><FileSearch />逐字匹配证据摘录</li><li><BadgeCheck />人工核验后发布产品</li><li><Scale />按字段和证据并排比较</li></ol></Card>
      <Card><div className="card-title"><h2>最近研究</h2><button className="link-button" onClick={() => go("hong-kong")}>查看工作台 <ChevronRight size={16} /></button></div>{data.recent_runs.length ? <div className="list">{data.recent_runs.map((item) => <div className="list-row" key={item.id}><FileSearch size={20} /><div><strong>{item.id}</strong><span>{item.status} · 待核验 {item.summary.waiting_review ?? 0}</span></div></div>)}</div> : <div className="small-empty"><Search /><p>尚未运行公开研究。进入香港储蓄/年金工作台，先看联网与用量预览。</p></div>}</Card>
    </div>
    <div className="notice"><ShieldCheck size={18} />家庭资料不会进入研究查询。每次联网搜索都必须先查看预览并单独确认。</div>
  </>;
}

function PoliciesPage({ openPolicy, go }: { openPolicy: (id: string) => void; go: (page: Page) => void }) {
  const [policies, setPolicies] = useState<PolicyView[] | null>(null);
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState("");
  const refresh = useCallback(() => {
    Promise.all([policyLens.listPolicies(), policyLens.listProducts(false)])
      .then(([policyValue, productValue]) => {
        setPolicies(policyValue as PolicyView[]);
        setProducts(productValue as ProductSummary[]);
      }).catch((reason) => setError(asError(reason)));
  }, []);
  useEffect(refresh, [refresh]);
  const create = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await policyLens.createPolicy({
        member_nickname: form.get("nickname"),
        product_version_id: form.get("product"),
        category: form.get("category"),
        status: "ACTIVE",
        due_amount: form.get("amount"),
        paid_amount: form.get("amount"),
        currency: form.get("currency"),
        frequency: "ANNUAL",
        due_date: form.get("date"),
        paid_date: form.get("date")
      });
      setShowForm(false);
      refresh();
    } catch (reason) { setError(asError(reason)); }
  };
  return <>
    <PageHeader title="家庭保单档案" subtitle="昵称化管理实际持有记录，标准费率与实际缴费分开" actions={<><button className="button secondary" onClick={() => go("import")}><Import size={18} />导入资料</button><button className="button primary" onClick={() => setShowForm(!showForm)}><Plus size={18} />新增保单</button></>} />
    {error && <ErrorPanel message={error} />}
    {showForm && <Card><form className="form-grid" onSubmit={(event) => void create(event)}><label>家庭成员昵称<input name="nickname" required maxLength={40} placeholder="例如：成员甲（请勿填真实姓名）" /></label><label>已核验产品<select name="product" required defaultValue=""><option value="" disabled>选择产品</option>{products.map((item) => <option key={item.version_id} value={item.version_id}>{item.display_name} · {item.version_label}</option>)}</select></label><label>保单分类<select name="category"><option value="CORE">长期核心</option><option value="GROUP">团体福利</option><option value="GIFT">赠送保障</option><option value="UNCONFIRMED">待核实</option></select></label><label>实际年缴金额<input name="amount" required pattern="\d+(\.\d{1,2})?" defaultValue="1280.00" /></label><label>币种<select name="currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>缴费日期<input type="date" name="date" required defaultValue="2026-09-03" /></label><div className="form-actions"><button type="button" className="button secondary" onClick={() => setShowForm(false)}>取消</button><button className="button primary" disabled={!products.length}>保存本地保单</button></div></form>{!products.length && <p className="hint">请先导入并核验至少一个合同或官方来源产品。</p>}</Card>}
    {policies === null ? <Loading /> : policies.length ? <Card className="table-card"><table><thead><tr><th>产品</th><th>成员昵称</th><th>分类</th><th>实际缴费</th><th>状态</th><th /></tr></thead><tbody>{policies.map((item) => <tr key={item.id}><td><strong>{item.product.display_name}</strong><small>{item.product.version_label}</small></td><td>{item.member_nickname}</td><td>{item.category}</td><td>{money(item.premium_records[0]?.paid_amount, item.premium_records[0]?.currency ?? "CNY")}</td><td><StatusBadge tone="success">{item.status}</StatusBadge></td><td><button className="icon-button" aria-label="查看保单" onClick={() => openPolicy(item.id)}><ChevronRight /></button></td></tr>)}</tbody></table></Card> : <Card className="small-empty"><Archive /><h2>尚无保单档案</h2><p>先核验一个本地产品版本，再用昵称建立保单记录。</p></Card>}
  </>;
}

function PolicyDetailPage({ id, back }: { id: string | null; back: () => void }) {
  const [policy, setPolicy] = useState<PolicyView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (id) policyLens.getPolicy(id).then((value) => setPolicy(value as PolicyView)).catch((reason) => setError(asError(reason))); }, [id]);
  if (error) return <ErrorPanel message={error} />;
  if (!policy) return <Loading />;
  const record = policy.premium_records[0];
  return <><button className="back" onClick={back}>← 返回保单档案</button><PageHeader title={policy.product.display_name} subtitle={`${policy.member_nickname} · ${policy.product.line_of_business} · ${policy.product.version_label}`} actions={<StatusBadge tone="success"><BadgeCheck size={14} />本地已核验版本</StatusBadge>} />
    <div className="metric-grid metric-grid--three"><Card className="metric"><CalendarIcon /><div><span>实际缴费</span><strong>{money(record?.paid_amount, record?.currency ?? policy.product.currency)}</strong></div></Card><Card className="metric"><RotateCcw /><div><span>续保权利</span><strong>{String(policy.product.renewal_terms?.renewal_mode ?? "UNKNOWN")}</strong></div></Card><Card className="metric"><WalletCards /><div><span>标准费率</span><strong>{money(String(policy.product.premium_rate?.amount ?? ""), String(policy.product.premium_rate?.currency ?? policy.product.currency))}</strong></div></Card></div>
    <div className="three-column"><ContractCard title="RenewalTerms 续保条款" value={policy.product.renewal_terms} /><ContractCard title="PremiumRate 标准费率" value={policy.product.premium_rate} /><ContractCard title="RateAdjustmentRule 调费规则" value={policy.product.rate_adjustment_rule} /></div>
    <Card><div className="card-title"><h2>PolicyPremiumRecord 实际缴费</h2><StatusBadge tone="info">与标准费率独立</StatusBadge></div><KeyValue data={record ?? {}} /></Card>
    <div className="notice warning"><CircleAlert size={18} />保证续保只描述续保权利，不表示未来保费固定。调费规则和每期实际缴费必须单独核验。</div>
  </>;
}

function CalendarIcon() { return <Clock3 className="metric__plain-icon" />; }

function ProductLibraryPage({ market, go }: { market: "mainland" | "hong-kong" | "pet"; go: (page: Page) => void }) {
  const definitions = {
    mainland: ["内地保险产品库", "后续开放官方来源、版本和类别筛选。首次交付仅显示本地导入产品。", <ShieldCheck size={36} key="m" />],
    "hong-kong": ["香港保险产品库", "后续开放币种、保证/非保证利益和跨境提示。", <BarChart3 size={36} key="h" />],
    pet: ["宠物险产品库", "后续开放宠物条件、指定医院、既往症与等待期比较。", <PawPrint size={36} key="p" />]
  } as const;
  const current = definitions[market];
  return <><PageHeader title={current[0]} subtitle="完整产品库属于后续 V1；这里不展示任何虚构产品" actions={<button className="button primary" onClick={() => go("import")}><Upload size={18} />导入本地资料</button>} /><div className="tabs"><button className={market === "mainland" ? "active" : ""} onClick={() => go("mainland")}>内地</button><button className={market === "hong-kong" ? "active" : ""} onClick={() => go("hong-kong")}>香港</button><button className={market === "pet" ? "active" : ""} onClick={() => go("pet")}>宠物险</button><button onClick={() => go("other-lines")}>其他险种</button></div><EmptyV1 icon={current[2]} title={current[0]} description={current[1]} /></>;
}

const researchErrors: Record<string, string> = {
  CODEX_FAILED: "研究执行失败，本次未取得完整结果；请勿将其理解为保险公司没有产品。旧记录未保留具体原因，请在修复生效后重新预览并启动研究。",
  CODEX_UNTRUSTED_DIRECTORY: "研究未能启动：临时工作目录未通过检查，请更新程序后重新研究。",
  CODEX_NOT_FOUND: "未找到 Codex CLI，请检查本机安装后重新研究。",
  CODEX_START_FAILED: "研究进程无法启动或临时文件无法读写，请检查本机运行环境。",
  CODEX_INVALID_SCHEMA: "研究输出格式配置不兼容，请更新程序后重新研究。",
  CODEX_AUTH_REQUIRED: "Codex 登录验证失败，请检查本机登录状态后重新研究。",
  CODEX_RATE_LIMIT: "Codex 可用额度或请求频率受限，请待限制恢复后重新研究。",
  CODEX_NETWORK_FAILED: "无法连接 Codex 服务，请检查网络后重新研究。",
  CODEX_TIMEOUT: "研究超时，本次未取得完整结果；请稍后重新预览并启动研究。",
  DNS_FAILED: "官网域名解析失败，无法取得原文。",
  DNS_REJECTED: "官网解析结果未通过安全检查，无法取得原文。",
  SSRF_REJECTED: "官网解析到了非公网地址，已停止抓取；请检查网络或代理的 DNS 设置。",
  EVIDENCE_MISMATCH: "返回的证据摘录无法在官网原文中逐字核对，该产品未进入候选。",
  REQUIRED_EVIDENCE_MISSING: "必要字段缺少可逐字核对的官方证据，该产品未进入候选。",
  OFFICIAL_LEAD_UNVERIFIED: "已找到官方页面线索，但尚未取得完整的可核验证据。",
  CODEX_INVALID_OUTPUT: "研究返回内容未通过格式校验，本次未创建候选产品。",
  CODEX_OUTPUT_TOO_LARGE: "研究输出超过安全上限，本次结果已拒绝。",
  RESEARCH_PIPELINE_FAILED: "研究处理失败，本次结果不完整。",
  USER_CANCELLED: "本次研究已取消，未完成的搜索不能视为没有产品。",
  PROCESS_INTERRUPTED: "服务退出导致研究中断，请重新预览并启动研究。",
  NO_VERIFIED_OFFICIAL_SOURCE: "本次搜索已结束，但没有取得通过官方来源核验的候选，请查看各公司的具体结果。",
  RESEARCH_FAILED: "本次研究执行失败，尚无完整搜索结果。",
  RESEARCH_CANCELLED: "本次研究已取消。",
  RESEARCH_INTERRUPTED: "本次研究已中断，请重新预览并启动研究。",
  NO_RESULT_RETURNED: "本次搜索已结束，未返回该公司的候选或线索。",
  NO_OFFICIAL_CANDIDATE: "本次仅发现第三方线索，未取得可核验的官方候选。"
};

function researchError(code: string): string {
  return researchErrors[code] ? `${researchErrors[code]}（${code}）` : code;
}

function ResearchExecution({ run }: { run: ResearchRunView }) {
  const execution = run.summary.execution;
  if (!execution) return null;
  const phases: Record<string, string> = {
    STARTING: "正在启动", RESEARCHING: "正在研究", WEB_SEARCH: "检索和读取公开网页", RESPONSE_READY: "已返回研究资料"
  };
  const elapsed = `${Math.floor(execution.elapsed_seconds / 60)} 分 ${execution.elapsed_seconds % 60} 秒`;
  return <div className="notice research-execution"><Clock3 /><span>
    {['QUEUED', 'DISCOVERING', 'FETCHING'].includes(run.status) ? "Codex 阶段" : "Codex 最后记录"}：{phases[execution.phase] ?? "正在处理"} · 已用 {elapsed} / 上限 {Math.ceil(execution.timeout_seconds / 60)} 分钟
    {" · "}网页检索活动 {execution.web_searches} 次
    {execution.last_event_elapsed_seconds !== null && ` · 最近活动在第 ${execution.last_event_elapsed_seconds} 秒`}
    {run.status === "FETCHING" && " · 正在核验官方原文"}
  </span></div>;
}

function ResearchStatus({ status }: { status: string }) {
  const tone = ["WAITING_REVIEW", "COMPLETED"].includes(status) ? "success" : ["FAILED", "CANCELLED", "INTERRUPTED"].includes(status) ? "danger" : "warning";
  const labels: Record<string, string> = { FAILED: "执行失败", CANCELLED: "已取消", INTERRUPTED: "已中断", NO_RESULT: "未发现结果", SEARCHING: "研究中", QUEUED: "等待启动", DISCOVERING: "联网研究中", FETCHING: "核验原文中", PARTIAL: "部分完成", LEAD_ONLY: "待核验线索" };
  return <StatusBadge tone={tone}>{labels[status] ?? status}</StatusBadge>;
}

function HongKongResearchPage({ openImport, openProduct }: { openImport: (id: string) => void; openProduct: (id: string) => void }) {
  const [preview, setPreview] = useState<ResearchPreviewView | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [run, setRun] = useState<ResearchRunView | null>(null);
  const [runs, setRuns] = useState<ResearchRunView[]>([]);
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [candidates, setCandidates] = useState<ResearchCandidateView[]>([]);
  const [readiness, setReadiness] = useState<ResearchReadinessView | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([]);
  const [candidateComparison, setCandidateComparison] = useState<CandidateComparisonView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = run && ["QUEUED", "DISCOVERING", "FETCHING"].includes(run.status);
  const refresh = useCallback(async () => {
    const [runValue, productValue, candidateValue, readinessValue] = await Promise.all([
      policyLens.listResearchRuns(),
      policyLens.listResearchProducts(true),
      policyLens.listResearchCandidates(),
      policyLens.getResearchReadiness()
    ]);
    const recent = runValue as ResearchRunView[];
    setRuns(recent);
    setProducts(productValue as ProductSummary[]);
    setCandidates(candidateValue as ResearchCandidateView[]);
    setReadiness(readinessValue as ResearchReadinessView);
    setRun((current) => current ? recent.find((item) => item.id === current.id) ?? current : recent[0] ?? null);
  }, []);
  useEffect(() => { refresh().catch((reason) => setError(asError(reason))); }, [refresh]);
  useEffect(() => {
    if (!active || !run) return;
    const timer = window.setInterval(() => {
      policyLens.getResearchRun(run.id).then((value) => {
        const next = value as ResearchRunView;
        setRun(next);
        if (!["QUEUED", "DISCOVERING", "FETCHING"].includes(next.status)) void refresh();
      }).catch((reason) => setError(asError(reason)));
    }, 1500);
    return () => window.clearInterval(timer);
  }, [active, refresh, run]);
  const prepare = async () => {
    setBusy(true); setError("");
    try { setPreview(await policyLens.previewResearch() as ResearchPreviewView); setConfirmed(false); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const start = async () => {
    if (!preview || !confirmed) return;
    setBusy(true); setError("");
    try { const next = await policyLens.startResearch(preview.preview_hash) as ResearchRunView; setRun(next); setPreview(null); setConfirmed(false); await refresh(); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const cancel = async () => {
    if (!run) return;
    try { await policyLens.cancelResearch(run.id); setRun(await policyLens.getResearchRun(run.id) as ResearchRunView); } catch (reason) { setError(asError(reason)); }
  };
  const toggleCandidate = (importId: string) => {
    setCandidateComparison(null);
    setSelectedCandidates((current) => current.includes(importId)
      ? current.filter((item) => item !== importId)
      : current.length < 4 ? [...current, importId] : current);
  };
  const compareCandidates = async () => {
    if (selectedCandidates.length < 2) return;
    setBusy(true); setError("");
    try {
      setCandidateComparison(await policyLens.compareResearchCandidates(selectedCandidates) as CandidateComparisonView);
    } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const officialLeads = run?.leads.filter((item) => item.channel === "OFFICIAL_SEARCH") ?? [];
  const thirdPartyLeads = run?.leads.filter((item) => item.channel === "THIRD_PARTY_LEAD") ?? [];
  return <>
    <PageHeader title="香港储蓄/年金主动研究" subtitle="友邦、保诚、宏利 · 全网发现线索 · 官方来源逐字验证" actions={<button className="button primary" disabled={busy || Boolean(active) || readiness?.ready === false} onClick={() => void prepare()}><Search size={18} />查看联网研究预览</button>} />
    {error && <ErrorPanel message={error} />}
    {readiness && <div className={`notice ${readiness.ready ? "success" : "warning"}`}>{readiness.ready ? <BadgeCheck /> : <CircleAlert />}{readiness.ready ? "研究环境已就绪；点击后仍会先展示本次联网范围与用量预览。" : readiness.checks.filter((item) => !item.ready).map((item) => item.message).join("；")}</div>}
    <div className="research-insurers">{["友邦香港", "保诚香港", "宏利香港"].map((name) => <Card key={name}><ShieldCheck /><div><strong>{name}</strong><span>官方域名白名单已锁定</span></div></Card>)}</div>
    {preview && <Card className="research-preview"><div className="card-title"><h2><Sparkles />本次联网研究预览</h2><StatusBadge tone="warning">需要逐次确认</StatusBadge></div><p className="research-query">{preview.query_summary}</p><div className="two-column compact-columns"><div><h3>会发送</h3><ul>{preview.will_send.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h3>不会发送</h3><ul>{preview.will_not_send.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="notice warning"><CircleAlert />{preview.usage_notice}</div><code>预览校验 {preview.preview_hash.slice(0, 12)}…</code><label className="confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已查看范围和用量提示，同意本次只搜索公开资料</label><div className="form-actions"><button className="button secondary" onClick={() => setPreview(null)}>取消</button><button className="button primary" disabled={!confirmed || busy} onClick={() => void start()}><Search />确认并启动一次研究</button></div></Card>}
    {run && <Card className="research-run"><div className="card-title"><h2><FileSearch />最近运行</h2><ResearchStatus status={run.status} /></div><div className="run-summary"><span>候选产品 <strong>{run.summary.discovered_products ?? 0}</strong></span><span>待核验 <strong>{run.summary.waiting_review ?? 0}</strong></span><span>已拒绝 <strong>{run.summary.rejected_products ?? 0}</strong></span><span>线索 <strong>{run.summary.lead_only ?? 0}</strong></span></div><ResearchExecution run={run} />{active && <div className="notice"><span className="spinner" />Codex 正在发现公开线索并验证官方页面。可以离开本页，运行记录会保留。<button className="button secondary" onClick={() => void cancel()}>取消研究</button></div>}{run.error_code && <div className="notice warning"><CircleAlert />{researchError(run.error_code)}</div>}{officialLeads.length > 0 && <div className="lead-list"><h3>官方来源与候选</h3>{officialLeads.map((lead) => <article key={lead.id}><div><strong>{lead.title}</strong><small>{lead.insurer_id} · {lead.authority}</small><span>{lead.url}</span></div><div><ResearchStatus status={lead.status} />{lead.import_id && <button className="button secondary" onClick={() => openImport(lead.import_id!)}>逐项核验</button>}</div></article>)}</div>}{thirdPartyLeads.length > 0 && <details className="third-party-leads"><summary>第三方线索 {thirdPartyLeads.length} 条（不会作为事实）</summary>{thirdPartyLeads.map((lead) => <p key={lead.id}>{lead.title} · {lead.url}</p>)}</details>}</Card>}
    {run && <Card className="insurer-outcomes"><div className="card-title"><h2>逐保险公司结果</h2><span>零结果也会给出明确原因</span></div><div className="outcome-grid">{run.insurer_outcomes.map((item) => <div key={item.insurer_id}><div><strong>{item.brand_name}</strong><ResearchStatus status={item.status} /></div><small>官方候选 {item.official_candidates} · 官方线索 {item.official_leads ?? 0} · 待核验 {item.waiting_review} · 第三方线索 {item.lead_only}</small>{item.error_codes.length > 0 && <p>{item.error_codes.map(researchError).join("、")}</p>}</div>)}</div></Card>}
    <Card className="candidate-workbench"><div className="card-title"><div><h2><FileSearch />研究候选工作台</h2><span>候选生成后立即可浏览、选中和并排比较</span></div><div className="candidate-actions"><StatusBadge tone="warning">全部先视为未核验</StatusBadge><button className="button primary" disabled={selectedCandidates.length < 2 || busy} onClick={() => void compareCandidates()}><Scale />对比所选 {selectedCandidates.length || ""}</button></div></div>{candidates.length ? <div className="candidate-card-grid">{candidates.map((candidate) => <article className={`candidate-card ${selectedCandidates.includes(candidate.import_id) ? "selected" : ""}`} key={candidate.import_id}><label className="candidate-select"><input type="checkbox" checked={selectedCandidates.includes(candidate.import_id)} disabled={!selectedCandidates.includes(candidate.import_id) && selectedCandidates.length >= 4} onChange={() => toggleCandidate(candidate.import_id)} />加入待核验对比</label><div className="card-title"><div><h3>{candidate.display_name}</h3><small>{candidate.version_label} · {candidate.insurer_id}</small></div><StatusBadge tone={candidate.review_status === "WAITING_REVIEW" ? "warning" : "success"}>{candidate.review_status === "WAITING_REVIEW" ? "未核验候选" : "已完成核验"}</StatusBadge></div><dl><div><dt>类别</dt><dd>{candidate.line_of_business ?? "未知"}</dd></div><div><dt>币种</dt><dd>{candidate.currency ?? "未知"}</dd></div><div><dt>销售状态</dt><dd>{candidate.sale_status ?? "未知"}</dd></div><div><dt>候选字段</dt><dd>{candidate.field_count}</dd></div></dl><details><summary>查看字段证据</summary>{candidate.fields.map((field) => <div className="candidate-evidence" key={field.id}><strong>{fieldLabels[field.field_path] ?? field.field_path}：{field.value} {field.unit ?? ""}</strong><small>{field.source_authority} · {field.page_number ? `第 ${field.page_number} 页` : "网页正文"}</small><blockquote>{field.excerpt}</blockquote></div>)}</details><div className="candidate-source"><BookOpen /><a href={candidate.source.canonical_url ?? undefined} target="_blank" rel="noreferrer">{candidate.source.title}</a></div><button className="button secondary full" onClick={() => candidate.published_product_version_id ? openProduct(candidate.published_product_version_id) : openImport(candidate.import_id)}>{candidate.published_product_version_id ? "查看正式产品" : "逐项人工核验"}</button></article>)}</div> : <div className="small-empty"><FileSearch /><h2>尚无研究候选</h2><p>完成一次联网研究后，通过官方来源逐字验证的候选会立即显示在这里；无需先发布成正式产品。</p></div>}</Card>
    {candidateComparison && <Card className="evidence-matrix candidate-matrix"><div className="card-title"><h2>待核验候选对比</h2><StatusBadge tone="warning">不是正式结论</StatusBadge></div><div className="matrix-scroll"><table><thead><tr><th>字段</th>{candidateComparison.candidates.map((candidate) => <th key={candidate.import_id}>{candidate.display_name}<small>{candidate.version_label}</small></th>)}</tr></thead><tbody>{candidateComparison.rows.map((row) => <tr key={row.field_path}><td><strong>{fieldLabels[row.field_path] ?? row.field_path}</strong></td>{row.cells.map((cell) => <td key={cell.import_id}><strong>{cell.value ?? "缺失"} {cell.unit ?? ""}</strong><small>{cell.verification_status} · {cell.guarantee_type}</small>{cell.excerpt && <details><summary>证据摘录</summary><blockquote>{cell.excerpt}</blockquote></details>}</td>)}</tr>)}</tbody></table></div><div className="notice warning"><CircleAlert />{candidateComparison.notice}</div></Card>}
    <Card className="table-card research-products"><div className="card-title table-heading"><h2>本地香港产品档案</h2><span>{products.length} 个版本</span></div>{products.length ? <table><thead><tr><th>产品</th><th>保险公司</th><th>类别</th><th>销售状态</th><th>核验</th><th /></tr></thead><tbody>{products.map((product) => <tr key={product.version_id}><td><strong>{product.display_name}</strong><small>{product.version_label}</small></td><td>{product.insurer_id ?? "未知"}</td><td>{product.product_category ?? product.line_of_business}</td><td>{product.sale_status ?? "未知"}</td><td><ResearchStatus status={product.record_status} /></td><td><button className="icon-button" aria-label={`查看产品 ${product.display_name}`} onClick={() => openProduct(product.version_id)}><ChevronRight /></button></td></tr>)}</tbody></table> : <div className="small-empty"><Search /><h2>尚无已抓取产品</h2><p>先运行一次公开研究。只有通过官方来源验证的候选才会进入人工核验。</p></div>}</Card>
    {runs.length > 1 && <div className="notice"><Clock3 />已保留 {runs.length} 次最近研究记录；服务重启不会自动重跑未完成任务。</div>}
  </>;
}

function OtherLinesPage() {
  const items = [["车险", "车型、地区、保障责任与报价来源"], ["企业险", "财产、责任、雇主与团体保障"], ["旅行险", "行程保障、意外医疗与紧急救援"], ["家财险", "家庭财产、责任与生活风险"]];
  return <><PageHeader title="其他险种" subtitle="保留产品架构，按研究优先级在 V1 之后逐步开放" /><div className="roadmap-grid">{items.map(([title, text], index) => <Card key={title} className="roadmap"><div className="roadmap__icon">{index < 2 ? <ShieldCheck /> : <Clock3 />}</div><div><StatusBadge tone="neutral">后续 V1+</StatusBadge><h2>{title}</h2><p>{text}</p></div></Card>)}</div><div className="notice"><Info size={18} />当前重点是来源采集、证据核验和同口径基础对比。</div></>;
}

function ImportPage({ openProduct, initialImportId }: { openProduct: (id: string) => void; initialImportId?: string | null }) {
  const [activeImport, setActiveImport] = useState<ImportView | null>(null);
  const [authority, setAuthority] = useState("CONTRACT_DOCUMENT");
  const [decisions, setDecisions] = useState<Record<string, { decision: string; edited_value?: string }>>({});
  const [manualOpen, setManualOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [published, setPublished] = useState<string | null>(null);
  const setImport = useCallback((value: unknown) => {
    const imported = value as ImportView;
    if ((imported as unknown as { cancelled?: boolean }).cancelled) return;
    setActiveImport(imported);
    setDecisions(Object.fromEntries(imported.candidates.map((item) => [item.id, { decision: "KEEP_UNVERIFIED" }])));
    setPublished(null);
  }, []);
  useEffect(() => {
    if (!initialImportId) return;
    policyLens.getImport(initialImportId).then(setImport).catch((reason) => setError(asError(reason)));
  }, [initialImportId, setImport]);
  const choosePdf = async () => {
    setBusy(true); setError("");
    try { setImport(await policyLens.chooseAndImportPdf(authority)); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const manual = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      setImport(await policyLens.importManual({
        display_name: form.get("display_name"), version_label: form.get("version_label"),
        jurisdiction: form.get("jurisdiction"), line_of_business: form.get("line_of_business"), currency: form.get("currency"),
        annual_premium: form.get("annual_premium"), renewal_mode: form.get("renewal_mode"),
        guarantee_period_years: Number(form.get("guarantee_period_years")), maximum_renewal_age: Number(form.get("maximum_renewal_age")),
        rate_adjustment_scope: form.get("rate_adjustment_scope"), benefit_limit: form.get("benefit_limit"),
        source_authority: form.get("source_authority"), evidence_note: form.get("evidence_note")
      }));
      setManualOpen(false);
    } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const submitReview = async () => {
    if (!activeImport) return;
    setBusy(true); setError("");
    try {
      const result = await policyLens.reviewImport(activeImport.id, { decisions: activeImport.candidates.map((candidate) => ({ candidate_id: candidate.id, ...decisions[candidate.id] })) }) as { product_version_id: string; import: ImportView };
      setActiveImport(result.import); setPublished(result.product_version_id);
    } catch (reason) { setError(asError(reason)); } finally { setBusy(false); }
  };
  const acceptAll = () => { if (activeImport) setDecisions(Object.fromEntries(activeImport.candidates.map((item) => [item.id, { decision: "ACCEPT" }]))); };
  return <>
    <PageHeader title="导入与核验" subtitle="只在本地解析文本型 PDF；所有候选字段都由你逐项确认" actions={<><select className="compact-select" value={authority} onChange={(event) => setAuthority(event.target.value)} aria-label="来源权威性"><option value="CONTRACT_DOCUMENT">正式合同/条款</option><option value="REGULATOR_PUBLICATION">监管披露</option><option value="INSURER_OFFICIAL_DISCLOSURE">保险公司正式披露</option><option value="INSURER_OFFICIAL_WEB">保险公司官网</option><option value="THIRD_PARTY_REFERENCE">第三方线索</option><option value="UNATTRIBUTED">来源不明</option></select><button className="button secondary" onClick={() => setManualOpen(!manualOpen)}><Plus size={18} />手工资料</button><button className="button primary" disabled={busy} onClick={() => void choosePdf()}><Upload size={18} />选择文本 PDF</button></>} />
    {error && <ErrorPanel message={error} />}
    <div className="stepper"><span className="done">1 选择资料</span><i /><span className={activeImport ? "done" : ""}>2 本地解析</span><i /><span className={activeImport ? "active" : ""}>3 字段核验</span><i /><span className={published ? "done" : ""}>4 保存入库</span></div>
    {manualOpen && <Card><div className="card-title"><h2>手工资料</h2><StatusBadge tone="warning">不要填写姓名、保单号或健康信息</StatusBadge></div><form className="form-grid" onSubmit={(event) => void manual(event)}><label>产品名称<input name="display_name" required defaultValue="SYNTHETIC 手工医疗示例" /></label><label>版本<input name="version_label" required defaultValue="Synthetic Manual 2026" /></label><label>司法辖区<select name="jurisdiction"><option>CN_MAINLAND</option><option>HK</option></select></label><label>险种<select name="line_of_business"><option>MEDICAL</option><option>ACCIDENT</option><option>CRITICAL_ILLNESS</option><option>ANNUITY</option><option>LIFE_SAVINGS</option><option>OTHER</option></select></label><label>币种<select name="currency"><option>CNY</option><option>HKD</option><option>USD</option></select></label><label>标准年费率<input name="annual_premium" required defaultValue="1280.00" pattern="\d+(\.\d{1,4})?" /></label><label>续保模式<select name="renewal_mode"><option>GUARANTEED_RENEWAL</option><option>CONDITIONAL_RENEWAL</option><option>NON_GUARANTEED_RENEWAL</option><option>NON_RENEWABLE</option><option>UNKNOWN</option></select></label><label>保证续保年数<input name="guarantee_period_years" type="number" min="0" max="100" defaultValue="6" /></label><label>最高续保年龄<input name="maximum_renewal_age" type="number" min="0" max="130" defaultValue="80" /></label><label>调费范围<select name="rate_adjustment_scope"><option>COHORT</option><option>PORTFOLIO</option><option>INDIVIDUAL</option><option>REGULATORY</option><option>UNKNOWN</option></select></label><label>责任限额<input name="benefit_limit" defaultValue="200000.00" /></label><label>来源权威性<select name="source_authority" defaultValue={authority}><option>CONTRACT_DOCUMENT</option><option>REGULATOR_PUBLICATION</option><option>INSURER_OFFICIAL_DISCLOSURE</option><option>INSURER_OFFICIAL_WEB</option><option>THIRD_PARTY_REFERENCE</option><option>UNATTRIBUTED</option></select></label><label className="span-two">证据摘录（最多 600 字）<textarea name="evidence_note" maxLength={600} required defaultValue="SYNTHETIC TEST ONLY：此段为从零编写的纯合成合同证据，不对应任何真实产品或家庭资料。" /></label><div className="form-actions span-two"><button className="button primary">生成待核验字段</button></div></form></Card>}
    {activeImport ? <div className="import-layout"><Card className="document-preview"><div className="card-title"><h2>文档预览</h2>{activeImport.duplicate && <StatusBadge tone="warning">内容哈希重复</StatusBadge>}</div><FileSearch size={48} /><strong>{activeImport.source.title}</strong><span>{activeImport.source.document_type} · {activeImport.source.page_count ? `${activeImport.source.page_count} 页` : "网页来源"}</span><code>SHA-256 {activeImport.source.sha256.slice(0, 12)}…{activeImport.source.sha256.slice(-8)}</code><div className="notice"><ShieldCheck size={18} />原文件已使用随机 DEK 加密到私有 vault；界面与日志不显示原始路径。</div></Card><Card className="candidate-panel"><div className="card-title"><h2>候选字段</h2>{activeImport.status === "WAITING_REVIEW" && <button className="link-button" onClick={acceptAll}><Check size={16} />全部接受</button>}</div><div className="candidate-list">{activeImport.candidates.map((candidate) => { const decision = decisions[candidate.id] ?? { decision: "KEEP_UNVERIFIED" }; return <div className="candidate" key={candidate.id}><div className="candidate__number">{candidate.page_number ?? "网"}</div><div className="candidate__main"><label>{fieldLabels[candidate.field_path] ?? candidate.field_path}<input value={decision.edited_value ?? candidate.value} disabled={activeImport.status !== "WAITING_REVIEW" || decision.decision !== "EDIT"} onChange={(event) => setDecisions({ ...decisions, [candidate.id]: { decision: "EDIT", edited_value: event.target.value } })} /></label><small>{candidate.page_number ? `第 ${candidate.page_number} 页` : "网页正文"} · {candidate.value_origin} · {candidate.source_authority}</small><blockquote>{candidate.excerpt}</blockquote></div><select value={activeImport.status === "WAITING_REVIEW" ? decision.decision : candidate.decision ?? "KEEP_UNVERIFIED"} disabled={activeImport.status !== "WAITING_REVIEW"} onChange={(event) => { const next = event.target.value === "EDIT" ? { decision: "EDIT", edited_value: candidate.value } : { decision: event.target.value }; setDecisions({ ...decisions, [candidate.id]: next }); }}><option value="KEEP_UNVERIFIED">保持待核验</option><option value="ACCEPT">接受</option><option value="EDIT">编辑后接受</option><option value="REJECT">拒绝</option></select></div>; })}</div>{activeImport.status === "WAITING_REVIEW" ? <div className="form-actions"><button className="button primary" disabled={busy} onClick={() => void submitReview()}><FileCheck2 size={18} />确认并发布版本</button></div> : published && <div className="success-panel"><BadgeCheck /><div><strong>产品版本已保存</strong><p>核验状态、值来源和证据权威性分别保留。</p></div><button className="button secondary" onClick={() => openProduct(published)}>查看字段证据</button></div>}</Card></div> : !manualOpen && <Card className="small-empty"><Upload /><h2>选择资料开始</h2><p>支持可提取文本的 PDF 或手工资料。扫描 PDF 会安全失败并提示“后续 V1”。</p></Card>}
    <div className="notice"><Info size={18} />图片 OCR、Excel 和官网采集属于后续 V1，本次不会上传云端处理。</div>
  </>;
}

function ProductDetailPage({ id, back }: { id: string | null; back: () => void }) {
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (id) policyLens.getProduct(id).then((value) => setProduct(value as ProductDetail)).catch((reason) => setError(asError(reason))); }, [id]);
  if (error) return <ErrorPanel message={error} />;
  if (!product) return <Loading />;
  return <><button className="back" onClick={back}>← 返回</button><PageHeader title={product.display_name} subtitle={`${product.jurisdiction} · ${product.line_of_business} · ${product.version_label}`} actions={<StatusBadge tone={product.record_status === "ACTIVE" ? "success" : "warning"}>{product.record_status}</StatusBadge>} /><div className="three-column"><ContractCard title="RenewalTerms" value={product.renewal_terms} /><ContractCard title="PremiumRate" value={product.premium_rate} /><ContractCard title="RateAdjustmentRule" value={product.rate_adjustment_rule} /></div><Card><div className="card-title"><h2>字段级证据</h2><span>{product.facts.length} 个事实版本</span></div><div className="fact-list">{product.facts.map((fact) => <article className="fact" key={fact.id}><div><h3>{fieldLabels[fact.field_path] ?? fact.field_path}</h3><strong>{fact.normalized_value} {fact.unit ?? ""}</strong><div className="badge-row"><StatusBadge tone={fact.verification_status === "VERIFIED" ? "success" : "warning"}>{fact.verification_status}</StatusBadge><StatusBadge tone="info">来源：{fact.value_origin}</StatusBadge><StatusBadge tone="neutral">保证属性：{fact.guarantee_type}</StatusBadge></div></div><div className="evidence-list">{fact.evidence.map((evidence) => <div className="evidence" key={evidence.id}><b>{evidence.id} · {evidence.page_number ? `第 ${evidence.page_number} 页` : "网页正文"}</b><span>{evidence.authority}</span><blockquote>{evidence.excerpt}</blockquote></div>)}</div></article>)}</div></Card><div className="notice"><Info size={18} />证据权威性、值来源与人工核验状态是三个独立维度；AI 不是证据来源。</div></>;
}

function ComparisonPage({ openProduct }: { openProduct: (id: string) => void }) {
  const [products, setProducts] = useState<ProductSummary[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<{ products: ProductDetail[]; notice: string } | null>(null);
  const [evidenceComparison, setEvidenceComparison] = useState<EvidenceComparisonView | null>(null);
  const [preview, setPreview] = useState<PreviewView | null>(null);
  const [previewSelection, setPreviewSelection] = useState<PreviewSelectionView | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<string[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [analysis, setAnalysis] = useState<AnalysisView | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { policyLens.listProducts(false).then((value) => setProducts(value as ProductSummary[])).catch((reason) => setError(asError(reason))); }, []);
  const toggle = (id: string) => setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : current.length < 4 ? [...current, id] : current);
  const compare = async () => { setBusy(true); setError(""); try { setEvidenceComparison(await policyLens.compareEvidence(selected) as EvidenceComparisonView); setComparison(selected.length === 2 ? await policyLens.compare(selected) as { products: ProductDetail[]; notice: string } : null); setPreview(null); setAnalysis(null); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); } };
  const makePreview = async (evidenceIds?: string[]) => { setBusy(true); setError(""); try { const result = await policyLens.previewCodex(selected, evidenceIds) as PreviewView | PreviewSelectionView; if ("requires_selection" in result) { setPreviewSelection(result); setSelectedEvidence(result.evidence_options.slice(0, 12).map((item) => item.evidenceId)); setPreview(null); } else { setPreview(result); setPreviewSelection(null); } setConfirmed(false); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); } };
  const run = async () => { if (!preview || !confirmed) return; setBusy(true); setError(""); try { const executed = await policyLens.runCodex(preview.payload); const evidenceIds = preview.payload.comparison.evidenceExcerpts.map((item) => item.evidenceId); const saved = await policyLens.saveAnalysis({ preview_hash: preview.preview_hash, evidence_ids: evidenceIds, result: executed.result, cli_version: executed.cliVersion, argument_profile: "EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1", prompt_template_version: "policylens-analysis-v1", exit_status: 0, schema_valid: true }); setAnalysis(saved as AnalysisView); } catch (reason) { setError(asError(reason)); } finally { setBusy(false); } };
  const updateStatus = async (status: "ACCEPTED_AS_NOTE" | "REJECTED") => { if (!analysis) return; setAnalysis(await policyLens.updateAnalysisStatus(analysis.id, status) as AnalysisView); };
  return <><PageHeader title="产品证据对比" subtitle="选择 2–4 个已核验版本，按同一字段查看值、状态和证据数量" actions={<button className="button primary" disabled={selected.length < 2 || busy} onClick={() => void compare()}><Scale size={18} />生成证据对比</button>} />{error && <ErrorPanel message={error} />}
    <Card><div className="card-title"><h2>选择 2–4 个版本</h2><span>{selected.length}/4</span></div>{products.length ? <div className="product-picker">{products.map((product) => <button key={product.version_id} className={selected.includes(product.version_id) ? "selected" : ""} onClick={() => toggle(product.version_id)}><span className="check-circle">{selected.includes(product.version_id) && <Check />}</span><strong>{product.display_name}</strong><small>{product.version_label} · {product.currency}</small></button>)}</div> : <div className="small-empty"><Scale /><p>还没有两个可比较的已核验版本。请先完成官方候选的逐字段核验。</p></div>}</Card>
    {evidenceComparison && <Card className="evidence-matrix"><div className="card-title"><h2>字段与证据矩阵</h2><StatusBadge tone="info">不排名、不推荐</StatusBadge></div><div className="matrix-scroll"><table><thead><tr><th>字段</th>{evidenceComparison.products.map((product) => <th key={product.version_id}>{product.display_name}<small>{product.version_label}</small></th>)}</tr></thead><tbody>{evidenceComparison.rows.map((row) => <tr key={row.field_path}><td><strong>{fieldLabels[row.field_path] ?? row.field_path}</strong></td>{row.cells.map((cell) => <td key={cell.version_id}><strong>{cell.value ?? "未知"} {cell.unit ?? ""}</strong><small>{cell.verification_status} · {cell.guarantee_type}</small><small>{cell.evidence_count} 条证据{cell.evidence_ids.length ? ` · ${cell.evidence_ids.join("、")}` : ""}</small></td>)}</tr>)}</tbody></table></div><div className="notice"><Info />{evidenceComparison.notice}</div></Card>}
    {comparison && <><div className="comparison-grid">{comparison.products.map((product) => <Card key={product.version_id} className="comparison-product"><div className="card-title"><div><h2>{product.display_name}</h2><span>{product.version_label}</span></div><button className="icon-button" onClick={() => openProduct(product.version_id)} aria-label="查看证据"><FileSearch /></button></div><ComparisonRows product={product} /></Card>)}</div><div className="notice warning"><CircleAlert size={18} />{comparison.notice}</div><Card className="codex-card"><div><div className="card-title"><h2><Sparkles size={21} />Codex 研究草稿</h2><StatusBadge tone="neutral">仅限两个产品</StatusBadge></div><p>完整白名单预览和逐次确认仍保留；AI 草稿不会改变事实状态。</p></div><button className="button secondary" onClick={() => void makePreview()} disabled={busy}><Bot size={18} />生成外发预览</button></Card></>}
    {previewSelection && <Card className="preview"><div className="card-title"><h2>主动选择外发证据</h2><StatusBadge tone="warning">{selectedEvidence.length}/12 段</StatusBadge></div><div className="notice warning"><CircleAlert size={18} />{previewSelection.message} 系统不会静默截断关键上下文。</div><div className="evidence-options">{previewSelection.evidence_options.map((item) => <label key={item.evidenceId}><input type="checkbox" checked={selectedEvidence.includes(item.evidenceId)} disabled={!selectedEvidence.includes(item.evidenceId) && selectedEvidence.length >= 12} onChange={(event) => setSelectedEvidence((current) => event.target.checked ? [...current, item.evidenceId] : current.filter((id) => id !== item.evidenceId))} /><div><strong>{item.product} · {fieldLabels[item.field] ?? item.field}</strong><small>{item.evidenceId} · {item.authority}</small><p>{item.text}</p></div></label>)}</div><div className="form-actions"><button className="button primary" disabled={!selectedEvidence.length || busy} onClick={() => void makePreview(selectedEvidence)}>使用所选证据生成完整预览</button></div></Card>}
    {preview && <Card className="preview"><div className="card-title"><h2>Codex 白名单外发预览</h2><StatusBadge tone="warning">{preview.excerpt_count} 段 / {preview.excerpt_characters} 字</StatusBadge></div>{preview.warnings.map((warning) => <div className="notice warning" key={warning}><CircleAlert size={17} />{warning}</div>)}<pre>{JSON.stringify(preview.payload, null, 2)}</pre><label className="confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已逐项查看本次完整预览，并主动确认只发送以上内容</label><div className="form-actions"><button className="button primary" disabled={!confirmed || busy} onClick={() => void run()}><Sparkles size={18} />确认并调用 Codex</button>{busy && <button className="button secondary" onClick={() => void policyLens.cancelCodex()}>取消运行</button>}</div></Card>}
    {analysis && <Card className="analysis"><div className="card-title"><h2><Bot size={21} />AI 草稿</h2><StatusBadge tone={analysis.status === "DRAFT" ? "warning" : analysis.status === "ACCEPTED_AS_NOTE" ? "success" : "neutral"}>{analysis.status}</StatusBadge></div><p className="analysis-summary">{analysis.result.summary}</p><h3>关键差异</h3>{analysis.result.differences.map((item) => <div className="analysis-item" key={item.title}><strong>{item.title}</strong><p>{item.explanation}</p><small>{item.evidence_ids.join("、") || "未引用具体证据"}</small></div>)}<div className="analysis-columns"><div><h3>未知项</h3><ul>{analysis.result.unknowns.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h3>风险</h3><ul>{analysis.result.risks.map((item) => <li key={item}>{item}</li>)}</ul></div><div><h3>人工核验问题</h3><ul>{analysis.result.questions_for_human_review.map((item) => <li key={item}>{item}</li>)}</ul></div></div><div className="notice"><ShieldCheck size={18} />AI 结果未改变任何事实的 VerificationStatus。</div>{analysis.status === "DRAFT" && <div className="form-actions"><button className="button secondary" onClick={() => void updateStatus("REJECTED")}>拒绝草稿</button><button className="button primary" onClick={() => void updateStatus("ACCEPTED_AS_NOTE")}>仅接受为笔记</button></div>}</Card>}
  </>;
}

function ComparisonRows({ product }: { product: ProductDetail }) {
  return <div className="comparison-rows"><KeyRow label="标准年费率" value={money(String(product.premium_rate?.amount ?? ""), String(product.premium_rate?.currency ?? product.currency))} /><KeyRow label="续保模式" value={String(product.renewal_terms?.renewal_mode ?? "UNKNOWN")} /><KeyRow label="保证续保期间" value={`${String(product.renewal_terms?.guarantee_period_years ?? "未知")} 年`} /><KeyRow label="最高续保年龄" value={`${String(product.renewal_terms?.maximum_renewal_age ?? "未知")} 岁`} /><KeyRow label="调费范围" value={String(product.rate_adjustment_rule?.scope ?? "UNKNOWN")} /><KeyRow label="证据字段" value={`${product.facts.filter((item) => item.verification_status === "VERIFIED").length} / ${product.facts.length} 已核验`} /></div>;
}

function SearchPage({ query, openProduct, openImport }: { query: string; openProduct: (id: string) => void; openImport: (id: string) => void }) {
  const [result, setResult] = useState<SearchResultView | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (query.trim().length < 2) { setResult(null); return; }
    policyLens.search(query).then((value) => setResult(value as SearchResultView)).catch((reason) => setError(asError(reason)));
  }, [query]);
  return <><PageHeader title="本地证据搜索" subtitle={query ? `搜索“${query}”的正式产品、待核验候选和来源` : "输入至少两个字符，搜索已经保存的产品、候选与来源"} />{error && <ErrorPanel message={error} />}{query.trim().length < 2 ? <Card className="small-empty"><Search /><p>在顶部搜索框输入产品名称、版本、保险公司或来源标题，然后按 Enter。</p></Card> : !result ? <Loading /> : <div className="search-grid"><Card><div className="card-title"><h2>正式产品</h2><span>{result.products.length}</span></div>{result.products.length ? <div className="list">{result.products.map((product) => <button className="search-result" key={product.version_id} onClick={() => openProduct(product.version_id)}><FileCheck2 /><span><strong>{product.display_name}</strong><small>{product.version_label} · {product.record_status}</small></span><ChevronRight /></button>)}</div> : <div className="small-empty"><Search /><p>没有匹配正式产品。</p></div>}</Card><Card><div className="card-title"><h2>待核验候选</h2><span>{result.candidates.length}</span></div>{result.candidates.length ? <div className="list">{result.candidates.map((candidate) => <button className="search-result" key={candidate.import_id} onClick={() => openImport(candidate.import_id)}><CircleAlert /><span><strong>{candidate.display_name}</strong><small>{candidate.version_label} · {candidate.review_status}</small></span><ChevronRight /></button>)}</div> : <div className="small-empty"><FileSearch /><p>没有匹配研究候选。</p></div>}</Card><Card><div className="card-title"><h2>来源</h2><span>{result.sources.length}</span></div>{result.sources.length ? <div className="list">{result.sources.map((source) => <div className="list-row" key={source.id}><BookOpen /><div><strong>{source.title}</strong><span>{source.authority} · {source.status}</span></div></div>)}</div> : <div className="small-empty"><BookOpen /><p>没有匹配来源。</p></div>}</Card></div>}</>;
}

function PlanningPage({ go }: { go: (page: Page) => void }) {
  const items: Array<[string, string, Page, ReactNode]> = [
    ["本地资料导入", "保留原有 PDF 和手工资料核验能力。", "import", <Upload key="import" />],
    ["其他保险研究", "内地、宠物及其他险种等待下一批官方来源适配。", "other-lines", <ShieldCheck key="mainland" />],
    ["养老现金流", "保证/非保证、XIRR 和汇率情景尚未实现。", "retirement", <BarChart3 key="retirement" />],
    ["复盘提醒", "本地日历和来源过期检查尚未实现。", "reminders", <Bell key="reminders" />]
  ];
  return <><PageHeader title="规划中与辅助工具" subtitle="未完成模块集中在这里，不再占据核心研究导航" /><div className="roadmap-grid">{items.map(([title, description, page, icon]) => <Card className="roadmap" key={title}><div className="roadmap__icon">{icon}</div><div><StatusBadge tone={page === "import" ? "success" : "neutral"}>{page === "import" ? "已可用" : "规划中"}</StatusBadge><h2>{title}</h2><p>{description}</p><button className="link-button" onClick={() => go(page)}>{page === "import" ? "打开工具" : "查看边界"}<ChevronRight /></button></div></Card>)}</div></>;
}

function SourcesPage() {
  const [sources, setSources] = useState<SourceView[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { policyLens.listSources().then((value) => setSources(value as SourceView[])).catch((reason) => setError(asError(reason))); }, []);
  if (error) return <ErrorPanel message={error} />;
  return <><PageHeader title="来源与证据中心" subtitle="官方网页、PDF、内容修订、哈希和字段证据都保留可追溯关系" />{sources === null ? <Loading /> : <><div className="metric-grid metric-grid--three"><Card className="metric"><BookOpen /><div><span>本地来源</span><strong>{sources.length}</strong></div></Card><Card className="metric"><BadgeCheck /><div><span>已核验来源</span><strong>{sources.filter((item) => item.status === "VERIFIED").length}</strong></div></Card><Card className="metric"><FileSearch /><div><span>证据锚点</span><strong>{sources.reduce((sum, item) => sum + item.evidence_count, 0)}</strong></div></Card></div>{sources.length ? <Card className="table-card"><table><thead><tr><th>来源</th><th>权威性</th><th>官方地址</th><th>SHA-256</th><th>证据</th><th>状态</th></tr></thead><tbody>{sources.map((source) => <tr key={source.id}><td><strong>{source.title}</strong><small>{source.document_type}{source.fetched_at ? ` · ${source.fetched_at.slice(0, 10)}` : ""}</small></td><td>{source.authority}</td><td><small className="source-url">{source.canonical_url ?? "本地导入"}</small></td><td><code>{source.sha256.slice(0, 10)}…{source.sha256.slice(-6)}</code></td><td>{source.evidence_count}</td><td><StatusBadge tone={source.status === "VERIFIED" ? "success" : "warning"}>{source.status}</StatusBadge></td></tr>)}</tbody></table></Card> : <Card className="small-empty"><BookOpen /><p>尚无来源。完成一次公开研究或导入本地资料后，这里会显示内容哈希和证据状态。</p></Card>}</>}<div className="notice"><Info size={18} />第三方内容只作为发现线索；产品事实必须落到保险公司官方来源并经过人工核验。</div></>;
}

function SettingsPage() {
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [runtime, setRuntime] = useState<Record<string, unknown> | null>(null);
  const [backupPassword, setBackupPassword] = useState("");
  const [backupConfirm, setBackupConfirm] = useState("");
  const [restorePassword, setRestorePassword] = useState("");
  const [restore, setRestore] = useState<RestorePreview | null>(null);
  const [restoreConfirmed, setRestoreConfirmed] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const refresh = useCallback(() => { Promise.all([policyLens.getSettings(), policyLens.getRuntimeInfo()]).then(([s, r]) => { setSettings(s as Record<string, unknown>); setRuntime(r as Record<string, unknown>); }).catch((reason) => setError(asError(reason))); }, []);
  useEffect(refresh, [refresh]);
  const backup = async () => { setError(""); setMessage(""); if (backupPassword !== backupConfirm) { setError("两次输入的恢复密码不一致。"); return; } if (backupPassword.length < 12) { setError("恢复密码至少需要 12 个字符。"); return; } try { const result = await policyLens.createBackup(backupPassword) as { cancelled?: boolean; file_name?: string; payload_sha256?: string }; if (!result.cancelled) { setMessage(`备份已验证并保存：${result.file_name}（校验 ${result.payload_sha256?.slice(0, 12)}…）`); setBackupPassword(""); setBackupConfirm(""); } } catch (reason) { setError(asError(reason)); } };
  const copyDataPath = async () => { setError(""); try { await policyLens.copyDataDirectory(); setMessage("数据目录路径已复制，请粘贴到资源管理器地址栏。"); } catch (reason) { setError(asError(reason)); } };
  const previewRestore = async () => { setError(""); setMessage(""); if (restorePassword.length < 12) { setError("请输入至少 12 个字符的恢复密码。"); return; } try { const result = await policyLens.previewRestore(restorePassword) as RestorePreview & { cancelled?: boolean }; if (!result.cancelled) { setRestore(result); setRestoreConfirmed(false); } } catch (reason) { setError(asError(reason)); } };
  const commitRestore = async () => { if (!restore || !restoreConfirmed) return; try { const result = await policyLens.commitRestore(restore.restore_token) as { safety_snapshot: string }; setMessage(`恢复成功，当前机器已重新包装 DEK；安全快照：${result.safety_snapshot}`); setRestore(null); setRestorePassword(""); setRestoreConfirmed(false); refresh(); } catch (reason) { setError(asError(reason)); } };
  return <><PageHeader title="设置" subtitle="本地优先、隐私可控、AI 可审计" />{error && <ErrorPanel message={error} />}{message && <div className="notice success"><BadgeCheck size={18} />{message}</div>}{!settings || !runtime ? <Loading /> : <div className="settings-grid"><Card><div className="card-title"><h2><Database />本地数据</h2><StatusBadge tone="success">AES-256-GCM</StatusBadge></div><KeyValue data={{ 数据目录: settings.data_directory, 数据库目录: settings.database_directory, 加密: settings.encryption, 本机密钥包装: settings.local_key_wrapper, 遥测: "关闭" }} /><button className="button secondary full" onClick={() => void copyDataPath()}><FolderOpen size={18} />复制数据目录路径</button></Card><Card><div className="card-title"><h2><Laptop />运行状态</h2><StatusBadge tone="success">浏览器本地模式</StatusBadge></div><KeyValue data={{ "Web 服务 PID": runtime.servicePid, 托管方式: runtime.manager, 监听地址: `${String(runtime.serviceHost)}:${String(runtime.servicePort)}`, 端口管理: "RunDock", 会话保护: runtime.sessionProtection }} /></Card><Card><div className="card-title"><h2><KeyRound />便携加密备份</h2><StatusBadge tone="info">Argon2id</StatusBadge></div><p>恢复密码用于另一台电脑。密码不会保存；丢失后无法跨机器恢复。</p><label>恢复密码（至少 12 字符）<input type="password" autoComplete="new-password" value={backupPassword} onChange={(event) => setBackupPassword(event.target.value)} /></label><label>再次输入恢复密码<input type="password" autoComplete="new-password" value={backupConfirm} onChange={(event) => setBackupConfirm(event.target.value)} /></label><button className="button primary full" onClick={() => void backup()}><LockKeyhole size={18} />验证密码并下载备份</button><small>{String(settings.portable_backup_kdf)}</small></Card><Card><div className="card-title"><h2><RotateCcw />跨机器恢复</h2><StatusBadge tone="warning">先验证，后切换</StatusBadge></div><p>错误密码、篡改或版本不兼容会在修改当前数据之前失败。</p><label>备份恢复密码<input type="password" autoComplete="current-password" value={restorePassword} onChange={(event) => setRestorePassword(event.target.value)} /></label><button className="button secondary full" onClick={() => void previewRestore()}><FolderOpen size={18} />上传备份并验证</button>{restore && <div className="restore-preview"><h3>恢复摘要</h3><KeyValue data={{ 来源: restore.source_count, 产品: restore.product_count, 保单: restore.policy_count, 备份时间: restore.backup_created_at, 当前数据: restore.current_data_unchanged ? "尚未修改" : "异常" }} /><label className="confirm"><input type="checkbox" checked={restoreConfirmed} onChange={(event) => setRestoreConfirmed(event.target.checked)} />我确认用已验证备份切换当前数据</label><button className="button primary full" disabled={!restoreConfirmed} onClick={() => void commitRestore()}>确认恢复并重新绑定 DPAPI</button></div>}</Card><Card className="span-two"><div className="card-title"><h2><Bot />Codex CLI 隐私边界</h2><StatusBadge tone="neutral">逐次确认</StatusBadge></div><div className="privacy-grid"><PrivacyItem ok text="只发送直接构造的白名单 DTO" /><PrivacyItem ok text="不发送原始 PDF、完整正文或私人路径" /><PrivacyItem ok text="不发送姓名、电话、证件号或完整保单号" /><PrivacyItem ok text="单段 ≤600 字，最多 12 段，总计 ≤7200 字" /><PrivacyItem ok text="不覆盖模型、Provider、登录或认证配置" /><PrivacyItem ok text="AI 结果只保存为 DRAFT 或用户接受的笔记" /></div><div className="notice warning"><CircleAlert size={18} />Codex 进程拥有当前 Windows 用户权限；工作目录、临时目录和只读 sandbox 只能作为纵深防御，不是保密边界。</div></Card></div>}</>;
}

function PrivacyItem({ ok, text }: { ok: boolean; text: string }) { return <div className="privacy-item">{ok ? <Check /> : <CircleAlert />}<span>{text}</span></div>; }

function ContractCard({ title, value }: { title: string; value: Record<string, unknown> | null }) { return <Card><h2>{title}</h2>{value ? <KeyValue data={Object.fromEntries(Object.entries(value).filter(([key]) => !["id", "product_version_id"].includes(key)))} /> : <p className="muted">暂无记录</p>}</Card>; }
function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未知";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || typeof value === "bigint") return String(value);
  return "不支持的值";
}
function KeyValue({ data }: { data: Record<string, unknown> }) { return <dl className="key-value">{Object.entries(data).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{displayValue(value)}</dd></div>)}</dl>; }
function KeyRow({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function ErrorPanel({ message }: { message: string }) { return <div className="error-panel" role="alert"><CircleAlert /><div><strong>操作未完成</strong><p>{message}</p></div></div>; }

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [searchDraft, setSearchDraft] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const activeNav = useMemo(() => page === "policy-detail" ? "policies" : page === "product-detail" ? "hong-kong" : page === "import" || page === "retirement" || page === "reminders" || page === "pet" || page === "other-lines" ? "mainland" : page === "search" ? "dashboard" : page, [page]);
  const go = (target: Page) => { setPage(target); setSelectedId(null); };
  const openPolicy = (id: string) => { setSelectedId(id); setPage("policy-detail"); };
  const openProduct = (id: string) => { setSelectedId(id); setPage("product-detail"); };
  const openImport = (id: string) => { setSelectedId(id); setPage("import"); };
  const submitSearch = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (searchDraft.trim().length >= 2) { setSearchQuery(searchDraft.trim()); setPage("search"); setSelectedId(null); } };
  let content: ReactNode;
  switch (page) {
    case "dashboard": content = <DashboardPage go={go} />; break;
    case "search": content = <SearchPage query={searchQuery} openProduct={openProduct} openImport={openImport} />; break;
    case "policies": content = <PoliciesPage openPolicy={openPolicy} go={go} />; break;
    case "policy-detail": content = <PolicyDetailPage id={selectedId} back={() => go("policies")} />; break;
    case "mainland": content = <PlanningPage go={go} />; break;
    case "hong-kong": content = <HongKongResearchPage openImport={openImport} openProduct={openProduct} />; break;
    case "pet": content = <ProductLibraryPage market="pet" go={go} />; break;
    case "other-lines": content = <OtherLinesPage />; break;
    case "product-detail": content = <ProductDetailPage id={selectedId} back={() => go("hong-kong")} />; break;
    case "comparison": content = <ComparisonPage openProduct={openProduct} />; break;
    case "import": content = <ImportPage openProduct={openProduct} initialImportId={selectedId} />; break;
    case "retirement": content = <><PageHeader title="养老现金流规划" subtitle="保证/非保证、XIRR、回本和汇率情景将在后续 V1 开放" /><EmptyV1 icon={<BarChart3 size={36} />} title="养老规划正在准备" description="后续将提供确定性现金流、寿命情景、保证/非保证分栏和独立复算。" /></>; break;
    case "sources": content = <SourcesPage />; break;
    case "reminders": content = <><PageHeader title="复盘与提醒" subtitle="本地日历、年度复盘和来源过期检查将在后续 V1 开放" /><EmptyV1 icon={<Bell size={36} />} title="复盘提醒尚未实现" description="应用不会自动续费、购买或修改任何保单。" /></>; break;
    case "settings": content = <SettingsPage />; break;
  }
  return <div className="app-shell" data-testid="app-shell"><aside className="sidebar"><button className="brand" onClick={() => go("dashboard")} aria-label="PolicyLens 首页"><span className="brand-mark"><ShieldCheck /></span><strong>PolicyLens</strong></button><nav>{navItems.map((item) => { const Icon = item.icon; return <button key={item.page} className={activeNav === item.page ? "active" : ""} onClick={() => go(item.page)}><Icon /><span>{item.label}</span></button>; })}</nav><div className="sidebar-foot"><ShieldCheck /><span>本地优先<br /><small>公开研究逐次确认</small></span></div></aside><section className="workspace"><div className="topbar"><form className="searchbox" onSubmit={submitSearch}><Search /><input aria-label="全局搜索" placeholder="搜索本地产品、版本或来源后按 Enter" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} /></form><div className="local-mode"><Laptop />本地模式</div></div><main>{content}</main></section></div>;
}

