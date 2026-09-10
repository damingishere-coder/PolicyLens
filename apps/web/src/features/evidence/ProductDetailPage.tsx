import { Link } from "../../app/router";
import { Card,StatusBadge } from "@policylens/ui";
import {
Info
} from "lucide-react";
import { useEffect,useState } from "react";
import { policyLens } from "../../api";
import { asError,ContractCard,ErrorPanel,fieldLabels,Loading,PageHeader } from '../../components/layout/LegacyShared';
import type { ProductDetail } from '../research/types';
export function ProductDetailPage({ id, back }: { id: string | null; back: () => void }) {
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { if (id) policyLens.getProduct(id).then((value) => setProduct(value as ProductDetail)).catch((reason) => setError(asError(reason))); }, [id]);
  if (error) return <ErrorPanel message={error} />;
  if (!product) return <Loading />;
  return <><button className="back" onClick={back}>← 返回</button><PageHeader title={product.display_name} subtitle={`${product.jurisdiction} · ${product.line_of_business} · ${product.version_label}`} actions={<StatusBadge tone={product.record_status === "ACTIVE" ? "success" : "warning"}>{product.record_status}</StatusBadge>} /><div className="three-column"><ContractCard title="能否续保、有哪些条件" value={product.renewal_terms} /><ContractCard title="产品费率参考" value={product.premium_rate} /><ContractCard title="未来保费如何调整" value={product.rate_adjustment_rule} /></div><Card><div className="card-title"><h2>字段级证据</h2><span>{product.facts.length} 个事实版本</span></div><div className="fact-list">{product.facts.map((fact) => <article className="fact" key={fact.id}><div><h3>{fieldLabels[fact.field_path] ?? fact.field_path}</h3><strong>{fact.normalized_value} {fact.unit ?? ""}</strong><div className="badge-row"><StatusBadge tone={fact.verification_status === "VERIFIED" ? "success" : "warning"}>{fact.verification_status}</StatusBadge><StatusBadge tone="info">来源：{fact.value_origin}</StatusBadge><StatusBadge tone="neutral">保证属性：{fact.guarantee_type}</StatusBadge></div></div><div className="evidence-list">{fact.evidence.map((evidence) => <div className="evidence" key={evidence.id}><b>{evidence.id} · {evidence.page_number ? `第 ${evidence.page_number} 页` : "网页正文"}</b><span>{evidence.authority}</span><blockquote>{evidence.excerpt}</blockquote><Link href={`/library/${evidence.source_id}?kind=source&page=${evidence.page_number ?? 1}`}>查看原文与页码 →</Link></div>)}</div></article>)}</div></Card><div className="notice"><Info size={18} />证据权威性、值来源与人工核验状态是三个独立维度；AI 不是证据来源。</div></>;
}
