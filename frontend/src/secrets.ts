const SECRET = /private|secret|api[_-]?key|authorization|password|seed|mnemonic/i;

export function stripSecrets(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => stripSecrets(item));
  }
  if (value && typeof value === "object") {
    const cleaned: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      if (SECRET.test(key)) {
        continue;
      }
      cleaned[key] = stripSecrets(item);
    }
    return cleaned;
  }
  if (typeof value === "string" && value.includes("PRIVATE KEY")) {
    return "[redacted]";
  }
  return value;
}
