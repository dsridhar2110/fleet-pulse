"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { FastForward, Loader2 } from "lucide-react";
import { advanceDay } from "@/app/actions";

export function AdvanceButton() {
  const [pending, start] = useTransition();
  const [note, setNote] = useState<string | null>(null);
  const router = useRouter();

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      {note && <span className="faint" style={{ fontSize: "0.74rem" }}>{note}</span>}
      <button
        className="advance-btn"
        disabled={pending}
        onClick={() =>
          start(async () => {
            setNote(null);
            const r = await advanceDay();
            if (r.ok) { setNote(`advanced → ${r.date}`); router.refresh(); }
            else setNote(r.error ?? "failed");
          })
        }
      >
        {pending ? <Loader2 size={14} className="spin" /> : <FastForward size={14} />}
        {pending ? "Simulating a day…" : "Advance a day"}
      </button>
    </div>
  );
}
