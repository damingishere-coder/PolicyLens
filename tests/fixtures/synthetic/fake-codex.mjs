import { readFileSync, writeFileSync } from "node:fs";

const args = process.argv.slice(2);
if (args.includes("--version")) {
  process.stdout.write("codex-cli synthetic-test-1.0\n");
  process.exit(0);
}

for (const forbidden of ["--model", "--oss", "--local-provider", "--add-dir", "--dangerously-bypass-approvals-and-sandbox"]) {
  if (args.includes(forbidden)) process.exit(41);
}
for (const required of ["exec", "--skip-git-repo-check", "--ephemeral", "--json", "--sandbox", "read-only", "--output-schema", "--cd", "-"]) {
  if (!args.includes(required)) process.exit(42);
}
const outputIndex = args.indexOf("--output-last-message") + 1;
if (outputIndex <= 0 || !args[outputIndex]) process.exit(43);

let prompt = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) prompt += chunk;
const payload = JSON.parse(prompt.slice(prompt.lastIndexOf("\n\n") + 2));
const evidenceIds = payload.comparison.evidenceExcerpts.map((item) => item.evidenceId);
const invalid = payload.comparison.products.some((item) => item.displayName === "RETURN_INVALID_REF");
const result = {
  summary: "这是由假 Codex 进程生成的纯合成结构化草稿。",
  differences: [{
    title: "合成费率差异",
    explanation: "两个纯合成产品的标准费率和续保条件不同。",
    evidence_ids: invalid ? ["EV-OUTSIDE-PREVIEW"] : evidenceIds.slice(0, 2)
  }],
  unknowns: ["未来调费幅度未知。"],
  risks: ["保证续保不表示保费固定。"],
  questions_for_human_review: ["请核验调费通知期。"],
  calculation_refs: []
};
writeFileSync(args[outputIndex], JSON.stringify(result), "utf8");
process.stdout.write(JSON.stringify({ type: "turn.completed", synthetic: true }) + "\n");
