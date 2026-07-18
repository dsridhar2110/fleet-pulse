import { neon } from "@neondatabase/serverless";

// Pooled Neon connection (set by the Vercel–Neon integration in .env.local /
// Vercel project env). The dashboard only ever reads.
const url = process.env.DATABASE_URL;
if (!url) throw new Error("DATABASE_URL is not set (Neon pooled connection string).");

export const sql = neon(url);
