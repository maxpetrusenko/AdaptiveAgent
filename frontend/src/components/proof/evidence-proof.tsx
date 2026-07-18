import { Gauge, Hash, Quote } from "lucide-react";

import type {
  IndexHealth,
  KnowledgeHit,
  ResearchMode,
  ResearchRun,
} from "@/lib/proof-types";

interface EvidenceProofProps {
  hits: KnowledgeHit[];
  run: ResearchRun | null;
  health: IndexHealth | null;
  mode: ResearchMode;
}

export function EvidenceProof({ hits, run, health, mode }: EvidenceProofProps) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1.4fr_0.6fr]">
      <section
        aria-labelledby="citation-proof-heading"
        className="rounded-2xl border bg-card p-4 sm:p-6"
      >
        <p className="text-xs font-black uppercase tracking-[0.22em] text-muted-foreground">
          {mode === "live"
            ? "03 · Live citation-verified output"
            : "03 · Fixture output + native inspection"}
        </p>
        <h2 id="citation-proof-heading" className="mt-1 text-2xl font-black">
          Citations you can audit
        </h2>
        <p className="mt-3 rounded-lg border bg-background p-3 text-xs leading-5 text-muted-foreground">
          {mode === "live"
            ? "Exact sealed run evidence: every displayed source was retrieved for this run and approved by the citation/overlap verifier."
            : "Fixture run. Results below are a separate native retrieval inspection, not evidence used by the fixture synthesizer."}
        </p>
        {run?.artifacts.synthesis ? (
          <div className="mt-4">
            <p className="text-[10px] font-black uppercase tracking-[0.16em] text-muted-foreground">
              {mode === "live" ? "Live synthesis" : "Fixture synthesis"}
            </p>
            <blockquote className="mt-2 border-l-4 border-primary pl-4 text-lg font-bold leading-7">
              {run.artifacts.synthesis.answer}
            </blockquote>
          </div>
        ) : (
          <p className="mt-4 rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            {mode === "live"
              ? "Complete the crash-and-resume run to materialize live citation-verified evidence."
              : "Complete the crash-and-resume run to inspect fixture output beside a separate native search."}
          </p>
        )}

        <div className="mt-5 grid gap-3">
          {hits.map((hit) => (
            <article key={hit.citation_id} className="rounded-xl border bg-background p-4">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="flex items-center gap-2 font-mono text-xs font-black">
                    <Quote className="h-4 w-4 text-green-700" aria-hidden="true" />
                    {hit.citation_id}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                    {hit.source_id}
                  </p>
                </div>
                <span className="w-fit rounded-full border bg-primary px-2 py-1 text-[10px] font-black uppercase">
                  {mode === "live"
                    ? "sealed cited source"
                    : "native inspection source"}
                </span>
              </div>
              <p className="mt-3 text-sm leading-6">{hit.text}</p>
              <dl className="mt-4 grid gap-3 border-t pt-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
                <Metadata label="Content hash" value={hit.content_hash} />
                <Metadata label="Embedding model" value={hit.embedding_fingerprint} />
                <Metadata label="Index" value={hit.index_version} />
                <Metadata
                  label="Ranks"
                  value={`dense ${hit.dense_rank ?? "—"} · BM25 ${hit.lexical_rank ?? "—"}`}
                />
              </dl>
            </article>
          ))}
        </div>
      </section>

      <aside
        aria-labelledby="benchmark-context-heading"
        className="rounded-2xl border-2 border-foreground bg-primary p-5 text-primary-foreground"
      >
        <Gauge className="h-7 w-7" aria-hidden="true" />
        <p className="mt-4 text-xs font-black uppercase tracking-[0.22em]">
          Benchmark context
        </p>
        <h2 id="benchmark-context-heading" className="mt-1 text-2xl font-black">
          Parity before latency
        </h2>
        <p className="mt-3 text-sm leading-6">
          Rust timing is valid only after ranked IDs, dense scores, and per-leg
          ranks match the Python oracle.
        </p>
        <dl className="mt-5 grid gap-4 border-t-2 border-foreground/20 pt-4">
          <Metadata label="Corpus" value={`${health?.chunk_count ?? 0} active chunks`} />
          <Metadata
            label="Retrieval"
            value="Exact cosine + Tantivy BM25 + deterministic RRF"
          />
          <Metadata
            label="Distribution"
            value="p50 · p95 · p99 · throughput · machine · commit"
          />
          <Metadata
            label="Current proof"
            value={hits.length ? `${hits.length} cited retrieval hits` : "Awaiting run"}
          />
        </dl>
      </aside>
    </div>
  );
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="flex items-center gap-1 text-[10px] font-black uppercase tracking-[0.14em] opacity-60">
        {label === "Content hash" && <Hash className="h-3 w-3" aria-hidden="true" />}
        {label}
      </dt>
      <dd className="mt-1 break-all font-mono text-[11px] font-bold">{value}</dd>
    </div>
  );
}
