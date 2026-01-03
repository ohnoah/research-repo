/**
 * Helicone CLI - Command-line interface for Helicone data
 *
 * Usage:
 *   helicone auth login           # Store API key
 *   helicone requests list        # List requests
 *   helicone sessions list        # List sessions
 *   helicone metrics summary      # Show metrics
 */

import { Command } from "commander";
import chalk from "chalk";
import { createAuthCommand } from "./commands/auth.js";
import { createRequestsCommand } from "./commands/requests.js";
import { createSessionsCommand } from "./commands/sessions.js";
import { createMetricsCommand } from "./commands/metrics.js";

const program = new Command();

program
  .name("helicone")
  .description("CLI for fetching data from Helicone")
  .version("0.1.0");

// Add subcommands
program.addCommand(createAuthCommand());
program.addCommand(createRequestsCommand());
program.addCommand(createSessionsCommand());
program.addCommand(createMetricsCommand());

// Add helpful examples in help text
program.addHelpText(
  "after",
  `
${chalk.bold("Examples:")}
  ${chalk.dim("# Login with API key")}
  $ helicone auth login --api-key sk-helicone-...

  ${chalk.dim("# List recent requests")}
  $ helicone requests list --since 24h --limit 50

  ${chalk.dim("# List requests with filters")}
  $ helicone requests list --model gpt-4o --status 200

  ${chalk.dim("# Export requests to file")}
  $ helicone requests export --since 7d --format jsonl -o requests.jsonl

  ${chalk.dim("# List sessions")}
  $ helicone sessions list --since 7d

  ${chalk.dim("# View metrics summary")}
  $ helicone metrics summary --since 30d

  ${chalk.dim("# View cost breakdown by model")}
  $ helicone metrics cost --by model --since 7d

${chalk.bold("Authentication:")}
  API key can be provided via:
  1. --api-key flag
  2. HELICONE_API_KEY environment variable
  3. Stored credentials (run 'helicone auth login')

${chalk.bold("More Info:")}
  Run 'helicone <command> --help' for command-specific help
  Documentation: https://docs.helicone.ai
`
);

// Handle unknown commands
program.on("command:*", () => {
  console.error(
    chalk.red(`Unknown command: ${program.args.join(" ")}\n`)
  );
  console.log("Run 'helicone --help' for available commands");
  process.exit(1);
});

// Parse and execute
program.parse();

// Show help if no command provided
if (!process.argv.slice(2).length) {
  program.outputHelp();
}
