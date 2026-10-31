import { useState } from "react";
import { AlertTriangle, BedDouble, Check, ChevronDown, Footprints, Plane, Sparkles, TramFront, TrainFront, Bus } from "lucide-react";
import type { Leg, Plan } from "../lib/api";
import { dayLabel, hhmm, inr, minutesLabel } from "../lib/format";
import { useLang } from "../lib/i18n";

const MODE_ICON: Record<string, any> = { walk: Footprints, metro: TramFront, flight: Plane, hotel: BedDouble, train: TrainFront, bus: Bus };

function legTitle(l: Leg) {
  const d = l.details || {};
  switch (l.mode) {
    case "walk": return `Walk ${d.minutes} min to ${l.to_label}`;
    case "metro": return `${d.line_name}: ${l.from_label} → ${l.to_label}`;
    case "flight": return `${d.airline} ${d.flight_no}: ${l.from_label} → ${l.to_label}`;
    case "train": return `${d.train_name} ${d.train_no} · ${d.travel_class}`;
    case "hotel": return `${d.hotel}, ${d.nights} night${d.nights === 1 ? "" : "s"}`;
    default: return `${l.from_label} → ${l.to_label}`;
  }
}

function legSub(l: Leg) {
  const d = l.details || {};
  if (l.mode === "hotel") return `Check-in ${d.check_in_time} · ${d.area} · ${d.partner}`;
  if (l.mode === "flight") return `${hhmm(l.start)} → ${hhmm(l.end)} · ${d.baggage}`;
  if (l.mode === "train") {
    const nextDay = l.end.slice(0, 10) !== l.start.slice(0, 10) ? " (+1 day)" : "";
    return `${l.from_label} ${hhmm(l.start)} → ${l.to_label} ${hhmm(l.end)}${nextDay} · ${d.availability}`;
  }
  if (l.mode === "metro") return `${hhmm(l.start)} → ${hhmm(l.end)} · ${d.stops} stop${d.stops === 1 ? "" : "s"} · QR ticket`;
  return `${hhmm(l.start)} → ${hhmm(l.end)}`;
}

export function LegRow({ leg, last }: { leg: Leg; last: boolean }) {
  const Icon = MODE_ICON[leg.mode] || Footprints;
  const tone = leg.mode === "flight" || leg.mode === "train" ? "bg-navy text-white" : leg.mode === "hotel" ? "bg-amber-100 text-amber-800" : "bg-sky-50 text-sky-paytm";
  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center">
        <span className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${tone}`}><Icon size={16} /></span>
        {!last && <span className="flex-1 w-px bg-slate-200 my-1" />}
      </div>
      <div className="flex-1 pb-3 min-w-0">
        <div className="flex justify-between gap-2">
          <p className="text-sm font-semibold leading-snug">{legTitle(leg)}</p>
          {leg.price > 0 && <span className="text-sm font-semibold tabular-nums shrink-0">{inr(leg.price)}</span>}
        </div>
        <p className="text-xs text-slate-500">{legSub(leg)}</p>
      </div>
    </li>
  );
}

export function Timeline({ legs }: { legs: Leg[] }) {
  const { t } = useLang();
  const groups = [
    { key: "outbound", label: t("outbound"), legs: legs.filter((l) => l.direction === "outbound") },
    { key: "return", label: t("returnLeg"), legs: legs.filter((l) => l.direction === "return") },
  ].filter((g) => g.legs.length);
  return (
    <div className="grid gap-2">
      {groups.map((g) => (
        <div key={g.key}>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400 mb-2">
            {g.label} · {dayLabel(g.legs[0].start)}
          </p>
          <ol>{g.legs.map((l, i) => <LegRow key={l.id} leg={l} last={i === g.legs.length - 1} />)}</ol>
        </div>
      ))}
    </div>
  );
}

function arrival(plan: Plan) {
  const dest = plan.legs.find((l) => l.details?.is_destination);
  const start = plan.legs[0]?.start;
  if (!dest) return "";
  return start && dest.end.slice(0, 10) !== start.slice(0, 10) ? `${dayLabel(dest.end)} ${hhmm(dest.end)}` : hhmm(dest.end);
}

/** The long-distance leg: a flight or a train. */
function mainOf(plan: Plan) {
  return plan.legs.find((l) => (l.mode === "flight" || l.mode === "train") && l.direction === "outbound");
}

function mainTitle(l: Leg | undefined) {
  if (!l) return "Option";
  // Overnight trains leave on different days for the same arrival, so their cards carry the day.
  return l.mode === "flight" ? `${hhmm(l.start)} ${l.details.airline} · ${l.details.flight_no}`
    : `${dayLabel(l.start)} ${hhmm(l.start)} · ${l.details.train_name.replace(" (demo)", "")} · ${l.details.travel_class}`;
}

export function PlanCard({ plan, index, onChoose, busy, selected }: {
  plan: Plan; index: number; onChoose: () => void; busy: boolean; selected: boolean;
}) {
  const { t, lang } = useLang();
  const [open, setOpen] = useState(plan.is_pick);
  const [showChecks, setShowChecks] = useState(false);
  const passed = plan.checks.filter((c) => c.passed);
  const f = mainOf(plan);
  return (
    <article className={`card p-4 grid gap-3 border-2 ${plan.is_pick ? "border-sky-paytm" : "border-transparent"}`}>
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {plan.is_pick ? (
            <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase text-sky-paytm"><Sparkles size={12} />{t("pick")}</span>
          ) : (
            <span className="text-[11px] font-bold uppercase text-slate-400">{t("option")} {index}</span>
          )}
          <p className="font-bold leading-snug">{f ? mainTitle(f) : plan.explanation_en}</p>
          <p className="text-xs text-slate-500">
            {minutesLabel(plan.total_duration)} {t("doorToDoor")} · arrive {arrival(plan)}
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xl font-extrabold tabular-nums">{inr(plan.total_price)}</p>
          <p className="text-[11px] text-slate-400">{t("total")}</p>
        </div>
      </header>
      {plan.is_pick && <p className="text-xs text-slate-600 bg-surface rounded-lg p-2">{lang === "hi" ? plan.explanation_hi : plan.explanation_en}</p>}
      <button onClick={() => setShowChecks((v) => !v)} className="flex items-center gap-1 text-xs font-semibold text-emerald-700 w-fit">
        <Check size={14} /> {passed.length}/{plan.checks.length} {t("checksPassed")}
        <ChevronDown size={14} className={showChecks ? "rotate-180 transition" : "transition"} />
      </button>
      {showChecks && (
        <ul className="grid gap-1 text-xs text-slate-600">
          {plan.checks.map((c) => (
            <li key={c.rule_id} className="flex gap-2">
              <span className={c.passed ? "text-emerald-600" : "text-amber-600"}>{c.passed ? "✓" : "!"}</span>
              <span><b className="font-mono text-[10px] text-slate-400 mr-1">{c.rule_id}</b>{lang === "hi" ? c.message_hi : c.message_en}</span>
            </li>
          ))}
        </ul>
      )}
      <button onClick={() => setOpen((v) => !v)} className="flex items-center justify-between text-sm font-semibold text-navy">
        Door-to-door timeline <ChevronDown size={16} className={open ? "rotate-180 transition" : "transition"} />
      </button>
      {open && <Timeline legs={plan.legs} />}
      <button
        onClick={onChoose}
        disabled={busy || selected}
        className={`rounded-full py-3 text-sm font-bold transition ${selected ? "bg-emerald-50 text-emerald-700" : "bg-sky-paytm text-white active:scale-[0.98]"} disabled:opacity-70`}
      >
        {selected ? "Selected · awaiting approval" : t("choose")}
      </button>
    </article>
  );
}

export function RejectedCard({ plan }: { plan: Plan }) {
  const { t, lang } = useLang();
  const reason = plan.checks.find((c) => !c.passed && c.severity === "block");
  const f = mainOf(plan);
  return (
    <article className="rounded-card border-2 border-dashed border-red-200 bg-red-50/60 p-4 grid gap-2">
      <p className="flex items-center gap-1 text-[11px] font-bold uppercase text-red-600"><AlertTriangle size={12} />{t("rejected")}</p>
      <div className="flex justify-between gap-2">
        <p className="font-bold line-through decoration-red-300">{mainTitle(f)}</p>
        <p className="font-bold tabular-nums text-slate-500 line-through decoration-red-300">{inr(plan.total_price)}</p>
      </div>
      {reason && (
        <p className="text-sm text-red-800">
          {lang === "hi" ? reason.message_hi : reason.message_en}
          <span className="block font-mono text-[10px] text-red-400 mt-1">rule: {reason.rule_id}</span>
        </p>
      )}
    </article>
  );
}
