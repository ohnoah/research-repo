/**
 * Helicone API Client with retry logic and proper error handling
 */

import type {
  AuthContext,
  ApiResult,
  HeliconeRequest,
  Session,
  RequestQueryParams,
  SessionQueryParams,
  FilterNode,
} from "./types.js";

// ============================================================================
// Constants
// ============================================================================

const API_ENDPOINTS = {
  us: "https://api.helicone.ai",
  eu: "https://eu.api.helicone.ai",
};

const DEFAULT_RETRY_OPTIONS = {
  maxRetries: 3,
  baseDelayMs: 1000,
};

// ============================================================================
// Client Class
// ============================================================================

export class HeliconeClient {
  private baseUrl: string;
  private apiKey: string;
  private maxRetries: number;
  private baseDelayMs: number;

  constructor(
    auth: AuthContext,
    options?: { maxRetries?: number; baseDelayMs?: number }
  ) {
    this.baseUrl = API_ENDPOINTS[auth.region];
    this.apiKey = auth.apiKey;
    this.maxRetries = options?.maxRetries ?? DEFAULT_RETRY_OPTIONS.maxRetries;
    this.baseDelayMs = options?.baseDelayMs ?? DEFAULT_RETRY_OPTIONS.baseDelayMs;
  }

  // ==========================================================================
  // Core HTTP Methods
  // ==========================================================================

  private async sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private async request<T>(
    method: "GET" | "POST",
    path: string,
    body?: unknown
  ): Promise<ApiResult<T>> {
    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
      try {
        const response = await fetch(`${this.baseUrl}${path}`, {
          method,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${this.apiKey}`,
          },
          body: body ? JSON.stringify(body) : undefined,
        });

        // Handle rate limiting
        if (response.status === 429) {
          const retryAfter = response.headers.get("Retry-After");
          const waitTime = retryAfter
            ? parseInt(retryAfter, 10) * 1000
            : this.baseDelayMs * Math.pow(2, attempt);

          if (attempt < this.maxRetries) {
            await this.sleep(waitTime);
            continue;
          }
        }

        if (!response.ok) {
          const errorText = await response.text();
          return {
            data: null,
            error: `API error ${response.status}: ${errorText}`,
          };
        }

        const data = await response.json();

        // Handle Helicone's Result<T, string> format
        if (data && typeof data === "object" && "data" in data) {
          return data as ApiResult<T>;
        }

        return { data: data as T, error: null };
      } catch (error) {
        lastError = error as Error;

        if (attempt < this.maxRetries) {
          const waitTime = this.baseDelayMs * Math.pow(2, attempt);
          await this.sleep(waitTime);
        }
      }
    }

    return {
      data: null,
      error: `Request failed after ${this.maxRetries + 1} attempts: ${lastError?.message}`,
    };
  }

  // ==========================================================================
  // Request Endpoints
  // ==========================================================================

  /**
   * Query requests with filters and pagination
   */
  async queryRequests(
    params: RequestQueryParams
  ): Promise<ApiResult<HeliconeRequest[]>> {
    const body = {
      filter: params.filter ?? "all",
      offset: params.offset ?? 0,
      limit: Math.min(params.limit ?? 25, 1000), // Enforce max limit
      sort: params.sort ?? { created_at: "desc" },
      isCached: params.isCached ?? false,
      includeInputs: params.includeInputs ?? false,
      isPartOfExperiment: params.isPartOfExperiment ?? false,
      isScored: params.isScored ?? false,
    };

    return this.request<HeliconeRequest[]>(
      "POST",
      "/v1/request/query-clickhouse",
      body
    );
  }

  /**
   * Get count of requests matching filter
   */
  async countRequests(filter: FilterNode = "all"): Promise<ApiResult<number>> {
    const body = {
      filter,
      isCached: false,
      includeInputs: false,
      isScored: false,
      isPartOfExperiment: false,
    };

    return this.request<number>("POST", "/v1/request/count/query", body);
  }

  /**
   * Get a single request by ID
   */
  async getRequest(
    requestId: string,
    includeBody = false
  ): Promise<ApiResult<HeliconeRequest>> {
    const path = includeBody
      ? `/v1/request/${requestId}?includeBody=true`
      : `/v1/request/${requestId}`;

    return this.request<HeliconeRequest>("GET", path);
  }

  /**
   * Fetch signed body from S3 URL
   */
  async fetchSignedBody(
    url: string
  ): Promise<{ request?: unknown; response?: unknown }> {
    try {
      const response = await fetch(url);
      if (!response.ok) {
        return {};
      }
      return await response.json();
    } catch {
      return {};
    }
  }

  // ==========================================================================
  // Session Endpoints
  // ==========================================================================

  /**
   * Query sessions with filters and pagination
   */
  async querySessions(
    params: SessionQueryParams
  ): Promise<ApiResult<Session[]>> {
    const body = {
      search: params.search ?? "",
      timeFilter: params.timeFilter,
      nameEquals: params.nameEquals,
      timezoneDifference: params.timezoneDifference,
      filter: params.filter ?? "all",
      offset: params.offset ?? 0,
      limit: params.limit ?? 50,
    };

    return this.request<Session[]>("POST", "/v1/session/query", body);
  }

  /**
   * Get session count and aggregate metrics
   */
  async getSessionsCount(params: SessionQueryParams): Promise<
    ApiResult<{
      count: number;
      total_cost: number;
      avg_cost: number;
      avg_latency: number;
      avg_requests: number;
    }>
  > {
    const body = {
      search: params.search ?? "",
      timeFilter: params.timeFilter,
      nameEquals: params.nameEquals,
      timezoneDifference: params.timezoneDifference,
      filter: params.filter ?? "all",
    };

    return this.request("POST", "/v1/session/count", body);
  }

  // ==========================================================================
  // Metrics Endpoints
  // ==========================================================================

  /**
   * Get dashboard metrics
   */
  async getDashboardScores(params: {
    timeFilter: { start: string; end: string };
    dbIncrement: "hour" | "day" | "week" | "month";
    timeZoneDifference: number;
  }): Promise<
    ApiResult<
      Array<{
        score_key: string;
        score_sum: number;
        created_at_trunc: string;
      }>
    >
  > {
    const body = {
      userFilter: "all",
      timeFilter: params.timeFilter,
      dbIncrement: params.dbIncrement,
      timeZoneDifference: params.timeZoneDifference,
    };

    return this.request("POST", "/v1/dashboard/scores/query", body);
  }

  // ==========================================================================
  // Auth/Status Check
  // ==========================================================================

  /**
   * Verify API key is valid by making a simple request
   */
  async verifyAuth(): Promise<ApiResult<{ valid: boolean; message?: string }>> {
    // Try to fetch a single request to verify auth works
    const result = await this.queryRequests({ limit: 1 });

    if (result.error) {
      if (result.error.includes("401")) {
        return { data: null, error: "Invalid API key" };
      }
      return { data: null, error: result.error };
    }

    return { data: { valid: true }, error: null };
  }
}

// ============================================================================
// Filter Builder Utilities
// ============================================================================

/**
 * Build a filter node from simple key-value conditions
 */
export function buildFilter(conditions: {
  model?: string;
  status?: number;
  userId?: string;
  provider?: string;
  startDate?: Date;
  endDate?: Date;
  minCost?: number;
  maxCost?: number;
  minLatency?: number;
  maxLatency?: number;
  properties?: Record<string, string>;
  cached?: boolean;
}): FilterNode {
  const filters: FilterNode[] = [];

  // Model filter
  if (conditions.model) {
    filters.push({
      request_response_rmt: {
        model: { equals: conditions.model },
      },
    });
  }

  // Status filter
  if (conditions.status !== undefined) {
    filters.push({
      request_response_rmt: {
        status: { equals: conditions.status },
      },
    });
  }

  // User ID filter
  if (conditions.userId) {
    filters.push({
      request_response_rmt: {
        user_id: { equals: conditions.userId },
      },
    });
  }

  // Provider filter
  if (conditions.provider) {
    filters.push({
      request_response_rmt: {
        provider: { equals: conditions.provider },
      },
    });
  }

  // Date range filters
  if (conditions.startDate) {
    filters.push({
      request_response_rmt: {
        request_created_at: { gte: conditions.startDate.toISOString() },
      },
    });
  }

  if (conditions.endDate) {
    filters.push({
      request_response_rmt: {
        request_created_at: { lte: conditions.endDate.toISOString() },
      },
    });
  }

  // Cost filters
  if (conditions.minCost !== undefined) {
    filters.push({
      request_response_rmt: {
        cost: { gte: conditions.minCost },
      },
    });
  }

  if (conditions.maxCost !== undefined) {
    filters.push({
      request_response_rmt: {
        cost: { lte: conditions.maxCost },
      },
    });
  }

  // Latency filters
  if (conditions.minLatency !== undefined) {
    filters.push({
      request_response_rmt: {
        latency: { gte: conditions.minLatency },
      },
    });
  }

  if (conditions.maxLatency !== undefined) {
    filters.push({
      request_response_rmt: {
        latency: { lte: conditions.maxLatency },
      },
    });
  }

  // Property filters
  if (conditions.properties) {
    for (const [key, value] of Object.entries(conditions.properties)) {
      filters.push({
        request_response_rmt: {
          properties: { [key]: { equals: value } },
        },
      });
    }
  }

  // Cache filter
  if (conditions.cached !== undefined) {
    filters.push({
      request_response_rmt: {
        cache_enabled: { equals: conditions.cached },
      },
    });
  }

  // Combine filters with AND
  if (filters.length === 0) {
    return "all";
  }

  if (filters.length === 1) {
    return filters[0];
  }

  // Build AND tree
  let result: FilterNode = filters[0];
  for (let i = 1; i < filters.length; i++) {
    result = {
      left: result,
      operator: "and",
      right: filters[i],
    };
  }

  return result;
}

/**
 * Parse time range string (e.g., "7d", "24h", "30d") to Date
 */
export function parseTimeRange(range: string): Date {
  const now = new Date();
  const match = range.match(/^(\d+)([hdwm])$/);

  if (!match) {
    throw new Error(
      `Invalid time range format: ${range}. Use formats like "24h", "7d", "4w", "1m"`
    );
  }

  const value = parseInt(match[1], 10);
  const unit = match[2];

  switch (unit) {
    case "h":
      return new Date(now.getTime() - value * 60 * 60 * 1000);
    case "d":
      return new Date(now.getTime() - value * 24 * 60 * 60 * 1000);
    case "w":
      return new Date(now.getTime() - value * 7 * 24 * 60 * 60 * 1000);
    case "m":
      return new Date(now.getTime() - value * 30 * 24 * 60 * 60 * 1000);
    default:
      throw new Error(`Unknown time unit: ${unit}`);
  }
}

/**
 * Parse date string that can be either ISO date or relative time range
 */
export function parseDate(value: string): Date {
  // Try as relative time range first
  if (/^\d+[hdwm]$/.test(value)) {
    return parseTimeRange(value);
  }

  // Try as ISO date
  const date = new Date(value);
  if (isNaN(date.getTime())) {
    throw new Error(
      `Invalid date format: ${value}. Use ISO format (YYYY-MM-DD) or relative (7d, 24h)`
    );
  }

  return date;
}
