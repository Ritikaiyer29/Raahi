import { useState } from "react";
import { CalendarDays, Clock, Gauge, MapPin, Minus, Plus, Users, X } from "lucide-react";
import type { Chip } from "../lib/api";
import { useLang } from "../lib/i18n";

// Only these slots change the plan today; the others (cabin, baggage) are shown so every default is visible.
const EDITABLE = new Set(["depart_date", "return_date", "party_size", "priority", "arrive_by"]);
const ICON: Record<string, any> = { origin: MapPin, depart_date: CalendarDays, return_date: CalendarDays, party_size: Users, priority: Gauge, arrive_by: Clock };

export function Chips({ chips, onEdit, busy }: { chips: Chip[]; onEdit: (o: Record<string, any>) => Promise<void>; busy: boolean }) {
  const { t, lang } = useLang();
  const [editing, setEditing] = useState<Chip | null>(null);
  if (!chips.length) return null;
  return (
    <section className="grid gap-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{t("assumptions")}</p>
      <div className="flex flex-wrap gap-2">
        {chips.map((c) => {
          const Icon = ICON[c.slot];
          const can = EDITABLE.has(c.slot);
          return (
            <button
              key={c.slot}
              disabled={!can || busy}
              onClick={() => setEditing(c)}
              className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-xs font-medium border transition
                ${c.assumed ? "border-dashed border-sky-paytm text-navy bg-sky-50" : "border-slate-200 bg-white text-navy"}
                ${can ? "hover:border-sky-paytm active:scale-95" : "opacity-70 cursor-default"}`}
              title={c.assumed ? "Assumed by Raahi" : "From what you said"}
            >
              {Icon && <Icon size={12} />}{lang === "hi" ? c.label_hi : c.label_en}
            </button>
          );
        })}
      </div>
      {editing && (
        <ChipEditor chip={editing} onClose={() => setEditing(null)} onApply={async (o) => { setEditing(null); await onEdit(o); }} />
      )}
    </section>
  );
}

function ChipEditor({ chip, onClose, onApply }: { chip: Chip; onClose: () => void; onApply: (o: Record<string, any>) => void }) {
  const { t } = useLang();
  const [value, setValue] = useState<any>(chip.value);
  return (
    <div className="card p-3 grid gap-3 border border-sky-100">
      <div className="flex justify-between items-center">
        <p className="text-sm font-bold">{t("change")}</p>
        <button onClick={onClose} aria-label="Close"><X size={16} /></button>
      </div>
      {chip.slot === "priority" && (
        <div className="grid grid-cols-3 gap-2">
          {(["economical", "fastest", "comfort"] as const).map((p) => (
            <button key={p} onClick={() => onApply({ priority: p })}
              className={`rounded-xl py-2 text-xs font-semibold border ${chip.value === p ? "border-sky-paytm bg-sky-50" : "border-slate-200"}`}>
              {t(p === "economical" ? "cheapest" : p)}
            </button>
          ))}
        </div>
      )}
      {chip.slot === "party_size" && (
        <div className="flex items-center justify-between">
          <span className="text-sm">{t("travellers")}</span>
          <div className="flex items-center gap-3">
            <button className="w-8 h-8 rounded-full border" onClick={() => setValue(Math.max(1, value - 1))} aria-label="Fewer"><Minus size={14} className="mx-auto" /></button>
            <span className="font-bold tabular-nums w-4 text-center">{value}</span>
            <button className="w-8 h-8 rounded-full border" onClick={() => setValue(Math.min(9, value + 1))} aria-label="More"><Plus size={14} className="mx-auto" /></button>
          </div>
        </div>
      )}
      {(chip.slot === "depart_date" || chip.slot === "return_date") && (
        <label className="grid gap-1 text-sm" htmlFor={`chip-${chip.slot}`}>
          {t(chip.slot === "depart_date" ? "departDate" : "returnDate")}
          <input id={`chip-${chip.slot}`} type="date" className="border rounded-lg px-3 py-2" value={value || ""} onChange={(e) => setValue(e.target.value || null)} />
          {chip.slot === "return_date" && (
            <button className="text-xs text-sky-paytm font-semibold text-left" onClick={() => onApply({ return_date: null })}>{t("oneWay")}</button>
          )}
        </label>
      )}
      {chip.slot === "arrive_by" && (
        <label className="grid gap-1 text-sm" htmlFor="chip-arrive">
          {t("arriveBy")}
          <input id="chip-arrive" type="time" className="border rounded-lg px-3 py-2" value={value || "13:00"} onChange={(e) => setValue(e.target.value)} />
        </label>
      )}
      {chip.slot !== "priority" && (
        <button className="rounded-full bg-navy text-white py-2 text-sm font-semibold" onClick={() => onApply({ [chip.slot]: value })}>{t("apply")}</button>
      )}
    </div>
  );
}
