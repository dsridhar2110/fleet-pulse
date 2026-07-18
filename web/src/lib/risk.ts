// Pure risk helpers — NO database import, so this is safe to use from client
// components (importing from queries.ts would pull the Neon client into the
// client bundle and crash on the missing DATABASE_URL).

export const CRITICAL = 0.15;
export const WATCH = 0.05;

export function band(p7: number): "critical" | "watch" | "healthy" {
  return p7 >= CRITICAL ? "critical" : p7 >= WATCH ? "watch" : "healthy";
}
