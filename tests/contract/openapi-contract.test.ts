import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";


interface OpenApiDocument {
  components: { schemas: Record<string, { enum?: string[]; additionalProperties?: boolean }> };
  paths: Record<string, unknown>;
}

describe("OpenAPI contract", () => {
  it("publishes independent verification, origin and authority enums", async () => {
    const raw = await readFile("packages/contracts/openapi.json", "utf8");
    const openapi = JSON.parse(raw) as OpenApiDocument;
    expect(openapi.components.schemas.VerificationStatus.enum).toEqual([
      "UNVERIFIED", "VERIFIED", "CONFLICTING", "STALE", "REJECTED"
    ]);
    expect(openapi.components.schemas.ValueOrigin.enum).toEqual([
      "MANUAL_ENTRY", "STRUCTURED_IMPORT", "RULE_EXTRACTION", "AI_EXTRACTION",
      "DETERMINISTIC_CALCULATION", "USER_ASSUMPTION"
    ]);
    expect(openapi.components.schemas.SourceAuthority.enum).toEqual([
      "CONTRACT_DOCUMENT", "REGULATOR_PUBLICATION", "INSURER_OFFICIAL_DISCLOSURE",
      "INSURER_OFFICIAL_WEB", "THIRD_PARTY_REFERENCE", "UNATTRIBUTED"
    ]);
  });

  it("rejects extra request fields and exposes the whole first-delivery API", async () => {
    const raw = await readFile("packages/contracts/openapi.json", "utf8");
    const openapi = JSON.parse(raw) as OpenApiDocument;
    expect(openapi.components.schemas.ManualMaterialRequest.additionalProperties).toBe(false);
    for (const route of [
      "/api/v1/imports/pdf",
      "/api/v1/imports/{import_id}/review",
      "/api/v1/comparisons/basic",
      "/api/v1/comparisons/evidence",
      "/api/v1/research/preview",
      "/api/v1/research/runs",
      "/api/v1/research/runs/{run_id}",
      "/api/v1/research/runs/{run_id}/cancel",
      "/api/v1/research/products",
      "/api/v1/search",
      "/api/v1/codex/preview",
      "/api/v1/codex/run",
      "/api/v1/backups/download",
      "/api/v1/restores/upload-preview",
      "/api/v1/restores/commit"
    ]) expect(openapi.paths).toHaveProperty(route);
  });
});
