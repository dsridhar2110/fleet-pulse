"use client";

import { useEffect, useMemo, useState } from "react";
import { search, type TicketIndex } from "@/lib/retrieval";
import { Pill } from "./primitives";

const EXAMPLES = [
  "helium is boiling off way too quickly",
  "tube is arcing more than usual",
  "scanner makes a grinding noise when it spins",
  "dead pixels and dropouts in the detector",
];

export function Copilot() {
  const [index, setIndex] = useState<TicketIndex | null>(null);
  const [query, setQuery] = useState(EXAMPLES[0]);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // 187KB, fetched once on the client rather than bundled into the page —
    // the index is data, not code.
    fetch("/data/tickets_index.json")
      .then((r) => r.json())
      .then(setIndex)
      .catch(() => setFailed(true));
  }, []);

  const result = useMemo(() => (index ? search(index, query, 5) : null), [index, query]);

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border p-6">
        <label htmlFor="copilot" className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
          Describe the symptom, as an engineer would
        </label>
        <input
          id="copilot"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. helium level dropping fast"
          className="mt-3 w-full rounded-md border border-input bg-background px-4 py-3 text-base outline-none focus:border-primary focus:ring-2 focus:ring-ring/30"
        />
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              type="button"
              onClick={() => setQuery(ex)}
              className="rounded-full border border-border bg-muted/60 px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      <div className="p-6">
        {failed ? (
          <p className="text-sm text-critical">Could not load the ticket index.</p>
        ) : !index ? (
          <p className="text-sm text-muted-foreground">Loading 440 resolved tickets…</p>
        ) : !result || result.hits.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            <p>Nothing in the ticket history matches those words.</p>
            {result && result.unknownTerms.length > 0 ? (
              <p className="mt-2">
                None of{" "}
                {result.unknownTerms.map((t) => (
                  <code key={t} className="mx-0.5 rounded bg-muted px-1 py-0.5 font-mono text-xs">
                    {t}
                  </code>
                ))}{" "}
                appear in the 73-term corpus vocabulary. This is exactly the out-of-vocabulary failure
                that motivates embeddings over TF-IDF.
              </p>
            ) : null}
          </div>
        ) : (
          <>
            {result.consensus ? (
              <div className="mb-6 rounded-lg bg-ground px-5 py-4 text-ground-foreground">
                <p className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-white/60">
                  Consensus of the 10 most similar past tickets
                </p>
                <p className="mt-2 text-xl font-semibold text-teal-bright">
                  {result.consensus.label}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-white/75">
                  {(result.consensus.share * 100).toFixed(0)}% of the retrieved similarity points at this
                  component
                  {result.likelyPart ? (
                    <>
                      . Most commonly replaced:{" "}
                      <span className="font-mono text-white">{result.likelyPart}</span>
                    </>
                  ) : null}
                  {result.medianDowntime !== null ? (
                    <>
                      . Median downtime when it happened:{" "}
                      <span className="tnum font-semibold text-white">
                        {result.medianDowntime} {result.medianDowntime === 1 ? "day" : "days"}
                      </span>
                    </>
                  ) : null}
                  .
                </p>
              </div>
            ) : null}

            <p className="mb-3 text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
              Closest resolved tickets
            </p>
            <ul className="flex flex-col divide-y divide-border">
              {result.hits.map(({ ticket, similarity }) => (
                <li key={ticket.id} className="flex flex-col gap-2 py-4 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm text-primary">{ticket.machine_id}</span>
                    <Pill tone="neutral">{ticket.modality}</Pill>
                    <Pill tone="neutral">{ticket.component_label}</Pill>
                    <span className="tnum ml-auto text-xs text-muted-foreground">
                      similarity {similarity.toFixed(2)}
                    </span>
                  </div>
                  <p className="text-sm leading-relaxed text-foreground/85">&ldquo;{ticket.note}&rdquo;</p>
                  <p className="text-xs text-muted-foreground">
                    {ticket.opened} · replaced{" "}
                    <span className="font-mono">{ticket.part_replaced}</span> ·{" "}
                    <span className="tnum">{ticket.downtime_days}</span> days down
                  </p>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
