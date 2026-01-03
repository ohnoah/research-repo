/**
 * Auth commands for managing Helicone credentials
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import {
  storeApiKey,
  clearCredentials,
  hasStoredCredentials,
  getConfigPath,
  getApiKey,
  getRegion,
} from "../lib/config.js";
import { HeliconeClient } from "../lib/client.js";

export function createAuthCommand(): Command {
  const auth = new Command("auth").description("Manage authentication");

  // ============================================================================
  // helicone auth login
  // ============================================================================
  auth
    .command("login")
    .description("Store API key for authentication")
    .option("--api-key <key>", "Helicone API key")
    .option("--region <region>", "API region (us or eu)", "us")
    .action(async (options) => {
      let apiKey = options.apiKey;

      // If no API key provided, check environment
      if (!apiKey) {
        apiKey = process.env.HELICONE_API_KEY;
      }

      // If still no API key, prompt for it
      if (!apiKey) {
        // Dynamic import for enquirer (ESM compatibility)
        const { default: Enquirer } = await import("enquirer");
        const enquirer = new Enquirer();

        const response = await enquirer.prompt<{ apiKey: string }>({
          type: "password",
          name: "apiKey",
          message: "Enter your Helicone API key:",
        });
        apiKey = response.apiKey;
      }

      if (!apiKey) {
        console.error(chalk.red("Error: No API key provided"));
        process.exit(1);
      }

      // Validate region
      const region = options.region === "eu" ? "eu" : "us";

      // Verify the API key works
      const spinner = ora("Verifying API key...").start();

      const client = new HeliconeClient({ apiKey, region });
      const result = await client.verifyAuth();

      if (result.error) {
        spinner.fail(chalk.red(`Authentication failed: ${result.error}`));
        process.exit(1);
      }

      // Store credentials
      storeApiKey(apiKey, region);
      spinner.succeed(chalk.green("Logged in successfully"));

      console.log(chalk.dim(`Credentials stored in ${getConfigPath()}`));
      console.log(chalk.dim(`Region: ${region.toUpperCase()}`));
    });

  // ============================================================================
  // helicone auth logout
  // ============================================================================
  auth
    .command("logout")
    .description("Remove stored credentials")
    .action(() => {
      if (!hasStoredCredentials()) {
        console.log(chalk.yellow("No stored credentials found"));
        return;
      }

      clearCredentials();
      console.log(chalk.green("Logged out successfully"));
      console.log(chalk.dim(`Credentials removed from ${getConfigPath()}`));
    });

  // ============================================================================
  // helicone auth status
  // ============================================================================
  auth
    .command("status")
    .description("Show current authentication status")
    .action(async () => {
      const apiKey = getApiKey();
      const region = getRegion();

      console.log(chalk.bold("\nAuthentication Status\n"));

      // Check for API key sources
      if (process.env.HELICONE_API_KEY) {
        console.log(
          chalk.green("✓"),
          "API Key:",
          chalk.dim("(from HELICONE_API_KEY environment variable)")
        );
      } else if (hasStoredCredentials()) {
        console.log(
          chalk.green("✓"),
          "API Key:",
          chalk.dim(`(from ${getConfigPath()})`)
        );
      } else {
        console.log(chalk.red("✗"), "API Key:", chalk.red("Not configured"));
        console.log(
          chalk.dim(
            "\n  Run 'helicone auth login' or set HELICONE_API_KEY environment variable"
          )
        );
        return;
      }

      console.log("  Region:", chalk.cyan(region.toUpperCase()));

      // Verify the key works
      if (apiKey) {
        const spinner = ora("Verifying credentials...").start();

        const client = new HeliconeClient({ apiKey, region });
        const result = await client.verifyAuth();

        if (result.error) {
          spinner.fail(chalk.red(`Invalid credentials: ${result.error}`));
        } else {
          spinner.succeed(chalk.green("Credentials verified"));
        }
      }
    });

  // ============================================================================
  // helicone auth whoami
  // ============================================================================
  auth
    .command("whoami")
    .description("Show current API key info (masked)")
    .action(() => {
      const apiKey = getApiKey();
      const region = getRegion();

      if (!apiKey) {
        console.log(chalk.red("Not logged in"));
        return;
      }

      // Mask API key, show first 4 and last 4 characters
      const masked =
        apiKey.length > 8
          ? `${apiKey.substring(0, 4)}...${apiKey.substring(apiKey.length - 4)}`
          : "****";

      console.log(chalk.bold("Current Configuration:"));
      console.log(`  API Key: ${masked}`);
      console.log(`  Region:  ${region.toUpperCase()}`);
    });

  return auth;
}
