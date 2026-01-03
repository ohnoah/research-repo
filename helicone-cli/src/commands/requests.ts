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
    .description("Get a single request by ID with flexible viewing options")
    .option(
      "-s, --show <section>",
      "What to show: summary, messages, request, response, metadata, properties, scores, all",
      "summary"
    )
    .option(
      "-e, --extract <path>",
      "Extract a specific field (e.g., 'response_body.choices[0].message.content')"
    )
    .option("--raw", "Output raw JSON (equivalent to --show all --format json)")
    .option(
      "-f, --format <format>",
      "Output format for --show all: json, jsonl",
      "json"
    )
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)")
    .action(async (requestId: string, options: GetOptions & { show?: string; extract?: string; raw?: boolean }) => {
      try {
        const auth = getAuthContext(options.apiKey, options.region);
        const client = new HeliconeClient(auth);

        const spinner = ora("Fetching request...").start();

        // Always fetch with body for most views
        const needsBody = options.show !== "metadata" && options.show !== "properties" && options.show !== "scores";
        const result = await client.getRequest(requestId, needsBody);

        if (result.error) {
          spinner.fail(chalk.red(`Error: ${result.error}`));
          process.exit(1);
        }

        spinner.stop();

        if (!result.data) {
          console.log(chalk.yellow("Request not found"));
          return;
        }

        const req = result.data;

        // Handle --extract for jq-like field extraction
        if (options.extract) {
          const value = extractPath(req, options.extract);
          if (value === undefined) {
            console.log(chalk.yellow(`Path '${options.extract}' not found`));
          } else if (typeof value === "string") {
            console.log(value);
          } else {
            console.log(JSON.stringify(value, null, 2));
          }
          return;
        }

        // Handle --raw flag
        if (options.raw) {
          console.log(JSON.stringify(req, null, 2));
          return;
        }

        // Handle different --show options
        const section = options.show || "summary";

        switch (section) {
          case "summary":
            printRequestSummary(req);
            break;

          case "messages":
            printMessages(req);
            break;

          case "request":
            printSection("Request Body", req.request_body);
            break;

          case "response":
            printSection("Response Body", req.response_body);
            break;

          case "metadata":
            printMetadata(req);
            break;

          case "properties":
            printSection("Properties", req.properties || req.request_properties);
            break;

          case "scores":
            printSection("Scores", req.scores);
            break;

          case "all":
            const format = (options.format || "json") as OutputFormat;
            if (format === "json") {
              console.log(JSON.stringify(req, null, 2));
            } else {
              console.log(JSON.stringify(req));
            }
            break;

          default:
            console.error(chalk.red(`Unknown section: ${section}`));
            console.log(chalk.dim("Available: summary, messages, request, response, metadata, properties, scores, all"));
            process.exit(1);
        }
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

// ============================================================================
// Helper Functions for Request Display
// ============================================================================

/**
 * Extract a value from an object using a dot-notation path with array support
 * e.g., "response_body.choices[0].message.content"
 */
function extractPath(obj: unknown, path: string): unknown {
  const parts = path.split(/\.|\[|\]/).filter(Boolean);
  let current: unknown = obj;

  for (const part of parts) {
    if (current === null || current === undefined) {
      return undefined;
    }
    if (typeof current === "object") {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }

  return current;
}

/**
 * Print a clean summary of a request
 */
function printRequestSummary(req: Record<string, unknown>): void {
  console.log(chalk.bold("\n📋 Request Summary\n"));

  const summary = [
    ["ID", req.request_id || req.id],
    ["Created", req.created_at ? new Date(req.created_at as string).toLocaleString() : "N/A"],
    ["Model", req.model || req.model_override || "Unknown"],
    ["Provider", req.provider || "Unknown"],
    ["Status", formatStatus(req.status as number)],
    ["Latency", req.latency_ms ? `${req.latency_ms}ms` : "N/A"],
    ["TTFT", req.time_to_first_token ? `${req.time_to_first_token}ms` : "N/A"],
  ];

  // Token info
  const promptTokens = req.prompt_tokens || (req.request_body as Record<string, unknown>)?.usage?.prompt_tokens;
  const completionTokens = req.completion_tokens || (req.response_body as Record<string, unknown>)?.usage?.completion_tokens;
  const totalTokens = req.total_tokens || (promptTokens && completionTokens ? (promptTokens as number) + (completionTokens as number) : null);

  if (totalTokens) {
    summary.push(["Tokens", `${totalTokens} (${promptTokens || "?"} prompt, ${completionTokens || "?"} completion)`]);
  }

  // Cost
  if (req.cost_usd || req.cost) {
    const cost = req.cost_usd || req.cost;
    summary.push(["Cost", `$${(cost as number).toFixed(6)}`]);
  }

  // User
  if (req.user_id) {
    summary.push(["User ID", req.user_id]);
  }

  // Path
  if (req.path || req.target_url) {
    summary.push(["Path", req.path || req.target_url]);
  }

  // Print summary table
  for (const [label, value] of summary) {
    console.log(`  ${chalk.dim(String(label).padEnd(12))} ${value}`);
  }

  // Properties preview
  const properties = req.properties || req.request_properties;
  if (properties && typeof properties === "object" && Object.keys(properties as object).length > 0) {
    console.log(`\n  ${chalk.dim("Properties:")} ${Object.keys(properties as object).join(", ")}`);
  }

  // Scores preview
  if (req.scores && typeof req.scores === "object" && Object.keys(req.scores as object).length > 0) {
    console.log(`  ${chalk.dim("Scores:")} ${Object.keys(req.scores as object).join(", ")}`);
  }

  console.log(chalk.dim("\n  Use --show <section> for more details: messages, request, response, metadata, properties, scores, all"));
  console.log(chalk.dim("  Use --extract <path> to extract specific fields, e.g., --extract response_body.choices[0].message.content\n"));
}

/**
 * Format HTTP status with color
 */
function formatStatus(status: number | undefined): string {
  if (!status) return "N/A";
  if (status >= 200 && status < 300) return chalk.green(status.toString());
  if (status >= 400 && status < 500) return chalk.yellow(status.toString());
  if (status >= 500) return chalk.red(status.toString());
  return status.toString();
}

/**
 * Print messages from a chat completion request
 */
function printMessages(req: Record<string, unknown>): void {
  console.log(chalk.bold("\n💬 Messages\n"));

  // Try to find messages in request body
  const requestBody = req.request_body as Record<string, unknown> | undefined;
  const responseBody = req.response_body as Record<string, unknown> | undefined;

  const inputMessages = requestBody?.messages as Array<{ role: string; content: unknown }> | undefined;
  const outputChoices = responseBody?.choices as Array<{ message?: { role: string; content: string }; delta?: { content: string } }> | undefined;

  if (!inputMessages && !outputChoices) {
    console.log(chalk.yellow("  No chat messages found. This may not be a chat completion request."));
    console.log(chalk.dim("  Use --show request or --show response to see raw bodies.\n"));
    return;
  }

  // Print input messages
  if (inputMessages && Array.isArray(inputMessages)) {
    for (const msg of inputMessages) {
      printMessage(msg.role, msg.content);
    }
  }

  // Print output message
  if (outputChoices && Array.isArray(outputChoices) && outputChoices.length > 0) {
    const choice = outputChoices[0];
    const content = choice.message?.content || choice.delta?.content;
    if (content) {
      printMessage("assistant", content);
    }
  }

  console.log();
}

/**
 * Print a single message with role-based formatting
 */
function printMessage(role: string, content: unknown): void {
  const roleColors: Record<string, (s: string) => string> = {
    system: chalk.magenta,
    user: chalk.blue,
    assistant: chalk.green,
    function: chalk.yellow,
    tool: chalk.yellow,
  };

  const colorFn = roleColors[role] || chalk.white;
  console.log(colorFn(`  [${role.toUpperCase()}]`));

  // Handle different content types
  if (typeof content === "string") {
    // Indent multi-line content
    const lines = content.split("\n");
    for (const line of lines) {
      console.log(`    ${line}`);
    }
  } else if (Array.isArray(content)) {
    // Handle content array (e.g., multimodal messages)
    for (const part of content) {
      if (typeof part === "object" && part !== null) {
        const typedPart = part as { type?: string; text?: string; image_url?: unknown };
        if (typedPart.type === "text" && typedPart.text) {
          const lines = typedPart.text.split("\n");
          for (const line of lines) {
            console.log(`    ${line}`);
          }
        } else if (typedPart.type === "image_url") {
          console.log(chalk.dim("    [Image]"));
        } else {
          console.log(`    ${JSON.stringify(part)}`);
        }
      }
    }
  } else if (content !== null && content !== undefined) {
    console.log(`    ${JSON.stringify(content, null, 2).split("\n").join("\n    ")}`);
  }

  console.log();
}

/**
 * Print a section with a title
 */
function printSection(title: string, data: unknown): void {
  console.log(chalk.bold(`\n📄 ${title}\n`));

  if (data === null || data === undefined) {
    console.log(chalk.yellow("  No data available\n"));
    return;
  }

  if (typeof data === "object") {
    console.log(JSON.stringify(data, null, 2));
  } else {
    console.log(String(data));
  }

  console.log();
}

/**
 * Print request metadata (timing, tokens, cost)
 */
function printMetadata(req: Record<string, unknown>): void {
  console.log(chalk.bold("\n📊 Request Metadata\n"));

  // Timing
  console.log(chalk.cyan("  Timing:"));
  console.log(`    ${chalk.dim("Created:")}      ${req.created_at ? new Date(req.created_at as string).toISOString() : "N/A"}`);
  console.log(`    ${chalk.dim("Latency:")}      ${req.latency_ms ? `${req.latency_ms}ms` : "N/A"}`);
  console.log(`    ${chalk.dim("TTFT:")}         ${req.time_to_first_token ? `${req.time_to_first_token}ms` : "N/A"}`);

  // Model info
  console.log(chalk.cyan("\n  Model:"));
  console.log(`    ${chalk.dim("Model:")}        ${req.model || "N/A"}`);
  console.log(`    ${chalk.dim("Provider:")}     ${req.provider || "N/A"}`);
  console.log(`    ${chalk.dim("Status:")}       ${formatStatus(req.status as number)}`);

  // Tokens
  console.log(chalk.cyan("\n  Tokens:"));
  console.log(`    ${chalk.dim("Prompt:")}       ${req.prompt_tokens ?? "N/A"}`);
  console.log(`    ${chalk.dim("Completion:")}   ${req.completion_tokens ?? "N/A"}`);
  console.log(`    ${chalk.dim("Total:")}        ${req.total_tokens ?? "N/A"}`);

  // Cost
  console.log(chalk.cyan("\n  Cost:"));
  const cost = req.cost_usd || req.cost;
  console.log(`    ${chalk.dim("Cost (USD):")}   ${cost ? `$${(cost as number).toFixed(6)}` : "N/A"}`);

  // Location
  if (req.country_code || req.country) {
    console.log(chalk.cyan("\n  Location:"));
    console.log(`    ${chalk.dim("Country:")}      ${req.country_code || req.country || "N/A"}`);
  }

  // Cache
  if (req.cache_enabled !== undefined || req.cached !== undefined) {
    console.log(chalk.cyan("\n  Cache:"));
    console.log(`    ${chalk.dim("Cached:")}       ${req.cached ? "Yes" : "No"}`);
  }

  console.log();
}
