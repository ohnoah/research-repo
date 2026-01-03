/**
 * Session commands for querying Helicone session/trace data
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import * as fs from "fs";
import { getAuthContext } from "../lib/config.js";
import { HeliconeClient, parseDate } from "../lib/client.js";
import {
  formatSessions,
  SESSION_DEFAULT_FIELDS,
} from "../lib/output.js";
import type { OutputFormat, ListOptions } from "../lib/types.js";

// Session-specific available fields
const SESSION_AVAILABLE_FIELDS = [
  "session_id",
  "name",
  "requests",
  "tokens",
  "prompt_tokens",
  "completion_tokens",
  "cost",
  "avg_latency_ms",
  "created_at",
  "last_request_at",
];

export function createSessionsCommand(): Command {
  const sessions = new Command("sessions").description(
    "Query and export session/trace data"
  );

  // ============================================================================
  // helicone sessions list
  // ============================================================================
  sessions
    .command("list")
    .description("List sessions with optional filters")
    .option("-n, --limit <number>", "Maximum number of results", "25")
    .option("--offset <number>", "Offset for pagination", "0")
    .option(
      "-f, --format <format>",
      "Output format: table, json, jsonl, csv",
      "table"
    )
    .option(
      "--fields <fields>",
      `Comma-separated fields. Available: ${SESSION_AVAILABLE_FIELDS.join(", ")}`
    )
    .option(
      "--since <date>",
      "Start date (ISO format or relative like 7d, 24h)",
      "7d"
    )
    .option("--until <date>", "End date (ISO format or relative)")
    .option("--search <query>", "Search sessions by name")
    .option("--name <name>", "Filter by exact session name")
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)")
    .option("-q, --quiet", "Suppress non-essential output")
    .action(async (options: ListOptions & { search?: string; name?: string }) => {
      try {
        const auth = getAuthContext(options.apiKey, options.region);
        const client = new HeliconeClient(auth);

        // Parse time range
        const startDate = options.since
          ? parseDate(options.since)
          : parseDate("7d");
        const endDate = options.until ? parseDate(options.until) : new Date();

        const limit = parseInt(options.limit as string, 10);
        const offset = parseInt(options.offset as string, 10);

        // Get timezone offset in minutes
        const timezoneDifference = new Date().getTimezoneOffset();

        const spinner = options.quiet
          ? null
          : ora("Fetching sessions...").start();

        const result = await client.querySessions({
          search: options.search || "",
          timeFilter: {
            startTimeUnixMs: startDate.getTime(),
            endTimeUnixMs: endDate.getTime(),
          },
          nameEquals: options.name,
          timezoneDifference,
          filter: "all",
          limit,
          offset,
        });

        if (result.error) {
          spinner?.fail(chalk.red(`Error: ${result.error}`));
          process.exit(1);
        }

        spinner?.stop();

        const sessions = result.data || [];

        if (sessions.length === 0) {
          console.log(chalk.yellow("No sessions found matching the filters"));
          return;
        }

        // Parse fields
        const fields = options.fields
          ? options.fields.split(",").map((f) => f.trim())
          : SESSION_DEFAULT_FIELDS;

        // Format and output
        const format = (options.format || "table") as OutputFormat;
        const output = formatSessions(sessions, format, fields);
        console.log(output);

        // Show summary for table format
        if (format === "table" && !options.quiet) {
          // Get count
          const countResult = await client.getSessionsCount({
            search: options.search || "",
            timeFilter: {
              startTimeUnixMs: startDate.getTime(),
              endTimeUnixMs: endDate.getTime(),
            },
            nameEquals: options.name,
            timezoneDifference,
            filter: "all",
          });

          if (countResult.data) {
            const { count, total_cost, avg_latency } = countResult.data;
            console.log(chalk.dim(`\nShowing ${sessions.length} of ${count} sessions`));
            console.log(
              chalk.dim(
                `Total cost: $${total_cost.toFixed(4)} | Avg latency: ${avg_latency.toFixed(0)}ms`
              )
            );
          }
        }
      } catch (error) {
        console.error(chalk.red(`Error: ${(error as Error).message}`));
        process.exit(1);
      }
    });

  // ============================================================================
  // helicone sessions get
  // ============================================================================
  sessions
    .command("get <sessionId>")
    .description("Get details for a specific session including its requests")
    .option(
      "-f, --format <format>",
      "Output format: table, json",
      "json"
    )
    .option("--include-requests", "Include all requests in the session")
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)")
    .action(async (sessionId: string, options) => {
      try {
        const auth = getAuthContext(options.apiKey, options.region);
        const client = new HeliconeClient(auth);

        const spinner = ora("Fetching session...").start();

        // Query sessions with this ID
        const timezoneDifference = new Date().getTimezoneOffset();
        const result = await client.querySessions({
          search: "",
          timeFilter: {
            // Look back 150 days (max supported)
            startTimeUnixMs: Date.now() - 150 * 24 * 60 * 60 * 1000,
            endTimeUnixMs: Date.now(),
          },
          timezoneDifference,
          filter: {
            sessions_request_response_rmt: {
              properties: {
                "Helicone-Session-Id": { equals: sessionId },
              },
            },
          },
          limit: 1,
        });

        if (result.error) {
          spinner.fail(chalk.red(`Error: ${result.error}`));
          process.exit(1);
        }

        if (!result.data || result.data.length === 0) {
          spinner.fail(chalk.yellow("Session not found"));
          process.exit(1);
        }

        const session = result.data[0];

        // If including requests, fetch them
        let requests = null;
        if (options.includeRequests) {
          spinner.text = "Fetching session requests...";

          const reqResult = await client.queryRequests({
            filter: {
              request_response_rmt: {
                properties: {
                  "Helicone-Session-Id": { equals: sessionId },
                },
              },
            },
            limit: 100,
            sort: { created_at: "asc" },
          });

          if (reqResult.data) {
            requests = reqResult.data;
          }
        }

        spinner.stop();

        // Output
        if (options.format === "json") {
          const output = {
            session,
            requests: requests || undefined,
          };
          console.log(JSON.stringify(output, null, 2));
        } else {
          // Table format - show session info
          console.log(chalk.bold("\nSession Details:\n"));
          console.log(`  Session ID:   ${chalk.cyan(session.session_id)}`);
          console.log(`  Name:         ${session.session_name || chalk.dim("(unnamed)")}`);
          console.log(`  Requests:     ${session.total_requests}`);
          console.log(`  Total Tokens: ${session.total_tokens.toLocaleString()}`);
          console.log(`  Total Cost:   $${session.total_cost.toFixed(4)}`);
          console.log(`  Avg Latency:  ${session.avg_latency.toFixed(0)}ms`);
          console.log(`  Created:      ${new Date(session.created_at).toLocaleString()}`);
          console.log(
            `  Last Request: ${new Date(session.latest_request_created_at).toLocaleString()}`
          );

          if (requests) {
            console.log(chalk.bold(`\nRequests (${requests.length}):\n`));
            for (const req of requests) {
              const status = req.response_status;
              const statusColor =
                status >= 200 && status < 300
                  ? chalk.green
                  : status >= 400
                    ? chalk.red
                    : chalk.yellow;

              console.log(
                `  ${statusColor(status)} ${req.model || "unknown"} ` +
                  `${chalk.dim(`${req.delay_ms}ms`)} ` +
                  `${chalk.dim(new Date(req.request_created_at).toLocaleTimeString())}`
              );
            }
          }
        }
      } catch (error) {
        console.error(chalk.red(`Error: ${(error as Error).message}`));
        process.exit(1);
      }
    });

  // ============================================================================
  // helicone sessions export
  // ============================================================================
  sessions
    .command("export")
    .description("Export sessions to a file")
    .option("-o, --output <path>", "Output file path", "sessions-export.jsonl")
    .option("-n, --limit <number>", "Maximum number of sessions")
    .option(
      "-f, --format <format>",
      "Output format: json, jsonl, csv",
      "jsonl"
    )
    .option(
      "--since <date>",
      "Start date (ISO format or relative)",
      "30d"
    )
    .option("--until <date>", "End date (ISO format or relative)")
    .option("--search <query>", "Search sessions by name")
    .option("--include-requests", "Include requests for each session")
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)")
    .action(async (options) => {
      try {
        const auth = getAuthContext(options.apiKey, options.region);
        const client = new HeliconeClient(auth);

        const startDate = options.since
          ? parseDate(options.since)
          : parseDate("30d");
        const endDate = options.until ? parseDate(options.until) : new Date();
        const timezoneDifference = new Date().getTimezoneOffset();

        const outputPath = options.output || "sessions-export.jsonl";
        const format = (options.format || "jsonl") as OutputFormat;
        const maxSessions = options.limit ? parseInt(options.limit, 10) : undefined;

        // Get count first
        console.log(chalk.dim("Counting sessions..."));
        const countResult = await client.getSessionsCount({
          search: options.search || "",
          timeFilter: {
            startTimeUnixMs: startDate.getTime(),
            endTimeUnixMs: endDate.getTime(),
          },
          timezoneDifference,
          filter: "all",
        });

        const totalCount = countResult.data?.count || 0;

        if (totalCount === 0) {
          console.log(chalk.yellow("No sessions found matching the filters"));
          return;
        }

        const sessionsToExport = maxSessions
          ? Math.min(totalCount, maxSessions)
          : totalCount;

        console.log(
          chalk.dim(
            `Found ${totalCount} sessions. Exporting ${sessionsToExport}...`
          )
        );

        // Open output file
        const stream = fs.createWriteStream(outputPath);

        if (format === "json") {
          stream.write("[\n");
        } else if (format === "csv") {
          stream.write(SESSION_DEFAULT_FIELDS.join(",") + "\n");
        }

        let offset = 0;
        let exported = 0;
        let isFirst = true;
        const batchSize = 50;
        const startTime = Date.now();

        while (exported < sessionsToExport) {
          const limit = Math.min(batchSize, sessionsToExport - exported);

          const result = await client.querySessions({
            search: options.search || "",
            timeFilter: {
              startTimeUnixMs: startDate.getTime(),
              endTimeUnixMs: endDate.getTime(),
            },
            timezoneDifference,
            filter: "all",
            limit,
            offset,
          });

          if (result.error) {
            console.error(chalk.red(`\nError: ${result.error}`));
            stream.close();
            process.exit(1);
          }

          const sessions = result.data || [];

          if (sessions.length === 0) break;

          // Optionally fetch requests for each session
          for (const session of sessions) {
            let sessionData: Record<string, unknown> = { ...session };

            if (options.includeRequests) {
              const reqResult = await client.queryRequests({
                filter: {
                  request_response_rmt: {
                    properties: {
                      "Helicone-Session-Id": { equals: session.session_id },
                    },
                  },
                },
                limit: 100,
                sort: { created_at: "asc" },
              });

              if (reqResult.data) {
                sessionData.requests = reqResult.data;
              }
            }

            // Write to file
            if (format === "jsonl") {
              stream.write(JSON.stringify(sessionData) + "\n");
            } else if (format === "json") {
              if (!isFirst) stream.write(",\n");
              stream.write(JSON.stringify(sessionData, null, 2));
              isFirst = false;
            } else if (format === "csv") {
              const row = SESSION_DEFAULT_FIELDS.map((field) => {
                const value = (session as Record<string, unknown>)[field];
                if (value === null || value === undefined) return "";
                const str = String(value);
                if (str.includes(",") || str.includes('"')) {
                  return `"${str.replace(/"/g, '""')}"`;
                }
                return str;
              }).join(",");
              stream.write(row + "\n");
            }
          }

          exported += sessions.length;
          offset += batchSize;

          // Progress
          const elapsed = (Date.now() - startTime) / 1000;
          const rate = exported / elapsed;
          process.stdout.write(
            `\r${chalk.dim(
              `Exported ${exported}/${sessionsToExport} sessions ` +
                `(${((exported / sessionsToExport) * 100).toFixed(1)}%)`
            )}`
          );

          await new Promise((resolve) => setTimeout(resolve, 100));
        }

        if (format === "json") {
          stream.write("\n]\n");
        }
        stream.close();

        const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
        console.log(
          `\n${chalk.green("✓")} Exported ${exported} sessions to ${outputPath} in ${totalTime}s`
        );
      } catch (error) {
        console.error(chalk.red(`Error: ${(error as Error).message}`));
        process.exit(1);
      }
    });

  // ============================================================================
  // helicone sessions fields
  // ============================================================================
  sessions
    .command("fields")
    .description("List available fields for sessions")
    .action(() => {
      console.log(chalk.bold("\nAvailable Session Fields:\n"));

      const descriptions: Record<string, string> = {
        session_id: "Unique session identifier",
        name: "Session name",
        requests: "Total request count in session",
        tokens: "Total token count",
        prompt_tokens: "Input token count",
        completion_tokens: "Output token count",
        cost: "Total cost in USD",
        avg_latency_ms: "Average request latency",
        created_at: "Session start time",
        last_request_at: "Most recent request time",
      };

      for (const field of SESSION_AVAILABLE_FIELDS) {
        const desc = descriptions[field] || "";
        const isDefault = SESSION_DEFAULT_FIELDS.includes(field);
        console.log(
          `  ${chalk.cyan(field.padEnd(20))} ${desc}${isDefault ? chalk.dim(" (default)") : ""}`
        );
      }
    });

  return sessions;
}
