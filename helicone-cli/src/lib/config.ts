/**
 * Configuration management for Helicone CLI
 *
 * Config precedence (highest to lowest):
 * 1. CLI flags (--api-key, --region)
 * 2. Environment variables (HELICONE_API_KEY, HELICONE_REGION)
 * 3. Config file (~/.helicone/config.yaml)
 */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import YAML from "yaml";
import type { Config, AuthContext } from "./types.js";

const CONFIG_DIR = path.join(os.homedir(), ".helicone");
const CONFIG_FILE = path.join(CONFIG_DIR, "config.yaml");

/**
 * Ensure config directory exists
 */
function ensureConfigDir(): void {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { mode: 0o700 });
  }
}

/**
 * Load config from file
 */
export function loadConfig(): Config {
  try {
    if (fs.existsSync(CONFIG_FILE)) {
      const content = fs.readFileSync(CONFIG_FILE, "utf-8");
      return YAML.parse(content) as Config;
    }
  } catch (error) {
    // Ignore errors, return empty config
  }
  return {};
}

/**
 * Save config to file
 */
export function saveConfig(config: Config): void {
  ensureConfigDir();
  const content = YAML.stringify(config);
  fs.writeFileSync(CONFIG_FILE, content, { mode: 0o600 });
}

/**
 * Get API key from various sources
 */
export function getApiKey(cliApiKey?: string): string | undefined {
  // 1. CLI flag
  if (cliApiKey) {
    return cliApiKey;
  }

  // 2. Environment variable
  const envKey = process.env.HELICONE_API_KEY;
  if (envKey) {
    return envKey;
  }

  // 3. Config file
  const config = loadConfig();
  return config.apiKey;
}

/**
 * Get region from various sources
 */
export function getRegion(cliRegion?: string): "us" | "eu" {
  // 1. CLI flag
  if (cliRegion === "us" || cliRegion === "eu") {
    return cliRegion;
  }

  // 2. Environment variable
  const envRegion = process.env.HELICONE_REGION;
  if (envRegion === "us" || envRegion === "eu") {
    return envRegion;
  }

  // 3. Config file
  const config = loadConfig();
  if (config.region === "us" || config.region === "eu") {
    return config.region;
  }

  // Default to US
  return "us";
}

/**
 * Get auth context from all sources, validate, and return
 */
export function getAuthContext(
  cliApiKey?: string,
  cliRegion?: string
): AuthContext {
  const apiKey = getApiKey(cliApiKey);

  if (!apiKey) {
    throw new Error(
      "No API key found. Set HELICONE_API_KEY environment variable, " +
        "use --api-key flag, or run 'helicone auth login'"
    );
  }

  return {
    apiKey,
    region: getRegion(cliRegion),
  };
}

/**
 * Store API key in config file
 */
export function storeApiKey(apiKey: string, region?: "us" | "eu"): void {
  const config = loadConfig();
  config.apiKey = apiKey;
  if (region) {
    config.region = region;
  }
  saveConfig(config);
}

/**
 * Remove stored credentials
 */
export function clearCredentials(): void {
  const config = loadConfig();
  delete config.apiKey;
  saveConfig(config);
}

/**
 * Check if credentials are stored
 */
export function hasStoredCredentials(): boolean {
  const config = loadConfig();
  return !!config.apiKey;
}

/**
 * Get config file path (for display purposes)
 */
export function getConfigPath(): string {
  return CONFIG_FILE;
}
