export const verificationStatuses = [
  "UNVERIFIED",
  "VERIFIED",
  "CONFLICTING",
  "STALE",
  "REJECTED"
] as const;

export const valueOrigins = [
  "MANUAL_ENTRY",
  "STRUCTURED_IMPORT",
  "RULE_EXTRACTION",
  "AI_EXTRACTION",
  "DETERMINISTIC_CALCULATION",
  "USER_ASSUMPTION"
] as const;

export const sourceAuthorities = [
  "CONTRACT_DOCUMENT",
  "REGULATOR_PUBLICATION",
  "INSURER_OFFICIAL_DISCLOSURE",
  "INSURER_OFFICIAL_WEB",
  "THIRD_PARTY_REFERENCE",
  "UNATTRIBUTED"
] as const;

export type VerificationStatus = (typeof verificationStatuses)[number];
export type ValueOrigin = (typeof valueOrigins)[number];
export type SourceAuthority = (typeof sourceAuthorities)[number];
export type AnalysisStatus = "DRAFT" | "ACCEPTED_AS_NOTE" | "REJECTED";
export type GuaranteeType = "CONTRACT_GUARANTEED" | "NON_GUARANTEED" | "UNKNOWN";

export interface EvidenceAnchor {
  id: string;
  sourceId: string;
  pageNumber: number;
  excerpt: string;
  excerptHash: string;
  authority: SourceAuthority;
}

export interface FactView {
  id: string;
  fieldPath: string;
  value: string;
  unit: string | null;
  guaranteeType: GuaranteeType;
  verificationStatus: VerificationStatus;
  valueOrigin: ValueOrigin;
  evidence: EvidenceAnchor[];
}

export interface RenewalTerms {
  renewalMode: "GUARANTEED_RENEWAL" | "CONDITIONAL_RENEWAL" | "NON_GUARANTEED_RENEWAL" | "NON_RENEWABLE" | "UNKNOWN";
  guaranteePeriodYears: number | null;
  maximumRenewalAge: number | null;
  requiresReunderwriting: boolean | null;
  reassessesHealth: boolean | null;
  waitingPeriodDays: number | null;
  continuityConditions: string | null;
  discontinuationTreatment: string | null;
  terminationConditions: string | null;
}

export interface PremiumRate {
  versionLabel: string;
  validFrom: string | null;
  validTo: string | null;
  currency: string;
  frequency: string;
  amount: string;
  pricingDimensions: Record<string, string>;
}

export interface RateAdjustmentRule {
  scope: "INDIVIDUAL" | "COHORT" | "PORTFOLIO" | "REGULATORY" | "UNKNOWN";
  triggerConditions: string | null;
  frequency: string | null;
  noticeDays: number | null;
  cap: string | null;
  floor: string | null;
  effectiveFrom: string | null;
}

export interface PolicyPremiumRecord {
  id: string;
  dueAmount: string;
  paidAmount: string | null;
  currency: string;
  frequency: string;
  dueDate: string;
  paidDate: string | null;
  premiumRateId: string | null;
}

export interface CodexAnalysis {
  summary: string;
  differences: Array<{ title: string; explanation: string; evidence_ids: string[] }>;
  unknowns: string[];
  risks: string[];
  questions_for_human_review: string[];
  calculation_refs: string[];
}

export interface CodexPreview {
  schemaVersion: "1.0";
  comparison: {
    products: Array<{
      publicId: string;
      displayName: string;
      versionLabel: string;
      jurisdiction: string;
      currency: string;
      facts: Array<{
        field: string;
        value: string;
        unit: string | null;
        guaranteeType: GuaranteeType;
        verificationStatus: VerificationStatus;
        valueOrigin: ValueOrigin;
        evidenceIds: string[];
      }>;
    }>;
    evidenceExcerpts: Array<{ evidenceId: string; text: string; authority: SourceAuthority }>;
  };
}
