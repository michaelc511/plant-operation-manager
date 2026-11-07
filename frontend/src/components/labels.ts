import type { AnswerStatus, Route } from "../api/types";

export const STATUS_LABEL: Record<AnswerStatus, string> = {
  answered: "Answered",
  not_found: "Not in the documents",
  clarify: "Needs more detail",
  out_of_scope: "Outside the documents",
};

export const ROUTE_LABEL: Record<Route, string> = {
  safety: "Safety",
  maintenance: "Maintenance",
  quality: "Quality",
  out_of_scope: "Out of scope",
};

export const SAMPLE_QUESTIONS = [
  "How often do we grease the conveyor bearings on Line 3?",
  "What PPE do I need to clean the solvent tank?",
  "What's the diameter tolerance for part A-102?",
  "Can I replace a machine guard while the line is running?",
  "What torque do the HP-400 die clamp bolts need?",
  "What do I do with a part that fails inspection?",
];

export function pages(start: number, end: number): string {
  return start === end ? `p. ${start}` : `pp. ${start}-${end}`;
}
