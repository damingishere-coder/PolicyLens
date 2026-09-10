import { Card, StatusBadge } from "@policylens/ui";
import { amount } from "../../lib/labels";
import type { Calculation } from "./types";

export function RetirementResult({result}: {result:Calculation}) {
  return <Card className="retirement-result"><div className="card-title"><div><span className="eyebrow">{result.valuation_date ?? "参考时点待填写"} · {result.currency}</span><h2>当前参数下的月度收支</h2></div><StatusBadge tone={result.status === "READY" ? "info" : "warning"}>{result.status === "READY" ? "基于假设的计算" : "还需要一些信息"}</StatusBadge></div>
    {result.status === "INCOMPLETE" ? <div className="notice warning">尚缺：{result.missing_inputs.join("、")}。补齐前不生成缺口金额。</div> : <div className="retirement-scenarios">{result.scenarios.map((scenario,index) => <article className={index === 0 ? "baseline" : ""} key={scenario.name}><span className="eyebrow">情景 {index+1}</span><h3>{scenario.name}</h3><small>每月收支缺口</small><strong className="scenario-number">{amount(scenario.monthly_gap,result.currency)}</strong><dl><div><dt>月度收入</dt><dd>{amount(scenario.monthly_income,result.currency)}</dd></div><div><dt>月度支出</dt><dd>{amount(scenario.monthly_expense,result.currency)}</dd></div><div><dt>月度结余</dt><dd>{amount(scenario.monthly_surplus,result.currency)}</dd></div></dl></article>)}</div>}
    <div className="calculation-assumptions"><h3>理解这个结果</h3><ul>{result.assumptions.map(assumption => <li key={assumption}>{assumption}</li>)}</ul></div>
    <details><summary>查看计算口径与版本</summary><p>算法版本：{result.algorithm_version}。输入来自你的本地记录，结果是确定性计算，未升级为已核验事实。</p><code>输入校验：{result.input_hash}</code></details>
  </Card>;
}
