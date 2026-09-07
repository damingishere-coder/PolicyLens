import { writeFileSync } from "node:fs";

const args = process.argv.slice(2);
if (args.includes("--version")) {
  process.stdout.write("codex-cli synthetic-research-1.0\n");
  process.exit(0);
}

for (const forbidden of ["--model", "--oss", "--local-provider", "--add-dir", "--dangerously-bypass-approvals-and-sandbox"]) {
  if (args.includes(forbidden)) process.exit(51);
}
for (const required of ["--search", "exec", "--ephemeral", "--json", "--sandbox", "read-only", "--output-schema", "--output-last-message", "--cd", "-"]) {
  if (!args.includes(required)) process.exit(52);
}
if (args.indexOf("--search") > args.indexOf("exec")) process.exit(53);
const outputIndex = args.indexOf("--output-last-message") + 1;
if (outputIndex <= 0 || !args[outputIndex]) process.exit(54);

let prompt = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) prompt += chunk;
if (prompt.includes("--model") || !prompt.includes("aia.com.hk") || !prompt.includes("THIRD_PARTY_LEAD")) process.exit(55);

writeFileSync(args[outputIndex], JSON.stringify({ schema_version: "1.0", products: [], leads: [] }), "utf8");
process.stdout.write(JSON.stringify({ type: "turn.completed", synthetic: true }) + "\n");
