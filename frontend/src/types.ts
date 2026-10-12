export interface SourceRecord {
  id: string;
  row_id: string;
  date: string;
  amount: number;
  original: Record<string, string>;
  name?: string;
  reference?: string;
  method?: string;
  members?: SourceRecord[];
  [key: string]: unknown;
}
export interface Evidence {
  score: number;
  difference: number;
  relative_difference: number;
  calendar_days: number;
  business_days: number;
  missing_evidence: string[];
  contradictions: string[];
  shared_references: string[][];
  breakdown: Record<
    string,
    { weight: number; value: number | null; effective_weight: number }
  >;
}
export interface Case {
  investigation?: Explanation | null;
  id: string;
  profile: string;
  left: SourceRecord;
  right: SourceRecord | null;
  evidence: Evidence | null;
  alternatives: { record: SourceRecord; evidence: Evidence }[];
  status: string;
  automated_status: string;
  effective_status: string;
  reason: string;
  residual: number;
  recommended_action: string;
  review?: { actor: string; note: string; new_status: string };
  settlement?: {
    gross: number;
    fees: number;
    taxes: number;
    refunds: number;
    adjustments: number;
    calculated_net: number;
    authoritative_net: number;
    integrity_difference: number;
    expected_date: string | null;
    settlement_delay_business_days: number | null;
    events: SourceRecord[];
    problems: string[];
  };
}
export interface Run {
  id: string;
  created: string;
  cases: Case[];
  config: Record<string, unknown>;
  metrics: {
    ledger_count: number;
    event_count: number;
    settlement_count: number;
    bank_count: number;
    statuses: Record<string, number>;
    matched: number;
    review: number;
    unmatched: number;
    outstanding_residual: number;
    expected_settlement: number;
    associated_bank_credits: number;
    confirmed_bank_credits: number;
    unexplained_variance: number;
  };
  provenance: { mode: string; hashes: Record<string, string> };
  unmatched_bank: SourceRecord[];
  unmatched_events: SourceRecord[];
}
export interface Imported {
  id: string;
  source: string;
  accepted: number;
  rejected_count: number;
  duplicate_count: number;
  records: SourceRecord[];
  rejected: { line: number; error: string; original: Record<string, string> }[];
  warnings: { row_id: string; error: string }[];
  headers: string[];
}
export interface Explanation {
  provider: string;
  state: string;
  explanation: {
    summary: string;
    recommended_action: string;
    data_sources_used: string[];
    supporting_evidence: string[];
    contradicting_evidence: string[];
    missing_evidence: string[];
    plausible_explanations: string[];
    reasoning_confidence: number;
    requires_human_review: boolean;
  };
}
export interface Settings {
  gemini: {
    state: string;
    model: string;
    requests_used: number;
    request_limit: number;
  };
  razorpay: {
    state: string;
    configured: boolean;
    connected: boolean;
    connection_tested: boolean;
    message: string;
    webhooks_configured: boolean;
  };
  config: Record<string, unknown>;
  calendar: { source: string; last_verified: string | null };
  sources: string[];
  required_columns: Record<string, string[]>;
  reports: string[];
  security: string;
}
