import type { ProofStage, ResearchMode } from "@/lib/proof-types";

export function RunMode({
  mode,
  onChange,
  stage,
}: {
  mode: ResearchMode;
  onChange: (mode: ResearchMode) => void;
  stage: ProofStage;
}) {
  const locked = ["running", "crashed", "resuming", "completed"].includes(stage);

  return (
    <fieldset className="rounded-2xl border bg-card p-4 sm:p-5">
      <legend className="px-2 text-xs font-black uppercase tracking-[0.2em] text-muted-foreground">
        Execution mode
      </legend>
      <div className="grid gap-3 sm:grid-cols-2">
        <ModeChoice
          checked={mode === "deterministic"}
          description="Fixture planner, retriever, synthesizer, and verifier. Proves crash recovery and exactly-once effects, not live model grounding."
          disabled={locked}
          label="Deterministic fixture"
          onChange={() => onChange("deterministic")}
          value="deterministic"
        />
        <ModeChoice
          checked={mode === "live"}
          description="Configured model plus tenant native retrieval. Grounding claims apply only when this live run completes verification."
          disabled={locked}
          label="Live model + native retrieval"
          onChange={() => onChange("live")}
          value="live"
        />
      </div>
      {locked && (
        <p className="mt-3 font-mono text-[11px] text-muted-foreground">
          Mode sealed with this durable run.
        </p>
      )}
    </fieldset>
  );
}

function ModeChoice({
  checked,
  description,
  disabled,
  label,
  onChange,
  value,
}: {
  checked: boolean;
  description: string;
  disabled: boolean;
  label: string;
  onChange: () => void;
  value: ResearchMode;
}) {
  return (
    <label
      className={`cursor-pointer rounded-xl border-2 p-4 transition-colors ${
        checked ? "border-foreground bg-primary/25" : "border-border bg-background"
      } ${disabled ? "cursor-not-allowed opacity-65" : ""}`}
    >
      <span className="flex items-center gap-3">
        <input
          aria-label={label}
          checked={checked}
          className="h-4 w-4 accent-foreground"
          disabled={disabled}
          name="research-mode"
          onChange={onChange}
          type="radio"
          value={value}
        />
        <span className="font-black">{label}</span>
      </span>
      <span className="mt-2 block text-xs leading-5 text-muted-foreground">
        {description}
      </span>
    </label>
  );
}
