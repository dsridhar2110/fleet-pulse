/**
 * Browser-side scorer for the Module 3 ticket index.
 *
 * This is a deliberate mirror of `ml/src/models/retrieval.py` — same stoplist,
 * same tokenizer, same sublinear-tf weighting, same L2 normalisation. The
 * document vectors were computed in Python and shipped as JSON; only the query
 * side runs here. If you change one file, change the other, or the query and
 * the corpus stop speaking the same language.
 */

export type Ticket = {
  id: number;
  machine_id: string;
  modality: string;
  country: string;
  component: string;
  component_label: string;
  part_replaced: string;
  downtime_days: number;
  opened: string;
  symptom: string;
  action: string;
  note: string;
  vec: Record<string, number>;
};

export type TicketIndex = {
  vocab: Record<string, number>;
  idf: number[];
  tickets: Ticket[];
};

export type Hit = { ticket: Ticket; similarity: number };

export type CopilotAnswer = {
  hits: Hit[];
  /** Similarity-weighted vote across the top-k retrieved tickets. */
  consensus: { label: string; component: string; share: number } | null;
  /** Most frequent part among the retrieved tickets that voted for the consensus. */
  likelyPart: string | null;
  medianDowntime: number | null;
  matchedTerms: string[];
  unknownTerms: string[];
};

const STOP = new Set(["the", "a", "an", "and", "of", "to", "on", "in", "at", "for", "is", "was", "it"]);
const NOISE = new Set(["esc", "l2", "ref", "prev", "tkt"]);

export function tokenize(text: string): string[] {
  const raw = text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  return raw.filter((t) => !STOP.has(t) && !NOISE.has(t) && t.length > 1);
}

export function search(index: TicketIndex, query: string, k = 5): CopilotAnswer {
  const tokens = tokenize(query);
  const matchedTerms = tokens.filter((t) => t in index.vocab);
  const unknownTerms = [...new Set(tokens.filter((t) => !(t in index.vocab)))];

  if (matchedTerms.length === 0) {
    return { hits: [], consensus: null, likelyPart: null, medianDowntime: null, matchedTerms: [], unknownTerms };
  }

  // Query vector: sublinear tf x idf, L2-normalised — identical to the corpus side.
  const tf = new Map<string, number>();
  for (const t of matchedTerms) tf.set(t, (tf.get(t) ?? 0) + 1);

  const q = new Map<string, number>();
  for (const [term, count] of tf) {
    const i = index.vocab[term];
    q.set(String(i), (1 + Math.log(count)) * index.idf[i]);
  }
  const norm = Math.sqrt([...q.values()].reduce((s, v) => s + v * v, 0)) || 1;
  for (const [key, v] of q) q.set(key, v / norm);

  const scored = index.tickets
    .map((ticket) => {
      let s = 0;
      for (const [key, v] of q) {
        const dv = ticket.vec[key];
        if (dv !== undefined) s += v * dv;
      }
      return { ticket, similarity: s };
    })
    .filter((h) => h.similarity > 0)
    .sort((a, b) => b.similarity - a.similarity);

  const hits = scored.slice(0, k);

  // Consensus over the top-10, weighted by similarity. Shown instead of trusting
  // the single nearest ticket, which can match on an incidental shared word.
  const pool = scored.slice(0, 10);
  const votes = new Map<string, { weight: number; label: string }>();
  let total = 0;
  for (const { ticket, similarity } of pool) {
    const prev = votes.get(ticket.component) ?? { weight: 0, label: ticket.component_label };
    prev.weight += similarity;
    votes.set(ticket.component, prev);
    total += similarity;
  }

  let consensus: CopilotAnswer["consensus"] = null;
  if (votes.size > 0 && total > 0) {
    const [component, { weight, label }] = [...votes.entries()].sort((a, b) => b[1].weight - a[1].weight)[0];
    consensus = { component, label, share: weight / total };
  }

  let likelyPart: string | null = null;
  let medianDowntime: number | null = null;
  if (consensus) {
    const agreeing = pool.filter((h) => h.ticket.component === consensus!.component);
    const partCounts = new Map<string, number>();
    for (const { ticket } of agreeing) {
      partCounts.set(ticket.part_replaced, (partCounts.get(ticket.part_replaced) ?? 0) + 1);
    }
    likelyPart = [...partCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;

    const downtimes = agreeing.map((h) => h.ticket.downtime_days).sort((a, b) => a - b);
    if (downtimes.length) {
      const mid = Math.floor(downtimes.length / 2);
      medianDowntime =
        downtimes.length % 2 === 0 ? (downtimes[mid - 1] + downtimes[mid]) / 2 : downtimes[mid];
    }
  }

  return { hits, consensus, likelyPart, medianDowntime, matchedTerms: [...new Set(matchedTerms)], unknownTerms };
}
