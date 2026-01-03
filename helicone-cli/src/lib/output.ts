/**
 * Output formatters for different display modes
 */

import Table from "cli-table3";
import chalk from "chalk";
import type {
  HeliconeRequest,
  Session,
  OutputFormat,
  RequestSummary,
  SessionSummary,
} from "./types.js";

// ============================================================================
// Field Definitions
// ============================================================================

// Default fields for request table display
export const REQUEST_DEFAULT_FIELDS = [
  "request_id",
  "created_at",
  "model",
  "status",
  "latency_ms",
  "tokens",
  "cost",
];

// All available request fields
export const REQUEST_AVAILABLE_FIELDS = [
  "request_id",
  "created_at",
  "model",
  "provider",
  "status",
  "latency_ms",
  "ttft_ms",
  "tokens",
  "prompt_tokens",
  "completion_tokens",
  "cost",
  "user_id",
  "country",
  "cached",
  "path",
];

// Default fields for session table display
export const SESSION_DEFAULT_FIELDS = [
  "session_id",
  "name",
  "requests",
  "tokens",
  "cost",
  "avg_latency_ms",
  "last_request_at",
];

// ============================================================================
// Request Formatters
// ============================================================================

/**
 * Convert HeliconeRequest to summary for display
 */
export function requestToSummary(req: HeliconeRequest): RequestSummary {
  return {
    request_id: req.request_id,
    created_at: req.request_created_at,
    model: req.model || req.request_model || "unknown",
    provider: req.provider,
    status: req.response_status,
    latency_ms: req.delay_ms,
    tokens: req.total_tokens,
    cost: req.cost,
    user_id: req.request_user_id,
  };
}

/**
 * Get value for a specific field from request
 */
function getRequestFieldValue(
  req: HeliconeRequest,
  field: string
): string | number | boolean | null {
  switch (field) {
    case "request_id":
      return req.request_id;
    case "created_at":
      return req.request_created_at;
    case "model":
      return req.model || req.request_model || "unknown";
    case "provider":
      return req.provider;
    case "status":
      return req.response_status;
    case "latency_ms":
      return req.delay_ms;
    case "ttft_ms":
      return req.time_to_first_token;
    case "tokens":
      return req.total_tokens;
    case "prompt_tokens":
      return req.prompt_tokens;
    case "completion_tokens":
      return req.completion_tokens;
    case "cost":
      return req.cost;
    case "user_id":
      return req.request_user_id;
    case "country":
      return req.country_code;
    case "cached":
      return req.cache_enabled;
    case "path":
      return req.request_path;
    default:
      return null;
  }
}

/**
 * Format a value for table display
 */
function formatValue(value: unknown, field: string): string {
  if (value === null || value === undefined) {
    return chalk.dim("-");
  }

  switch (field) {
    case "request_id":
    case "session_id":
      // Show enough of UUID to be useful for copy/paste
      // UUIDs are 36 chars, show first 15 to include most of the unique part
      const id = String(value);
      return id.length > 15 ? id.substring(0, 15) + "..." : id;

    case "created_at":
      // Format date nicely
      const date = new Date(value as string);
      return date.toLocaleString();

    case "status":
      const status = value as number;
      if (status >= 200 && status < 300) {
        return chalk.green(String(status));
      } else if (status >= 400) {
        return chalk.red(String(status));
      }
      return chalk.yellow(String(status));

    case "latency_ms":
    case "ttft_ms":
    case "avg_latency_ms":
      const ms = value as number;
      if (ms > 5000) {
        return chalk.red(`${ms.toFixed(0)}ms`);
      } else if (ms > 2000) {
        return chalk.yellow(`${ms.toFixed(0)}ms`);
      }
      return `${ms.toFixed(0)}ms`;

    case "cost":
      const cost = value as number;
      if (cost === 0) {
        return chalk.dim("$0.00");
      }
      return `$${cost.toFixed(4)}`;

    case "tokens":
    case "prompt_tokens":
    case "completion_tokens":
      return (value as number).toLocaleString();

    case "cached":
      return value ? chalk.cyan("yes") : chalk.dim("no");

    default:
      return String(value);
  }
}

/**
 * Format requests as table
 */
export function formatRequestsTable(
  requests: HeliconeRequest[],
  fields: string[] = REQUEST_DEFAULT_FIELDS
): string {
  const table = new Table({
    head: fields.map((f) => chalk.bold(f)),
    style: { head: [], border: [] },
  });

  for (const req of requests) {
    const row = fields.map((field) => {
      const value = getRequestFieldValue(req, field);
      return formatValue(value, field);
    });
    table.push(row);
  }

  return table.toString();
}

/**
 * Format requests as JSON
 */
export function formatRequestsJson(
  requests: HeliconeRequest[],
  fields?: string[]
): string {
  if (fields && fields.length > 0) {
    const filtered = requests.map((req) => {
      const obj: Record<string, unknown> = {};
      for (const field of fields) {
        obj[field] = getRequestFieldValue(req, field);
      }
      return obj;
    });
    return JSON.stringify(filtered, null, 2);
  }
  return JSON.stringify(requests, null, 2);
}

/**
 * Format requests as JSONL
 */
export function formatRequestsJsonl(
  requests: HeliconeRequest[],
  fields?: string[]
): string {
  if (fields && fields.length > 0) {
    return requests
      .map((req) => {
        const obj: Record<string, unknown> = {};
        for (const field of fields) {
          obj[field] = getRequestFieldValue(req, field);
        }
        return JSON.stringify(obj);
      })
      .join("\n");
  }
  return requests.map((req) => JSON.stringify(req)).join("\n");
}

/**
 * Format requests as CSV
 */
export function formatRequestsCsv(
  requests: HeliconeRequest[],
  fields: string[] = REQUEST_DEFAULT_FIELDS
): string {
  const header = fields.join(",");
  const rows = requests.map((req) => {
    return fields
      .map((field) => {
        const value = getRequestFieldValue(req, field);
        if (value === null || value === undefined) {
          return "";
        }
        const str = String(value);
        // Escape quotes and wrap in quotes if contains comma
        if (str.includes(",") || str.includes('"') || str.includes("\n")) {
          return `"${str.replace(/"/g, '""')}"`;
        }
        return str;
      })
      .join(",");
  });

  return [header, ...rows].join("\n");
}

/**
 * Format requests in specified format
 */
export function formatRequests(
  requests: HeliconeRequest[],
  format: OutputFormat,
  fields?: string[]
): string {
  const fieldList = fields && fields.length > 0 ? fields : undefined;

  switch (format) {
    case "table":
      return formatRequestsTable(requests, fieldList || REQUEST_DEFAULT_FIELDS);
    case "json":
      return formatRequestsJson(requests, fieldList);
    case "jsonl":
      return formatRequestsJsonl(requests, fieldList);
    case "csv":
      return formatRequestsCsv(requests, fieldList || REQUEST_DEFAULT_FIELDS);
    default:
      return formatRequestsTable(requests);
  }
}

// ============================================================================
// Session Formatters
// ============================================================================

/**
 * Convert Session to summary for display
 */
export function sessionToSummary(session: Session): SessionSummary {
  return {
    session_id: session.session_id,
    name: session.session_name,
    requests: session.total_requests,
    tokens: session.total_tokens,
    cost: session.total_cost,
    avg_latency_ms: session.avg_latency,
    created_at: session.created_at,
    last_request_at: session.latest_request_created_at,
  };
}

/**
 * Get value for a specific field from session
 */
function getSessionFieldValue(
  session: Session,
  field: string
): string | number | null {
  switch (field) {
    case "session_id":
      return session.session_id;
    case "name":
      return session.session_name;
    case "requests":
      return session.total_requests;
    case "tokens":
      return session.total_tokens;
    case "prompt_tokens":
      return session.prompt_tokens;
    case "completion_tokens":
      return session.completion_tokens;
    case "cost":
      return session.total_cost;
    case "avg_latency_ms":
      return session.avg_latency;
    case "created_at":
      return session.created_at;
    case "last_request_at":
      return session.latest_request_created_at;
    default:
      return null;
  }
}

/**
 * Format sessions as table
 */
export function formatSessionsTable(
  sessions: Session[],
  fields: string[] = SESSION_DEFAULT_FIELDS
): string {
  const table = new Table({
    head: fields.map((f) => chalk.bold(f)),
    style: { head: [], border: [] },
  });

  for (const session of sessions) {
    const row = fields.map((field) => {
      const value = getSessionFieldValue(session, field);
      return formatValue(value, field);
    });
    table.push(row);
  }

  return table.toString();
}

/**
 * Format sessions as JSON
 */
export function formatSessionsJson(
  sessions: Session[],
  fields?: string[]
): string {
  if (fields && fields.length > 0) {
    const filtered = sessions.map((session) => {
      const obj: Record<string, unknown> = {};
      for (const field of fields) {
        obj[field] = getSessionFieldValue(session, field);
      }
      return obj;
    });
    return JSON.stringify(filtered, null, 2);
  }
  return JSON.stringify(sessions, null, 2);
}

/**
 * Format sessions in specified format
 */
export function formatSessions(
  sessions: Session[],
  format: OutputFormat,
  fields?: string[]
): string {
  const fieldList = fields && fields.length > 0 ? fields : undefined;

  switch (format) {
    case "table":
      return formatSessionsTable(sessions, fieldList || SESSION_DEFAULT_FIELDS);
    case "json":
      return formatSessionsJson(sessions, fieldList);
    case "jsonl":
      return sessions.map((s) => JSON.stringify(s)).join("\n");
    case "csv":
      // Similar to requests CSV
      const csvFields = fieldList || SESSION_DEFAULT_FIELDS;
      const header = csvFields.join(",");
      const rows = sessions.map((session) => {
        return csvFields
          .map((field) => {
            const value = getSessionFieldValue(session, field);
            if (value === null || value === undefined) return "";
            const str = String(value);
            if (str.includes(",") || str.includes('"')) {
              return `"${str.replace(/"/g, '""')}"`;
            }
            return str;
          })
          .join(",");
      });
      return [header, ...rows].join("\n");
    default:
      return formatSessionsTable(sessions);
  }
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * Parse comma-separated field list
 */
export function parseFields(fieldsStr: string): string[] {
  return fieldsStr.split(",").map((f) => f.trim());
}

/**
 * Print summary line after output
 */
export function printSummary(count: number, totalCount?: number): void {
  if (totalCount !== undefined && totalCount > count) {
    console.log(
      chalk.dim(`\nShowing ${count} of ${totalCount.toLocaleString()} results`)
    );
  } else {
    console.log(chalk.dim(`\n${count} results`));
  }
}
