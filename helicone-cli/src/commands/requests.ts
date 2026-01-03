/**
 * Request commands for querying and exporting Helicone request data
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import * as fs from "fs";
import { getAuthContext } from "../lib/config.js";
import { HeliconeClient, buildFilter, parseDate } from "../lib/client.js";
import {
  formatRequests,
  parseFields,
  printSummary,
  REQUEST_AVAILABLE_FIELDS,
  REQUEST_DEFAULT_FIELDS,
} from "../lib/output.js";
import type { OutputFormat, ListOptions, GetOptions, ExportOptions } from "../lib/types.js";

export function createRequestsCommand(): Command {
  const requests = new Command("requests").description(
    "Query and export request data"
  );

  // ============================================================================
  // helicone requests list
  // ============================================================================
  requests
    .command("list")
    .description("List requests with optional filters")
    .option("-n, --limit <number>", "Maximum number of results", "25")
    .option("--offset <number>", "Offset for pagination", "0")
    .option(
      "-f, --format <format>",
      "Output format: table, json, jsonl, csv",
      "table"
    )
    .option(
      "--fields <fields>",
      `Comma-separated fields to display. Available: ${REQUEST_AVAILABLE_FIELDS.join(", ")}`
    )
    .option(
      "--since <date>",
      "Start date (ISO format or relative like 7d, 24h)",
      "7d"
    )
    .option("--until <date>", "End date (ISO format or relative)")
    .option("--model <model>", "Filter by model name")
    .option("--status <status>", "Filter by HTTP status code")
    .option("--user-id <userId>", "Filter by user ID")
    .option(
      "-p, --property <key=value>",
      "Filter by property (can be used multiple times)",
      (value: string, previous: string[]) => {
        previous.push(value);
        return previous;
      },
      [] as string[]
    )
    .option("--min-cost <cost>", "Minimum cost in USD")
    .option("--max-cost <cost>", "Maximum cost in USD")
    .option("--min-latency <ms>", "Minimum latency in milliseconds")
    .option("--max-latency <ms>", "Maximum latency in milliseconds")
    .option("--cached", "Only show cached requests")
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)")
    .option("-q, --quiet", "Suppress non-essential output")
    .action(async (options: ListOptions & { cached?: boolean; property: string[] }) => {
      try {
        const auth = getAuthContext(options.apiKey, options.region);
        const client = new HeliconeClient(auth);

        // Parse filters
        const startDate = options.since ? parseDate(options.since) : undefined;
        const endDate = options.until ? parseDate(options.until) : undefined;

        // Parse property filters
        const properties: Record<string, string> = {};
        for (const prop of options.property || []) {
          const [key, value] = prop.split("=");
          if (key && value) {
            properties[key] = value;
          }
        }

        const filter = buildFilter({
          model: options.model,
          status: options.status ? parseInt(options.status, 10) : undefined,
          userId: options.userId,
          startDate,
          endDate,
          minCost: options.minCost ? parseFloat(options.minCost) : undefined,
          maxCost: options.maxCost ? parseFloat(options.maxCost) : undefined,
          minLatency: options.minLatency
            ? parseInt(options.minLatency, 10)
            : undefined,
          maxLatency: options.maxLatency
            ? parseInt(options.maxLatency, 10)
            : undefined,
          properties: Object.keys(properties).length > 0 ? properties : undefined,
          cached: options.cached,
        });

        const limit = parseInt(options.limit as string, 10);
        const offset = parseInt(options.offset as string, 10);

        // Show spinner for non-quiet mode
        const spinner = options.quiet ? null : ora("Fetching requests...").start();

        // Fetch requests
        const result = await client.queryRequests({
          filter,
          limit,
          offset,
          sort: { created_at: "desc" },
        });

        if (result.error) {
          spinner?.fail(chalk.red(`Error: ${result.error}`));
          process.exit(1);
        }

        spinner?.stop();

        const requests = result.data || [];

        if (requests.length === 0) {
          console.log(chalk.yellow("No requests found matching the filters"));
          return;
        }

        // Parse fields
        const fields = options.fields
          ? parseFields(options.fields)
          : REQUEST_DEFAULT_FIELDS;

        // Format and output
        const format = (options.format || "table") as OutputFormat;
        const output = formatRequests(requests, format, fields);
        console.log(output);

        // Show summary for table format
        if (format === "table" && !options.quiet) {
          // Get total count if we hit the limit
          if (requests.length === limit) {
            const countResult = await client.countRequests(filter);
            printSummary(requests.length, countResult.data ?? undefined);
          } else {
            printSummary(requests.length);
          }
        }
      } catch (error) {
        console.error(chalk.red(`Error: ${(error as Error).message}`));
        process.exit(1);
      }
    });

  // ============================================================================
  // helicone requests get
  // ============================================================================
  requests
    .command("get <requestId>")
    .description("Get a single request by ID")
    .option(
      "-f, --format <format>",
      "Output format: table, json, jsonl",
      "json"
    )
    .option("--include-body", "Include full request/response bodies")
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)")
    .action(async (requestId: string, options: GetOptions) => {
      try {
        const auth = getAuthContext(options.apiKey, options.region);
        const client = new HeliconeClient(auth);

        const spinner = ora("Fetching request...").start();

        const result = await client.getRequest(requestId, options.includeBody);

        if (result.error) {
          spinner.fail(chalk.red(`Error: ${result.error}`));
          process.exit(1);
        }

        spinner.stop();

        if (!result.data) {
          console.log(chalk.yellow("Request not found"));
          return;
        }

        const format = (options.format || "json") as OutputFormat;
        const output = formatRequests([result.data], format);
        console.log(output);
      } catch (error) {
        console.error(chalk.red(`Error: ${(error as Error).message}`));
        process.exit(1);
      }
    });

  // ============================================================================
  // helicone requests export
  // ============================================================================
  requests
    .command("export")
    .description("Export requests to a file with pagination handling")
    .option("-o, --output <path>", "Output file path", "requests-export.jsonl")
    .option("-n, --limit <number>", "Maximum number of records to export")
    .option(
      "-f, --format <format>",
      "Output format: json, jsonl, csv",
      "jsonl"
    )
    .option(
      "--fields <fields>",
      "Comma-separated fields to include in export"
    )
    .option("--include-body", "Include full request/response bodies")
    .option("--batch-size <size>", "Records per API request", "1000")
    .option(
      "--since <date>",
      "Start date (ISO format or relative like 7d, 24h)",
      "30d"
    )
    .option("--until <date>", "End date (ISO format or relative)")
    .option("--model <model>", "Filter by model name")
    .option("--status <status>", "Filter by HTTP status code")
    .option("--user-id <userId>", "Filter by user ID")
    .option(
      "-p, --property <key=value>",
      "Filter by property",
      (value: string, previous: string[]) => {
        previous.push(value);
        return previous;
      },
      [] as string[]
    )
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)")
    .action(async (options: ExportOptions & { property: string[] }) => {
      try {
        const auth = getAuthContext(options.apiKey, options.region);
        const client = new HeliconeClient(auth);

        // Parse filters
        const startDate = options.since ? parseDate(options.since) : undefined;
        const endDate = options.until ? parseDate(options.until) : undefined;

        // Parse property filters
        const properties: Record<string, string> = {};
        for (const prop of options.property || []) {
          const [key, value] = prop.split("=");
          if (key && value) {
            properties[key] = value;
          }
        }

        const filter = buildFilter({
          model: options.model,
          status: options.status ? parseInt(options.status, 10) : undefined,
          userId: options.userId,
          startDate,
          endDate,
          properties: Object.keys(properties).length > 0 ? properties : undefined,
        });

        const outputPath = options.output || "requests-export.jsonl";
        const format = (options.format || "jsonl") as OutputFormat;
        const batchSize = parseInt(options.batchSize as string, 10) || 1000;
        const maxRecords = options.limit ? parseInt(options.limit as string, 10) : undefined;

        // Get total count first
        console.log(chalk.dim("Counting records..."));
        const countResult = await client.countRequests(filter);
        const totalCount = countResult.data || 0;

        if (totalCount === 0) {
          console.log(chalk.yellow("No requests found matching the filters"));
          return;
        }

        const recordsToExport = maxRecords
          ? Math.min(totalCount, maxRecords)
          : totalCount;

        console.log(
          chalk.dim(
            `Found ${totalCount.toLocaleString()} records. Exporting ${recordsToExport.toLocaleString()}...`
          )
        );

        // Open output file
        const stream = fs.createWriteStream(outputPath);

        // Write header for formats that need it
        if (format === "json") {
          stream.write("[\n");
        } else if (format === "csv") {
          const fields = options.fields
            ? parseFields(options.fields)
            : REQUEST_DEFAULT_FIELDS;
          stream.write(fields.join(",") + "\n");
        }

        let offset = 0;
        let exported = 0;
        let isFirst = true;
        const startTime = Date.now();

        while (exported < recordsToExport) {
          const limit = Math.min(batchSize, recordsToExport - exported);

          const result = await client.queryRequests({
            filter,
            limit,
            offset,
            sort: { created_at: "desc" },
          });

          if (result.error) {
            console.error(chalk.red(`\nError: ${result.error}`));
            stream.close();
            process.exit(1);
          }

          const requests = result.data || [];

          if (requests.length === 0) {
            break;
          }

          // Fetch bodies if requested
          if (options.includeBody) {
            for (const req of requests) {
              if (req.signed_body_url) {
                const body = await client.fetchSignedBody(req.signed_body_url);
                if (body.request) req.request_body = body.request;
                if (body.response) req.response_body = body.response;
              }
            }
          }

          // Write to file
          for (const req of requests) {
            if (format === "jsonl") {
              stream.write(JSON.stringify(req) + "\n");
            } else if (format === "json") {
              if (!isFirst) stream.write(",\n");
              stream.write(JSON.stringify(req, null, 2));
              isFirst = false;
            } else if (format === "csv") {
              const fields = options.fields
                ? parseFields(options.fields)
                : REQUEST_DEFAULT_FIELDS;
              const row = fields
                .map((field) => {
                  const value = (req as Record<string, unknown>)[field];
                  if (value === null || value === undefined) return "";
                  const str = String(value);
                  if (str.includes(",") || str.includes('"')) {
                    return `"${str.replace(/"/g, '""')}"`;
                  }
                  return str;
                })
                .join(",");
              stream.write(row + "\n");
            }
          }

          exported += requests.length;
          offset += batchSize;

          // Progress update
          const elapsed = (Date.now() - startTime) / 1000;
          const rate = exported / elapsed;
          const remaining = (recordsToExport - exported) / rate;

          process.stdout.write(
            `\r${chalk.dim(
              `Exported ${exported.toLocaleString()}/${recordsToExport.toLocaleString()} ` +
                `(${((exported / recordsToExport) * 100).toFixed(1)}%) ` +
                `- ${rate.toFixed(0)} rec/s - ETA: ${remaining.toFixed(0)}s`
            )}`
          );

          // Small delay between batches
          await new Promise((resolve) => setTimeout(resolve, 100));
        }

        // Close file
        if (format === "json") {
          stream.write("\n]\n");
        }
        stream.close();

        const totalTime = ((Date.now() - startTime) / 1000).toFixed(1);
        console.log(
          `\n${chalk.green("✓")} Exported ${exported.toLocaleString()} records to ${outputPath} in ${totalTime}s`
        );
      } catch (error) {
        console.error(chalk.red(`Error: ${(error as Error).message}`));
        process.exit(1);
      }
    });

  // ============================================================================
  // helicone requests fields
  // ============================================================================
  requests
    .command("fields")
    .description("List available fields for requests")
    .action(() => {
      console.log(chalk.bold("\nAvailable Request Fields:\n"));

      const descriptions: Record<string, string> = {
        request_id: "Unique request identifier",
        created_at: "Request timestamp",
        model: "Model name (resolved)",
        provider: "LLM provider (OPENAI, ANTHROPIC, etc.)",
        status: "HTTP response status code",
        latency_ms: "Total latency in milliseconds",
        ttft_ms: "Time to first token in milliseconds",
        tokens: "Total token count",
        prompt_tokens: "Input token count",
        completion_tokens: "Output token count",
        cost: "Cost in USD",
        user_id: "Your application's user ID",
        country: "Request origin country code",
        cached: "Whether response was cached",
        path: "API endpoint path",
      };

      for (const field of REQUEST_AVAILABLE_FIELDS) {
        const desc = descriptions[field] || "";
        const isDefault = REQUEST_DEFAULT_FIELDS.includes(field);
        console.log(
          `  ${chalk.cyan(field.padEnd(20))} ${desc}${isDefault ? chalk.dim(" (default)") : ""}`
        );
      }

      console.log(
        chalk.dim("\nUse --fields to specify which fields to display\n")
      );
    });

  return requests;
}
