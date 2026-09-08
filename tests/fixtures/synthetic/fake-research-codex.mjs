import { readFileSync, writeFileSync } from "node:fs";

const args = process.argv.slice(2);
if (args.includes("--version")) {
  process.stdout.write("codex-cli synthetic-research-1.0\n");
  process.exit(0);
}

for (const forbidden of ["--model", "--oss", "--local-provider", "--add-dir", "--dangerously-bypass-approvals-and-sandbox"]) {
  if (args.includes(forbidden)) process.exit(51);
}
for (const required of ["--search", "exec", "--skip-git-repo-check", "--ephemeral", "--json", "--sandbox", "read-only", "--output-schema", "--output-last-message", "--cd", "-"]) {
  if (!args.includes(required)) process.exit(52);
}
if (args.indexOf("--search") > args.indexOf("exec")) process.exit(53);
const schema = JSON.parse(readFileSync(args[args.indexOf("--output-schema") + 1], "utf8"));
function checkStrict(node) {
  if (!node || typeof node !== "object") return;
  if (node.type === "object" && (node.additionalProperties !== false || Object.keys(node.properties).some((key) => !node.required?.includes(key)))) {
    process.stderr.write("Invalid schema: all properties must be required\n");
    process.exit(56);
  }
  for (const value of Object.values(node)) checkStrict(value);
}
checkStrict(schema);
const outputIndex = args.indexOf("--output-last-message") + 1;
if (outputIndex <= 0 || !args[outputIndex]) process.exit(54);

let prompt = "";
process.stdin.setEncoding("utf8");
for await (const chunk of process.stdin) prompt += chunk;
if (prompt.includes("--model") || !prompt.includes("aia.com.hk") || !prompt.includes("THIRD_PARTY_LEAD")) process.exit(55);

function product(insurerId, displayName, sourceUrl) {
  const facts = [
    ["product.display_name", displayName, `Official product name is ${displayName}`],
    ["product.version_label", "September 2026 official edition", "September 2026 official edition"],
    ["product.jurisdiction", "HK", "This product is issued in HK"],
    ["product.line_of_business", "LIFE_SAVINGS", "Product category is LIFE_SAVINGS"],
    ["product.currency", "HKD", "The primary illustration currency is HKD"],
    ["product.insurer_id", insurerId, `Official insurer identity is ${insurerId}`],
    ["product.sale_status", "ACTIVE", "Sale status is ACTIVE"],
    ["product.payment_term", "5 years", "Premium payment terms include 5 years"]
  ].map(([field_path, value, evidence_excerpt], index) => ({
    field_path,
    value,
    unit: null,
    guarantee_type: "UNKNOWN",
    evidence_excerpt,
    page_number: null,
    locator: `synthetic-section-${index + 1}`
  }));
  return {
    insurer_id: insurerId,
    display_name: displayName,
    version_label: "September 2026 official edition",
    source_title: `${displayName} official page`,
    source_url: sourceUrl,
    document_type: "OFFICIAL_WEB",
    facts
  };
}

writeFileSync(args[outputIndex], JSON.stringify({
  schema_version: "1.0",
  products: [
    product("aia-hk", "SYNTHETIC Future Savings Plan", "https://www.aia.com.hk/synthetic/future-savings"),
    product("prudential-hk", "SYNTHETIC Retirement Plan", "https://www.prudential.com.hk/synthetic/retirement-plan")
  ],
  leads: [{
    insurer_id: "manulife-hk",
    title: "SYNTHETIC third-party lead",
    url: "https://example.test/synthetic-manulife-lead",
    channel: "THIRD_PARTY_LEAD",
    official_verification_url: "https://www.manulife.com.hk/"
  }]
}), "utf8");
process.stdout.write(JSON.stringify({ type: "turn.completed", synthetic: true }) + "\n");
