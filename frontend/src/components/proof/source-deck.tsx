"use client";

import { CheckCircle2, ChevronDown, FileText } from "lucide-react";
import { useState } from "react";

import type { IndexMutation, ProofSource } from "@/lib/proof-types";

interface SourceDeckProps {
  sources: ProofSource[];
  results: ReadonlyMap<string, IndexMutation>;
  disabled: boolean;
  onChange: (sources: ProofSource[]) => void;
  onIngest: () => void;
}

export function SourceDeck({
  sources,
  results,
  disabled,
  onChange,
  onIngest,
}: SourceDeckProps) {
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());

  const toggle = (externalId: string) => {
    setOpenIds((current) => {
      const next = new Set(current);
      if (next.has(externalId)) {
        next.delete(externalId);
      } else {
        next.add(externalId);
      }
      return next;
    });
  };

  const updateText = (externalId: string, text: string) => {
    onChange(
      sources.map((source) =>
        source.externalId === externalId ? { ...source, text } : source
      )
    );
  };

  return (
    <section
      aria-labelledby="proof-sources-heading"
      className="rounded-2xl border bg-card p-4 shadow-[5px_5px_0_0_#1a1a1a] sm:p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.22em] text-muted-foreground">
            01 · Evidence corpus
          </p>
          <h2 id="proof-sources-heading" className="mt-1 text-2xl font-black">
            Three inspectable sources
          </h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">
            Read every byte before indexing it. Nothing enters the proof corpus
            invisibly.
          </p>
        </div>
        <button
          type="button"
          onClick={onIngest}
          disabled={disabled || sources.some((source) => !source.text.trim())}
          className="min-h-11 rounded-lg border-2 border-foreground bg-primary px-4 py-2 text-sm font-black text-primary-foreground shadow-[3px_3px_0_0_#1a1a1a] transition-transform hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {disabled ? "Indexing sources…" : "Ingest 3 sources"}
        </button>
      </div>

      <div className="mt-5 grid gap-3">
        {sources.map((source, index) => {
          const isOpen = openIds.has(source.externalId);
          const result = results.get(source.externalId);
          const panelId = `source-${source.externalId}`;
          return (
            <article key={source.externalId} className="rounded-xl border bg-background">
              <button
                type="button"
                aria-expanded={isOpen}
                aria-controls={panelId}
                onClick={() => toggle(source.externalId)}
                className="flex min-h-14 w-full items-center gap-3 px-4 py-3 text-left focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border bg-card text-xs font-black">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 font-bold">
                    <FileText className="h-4 w-4" aria-hidden="true" />
                    {source.title}
                  </span>
                  <span className="mt-0.5 block truncate font-mono text-xs text-muted-foreground">
                    {source.externalId}
                  </span>
                </span>
                {result && (
                  <CheckCircle2
                    className="h-5 w-5 text-green-700"
                    aria-label="Indexed"
                  />
                )}
                <span className="sr-only">Inspect source {source.title}</span>
                <ChevronDown
                  aria-hidden="true"
                  className={`h-5 w-5 transition-transform ${isOpen ? "rotate-180" : ""}`}
                />
              </button>
              {isOpen && (
                <div id={panelId} className="border-t p-4">
                  <label
                    htmlFor={`${panelId}-text`}
                    className="text-xs font-black uppercase tracking-[0.16em]"
                  >
                    Source text
                  </label>
                  <textarea
                    id={`${panelId}-text`}
                    value={source.text}
                    onChange={(event) =>
                      updateText(source.externalId, event.target.value)
                    }
                    disabled={disabled}
                    rows={5}
                    className="mt-2 w-full resize-y rounded-lg border bg-card p-3 font-mono text-xs leading-5 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-60"
                  />
                  {result && (
                    <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                      {result.source_id} · {result.index_version} ·{" "}
                      {result.changed ? "indexed" : "unchanged"}
                    </p>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
