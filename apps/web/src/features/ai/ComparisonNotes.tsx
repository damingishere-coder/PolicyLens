import { Card } from "@policylens/ui";
import { useResource } from "../../hooks/useResource";
import { ResourceState } from "../../components/feedback/ResourceState";
import type { AnalysisView } from "../research/types";

export function ComparisonNotes() {
  const resource=useResource<AnalysisView[]>("/api/v1/analyses");
  return <Card><h2>产品比较解读记录</h2><ResourceState error={resource.error} loading={!resource.data} retry={resource.refresh}>{resource.data?.length ? resource.data.map(note => <details key={note.id}><summary>{note.status === "ACCEPTED_AS_NOTE" ? "已接受为笔记" : note.status === "DRAFT" ? "待审阅草稿" : "已拒绝草稿"} · {note.result.summary}</summary><p>这是当次预览对应的历史解释；不表示当前条款已更新或重新核验。</p>{note.result.differences.map((item,index) => <article key={index}><h3>{item.title}</h3><p>{item.explanation}</p><small>{item.evidence_ids.join("、")}</small></article>)}<h3>未知项</h3><ul>{note.result.unknowns.map((text,index) => <li key={index}>{text}</li>)}</ul><h3>需要注意</h3><ul>{note.result.risks.map((text,index) => <li key={index}>{text}</li>)}</ul><h3>待人工核对</h3><ul>{note.result.questions_for_human_review.map((text,index) => <li key={index}>{text}</li>)}</ul></details>) : <p>暂无产品比较解读。</p>}</ResourceState></Card>;
}
