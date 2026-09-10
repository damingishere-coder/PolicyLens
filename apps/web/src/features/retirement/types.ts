import type { components } from "@policylens/contracts/generated";
export type PlanInput = components["schemas"]["RetirementInput"];
export type Income = Required<components["schemas"]["RetirementIncome"]>;
export type Plan = Omit<Required<components["schemas"]["RetirementView"]>,"incomes"> & { incomes: Income[] };
export type Snapshot = components["schemas"]["RetirementSnapshot"];
export type Calculation = components["schemas"]["RetirementResult"];
export const incomeKinds = { GUARANTEED:"用户标记的确定收入（待核实）", ESTIMATE:"用户估计收入", NON_GUARANTEED:"非保证演示收入" };
