import type { components } from "@policylens/contracts/generated";
import { jsonBody,request } from "./http";

type Schema = components["schemas"];
export type Member = Required<Schema["MemberView"]>;
export type Policy = Omit<Required<Schema["PolicyView"]>, "premium_records"> & { premium_records: Payment[] };
export type Payment = Required<Schema["PaymentView"]>;
export type Task = Required<Schema["TaskView"]>;
export type Summary = Omit<Schema["HouseholdSummary"], "members" | "policies" | "tasks"> & { members: Member[]; policies: Policy[]; tasks: Task[] };
export type MemberInput = Schema["MemberInput"];
export type PolicyInput = Schema["PolicyInput"];
export type PaymentInput = Schema["PaymentInput"];
export type HistoryEntry = Schema["PolicyHistoryView"];
export const familyBase = "/api/v1/household";
const path = (kind: string, id?: string) => `${familyBase}/${kind}${id ? `/${encodeURIComponent(id)}` : ""}`;

export const familyApi = {
  member: (value: MemberInput, existing?: Member) => request<Member>(path("members", existing?.id), jsonBody(existing ? { ...value, expected_revision: existing.revision } : value, existing ? "PUT" : "POST")),
  policy: (value: PolicyInput, existing?: Policy) => request<Policy>(path("policies", existing?.id), jsonBody(existing ? { ...value, expected_revision: existing.revision } : value, existing ? "PUT" : "POST")),
  payment: (policyId: string, value: PaymentInput, existing?: Payment) => request<Payment>(`${path("policies", policyId)}/payments${existing ? `/${encodeURIComponent(existing.id)}` : ""}`, jsonBody(existing ? { ...value, expected_revision: existing.revision } : value, existing ? "PUT" : "POST")),
  createTask: (value: Schema["TaskInput"]) => request<Task>(path("tasks"), jsonBody(value)),
  task: (task: Task, value: Omit<Schema["TaskAction"], "expected_revision">) => request<Task>(path("tasks", task.id), jsonBody({ ...value, expected_revision: task.revision }, "PUT")),
};
