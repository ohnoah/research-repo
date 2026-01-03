/**
 * Helicone CLI Types
 */

// ============================================================================
// Configuration Types
// ============================================================================

export interface Config {
  apiKey?: string;
  region?: "us" | "eu";
  defaultLimit?: number;
  defaultTimeRange?: string; // e.g., "7d", "30d", "24h"
}

export interface AuthContext {
  apiKey: string;
  region: "us" | "eu";
}

// ============================================================================
// API Response Types
// ============================================================================

export interface ApiResult<T> {
  data: T | null;
  error: string | null;
}

// ============================================================================
// Request Types
// ============================================================================

export interface HeliconeRequest {
  request_id: string;
  request_created_at: string;
  request_path: string;
  request_body?: unknown;
  request_user_id: string | null;
  request_properties: Record<string, string> | null;
  request_model: string | null;

  response_id: string | null;
  response_created_at: string | null;
  response_body?: unknown;
  response_status: number;
  response_model: string | null;

  model: string;
  provider: string;
  target_url: string;

  delay_ms: number | null;
  time_to_first_token: number | null;

  total_tokens: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;

  cost: number | null;
  costUSD?: number | null;

  country_code: string | null;
  cache_enabled: boolean;

  feedback_rating?: boolean | null;
  scores: Record<string, number> | null;
  properties: Record<string, string>;

  signed_body_url?: string | null;
}

// Slim version for table display
export interface RequestSummary {
  request_id: string;
  created_at: string;
  model: string;
  provider: string;
  status: number;
  latency_ms: number | null;
  tokens: number | null;
  cost: number | null;
  user_id: string | null;
}

// ============================================================================
// Session Types
// ============================================================================

export interface Session {
  session_id: string;
  session_name: string;
  created_at: string;
  latest_request_created_at: string;
  total_requests: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_cost: number;
  avg_latency: number;
}

export interface SessionSummary {
  session_id: string;
  name: string;
  requests: number;
  tokens: number;
  cost: number;
  avg_latency_ms: number;
  created_at: string;
  last_request_at: string;
}

// ============================================================================
// Filter Types
// ============================================================================

export type FilterOperator =
  | "equals"
  | "not-equals"
  | "contains"
  | "not-contains"
  | "gte"
  | "lte"
  | "gt"
  | "lt";

export interface FilterCondition {
  field: string;
  operator: FilterOperator;
  value: string | number | boolean;
}

export type FilterNode =
  | { [table: string]: { [field: string]: { [op: string]: unknown } } }
  | { left: FilterNode; operator: "and" | "or"; right: FilterNode }
  | "all";

// ============================================================================
// Query Parameters
// ============================================================================

export interface RequestQueryParams {
  filter?: FilterNode;
  offset?: number;
  limit?: number;
  sort?: { [field: string]: "asc" | "desc" };
  isCached?: boolean;
  includeInputs?: boolean;
  isPartOfExperiment?: boolean;
  isScored?: boolean;
}

export interface SessionQueryParams {
  search?: string;
  timeFilter: {
    startTimeUnixMs: number;
    endTimeUnixMs: number;
  };
  nameEquals?: string;
  timezoneDifference: number;
  filter: FilterNode;
  offset?: number;
  limit?: number;
}

// ============================================================================
// Output Options
// ============================================================================

export type OutputFormat = "table" | "json" | "jsonl" | "csv";

export interface OutputOptions {
  format: OutputFormat;
  fields?: string[];
  noHeaders?: boolean;
  raw?: boolean;
}

// ============================================================================
// CLI Command Options
// ============================================================================

export interface GlobalOptions {
  apiKey?: string;
  region?: "us" | "eu";
  quiet?: boolean;
}

export interface ListOptions extends GlobalOptions {
  limit?: number;
  offset?: number;
  format?: OutputFormat;
  fields?: string;
  since?: string;
  until?: string;
  model?: string;
  status?: string;
  userId?: string;
  property?: string[];
  minCost?: string;
  maxCost?: string;
  minLatency?: string;
  maxLatency?: string;
}

export interface ExportOptions extends ListOptions {
  output?: string;
  includeBody?: boolean;
  batchSize?: number;
}

export interface GetOptions extends GlobalOptions {
  format?: OutputFormat;
  includeBody?: boolean;
}
