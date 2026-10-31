import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { dayLabel, hhmm, inr } from "../lib/format";

/** Paytm's existing catalogue (demo inventory) behind each tile, to show Raahi is built on it. */
export function ServiceList({ kind, label }: { kind: string; label: string }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setRows(null); setError(null);
    const q = kind === "metro" ? "?city=BOM" : "";
    api.inventory(kind, q).then(setRows).catch((e) => setError(e.message));
  }, [kind]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!rows) return <div className="grid gap-2">{[0, 1, 2].map((i) => <div key={i} className="card h-16 animate-pulse" />)}</div>;
  return (
    <div className="grid gap-2">
      <p className="text-xs text-slate-500">{label} · demo inventory, the same catalogue Raahi plans from</p>
      {kind === "flights" && rows.slice(0, 12).map((f) => (
        <div key={f.id} className="card p-3 flex justify-between text-sm">
          <span><b>{hhmm(f.dep)} → {hhmm(f.arr)}</b> · {f.airline} {f.flight_no}<span className="block text-xs text-slate-500">{dayLabel(f.dep)} · BOM {f.from_terminal} → DEL {f.to_terminal} · {f.seats_left} seats</span></span>
          <b className="tabular-nums">{inr(f.fare)}</b>
        </div>
      ))}
      {kind === "trains" && rows.slice(0, 6).map((tr) => (
        <div key={tr.id} className="card p-3 text-sm">
          <b>{tr.number} {tr.name}</b><span className="block text-xs text-slate-500">{dayLabel(tr.dep)} {hhmm(tr.dep)} · {tr.from_station} → {tr.to_station}</span>
          <div className="flex gap-2 mt-1 flex-wrap">{tr.classes.map((c: any) => (
            <span key={c.class} className={`text-[11px] rounded px-2 py-0.5 ${c.availability.startsWith("WL") ? "bg-amber-50 text-amber-700" : "bg-emerald-50 text-emerald-700"}`}>{c.class} {inr(c.fare)} · {c.availability}</span>
          ))}</div>
        </div>
      ))}
      {kind === "buses" && rows.slice(0, 6).map((b) => (
        <div key={b.id} className="card p-3 flex justify-between text-sm">
          <span><b>{b.operator}</b><span className="block text-xs text-slate-500">{dayLabel(b.dep)} {hhmm(b.dep)} · {b.from_city} → {b.to_city}{b.live_tracking ? " · live tracking" : ""}</span></span>
          <b className="tabular-nums">{inr(b.fare)}</b>
        </div>
      ))}
      {kind === "hotels" && rows.map((h) => (
        <div key={h.id} className="card p-3 flex justify-between text-sm">
          <span><b>{h.name}</b><span className="block text-xs text-slate-500">{h.area} · ★ {h.rating} · via {h.partner}</span></span>
          <b className="tabular-nums">{inr(h.price_per_night)}<span className="text-xs font-normal">/night</span></b>
        </div>
      ))}
      {kind === "metro" && rows.map((l) => (
        <div key={l.code} className="card p-3 text-sm">
          <b>{l.name}</b><span className="text-xs text-slate-500"> · first {l.first_train}, last {l.last_train} (demo hours)</span>
          <p className="text-xs text-slate-600 mt-1">{l.stations.map((s: any) => s.name + (s.terminal ? ` (${s.terminal})` : "")).join(" → ")}</p>
        </div>
      ))}
      {kind === "addons" && rows.map((a) => (
        <div key={a.code} className="card p-3 flex justify-between text-sm">
          <span><b>{a.name}</b><span className="block text-xs text-slate-500">{a.description}</span></span>
          <b className="tabular-nums">{inr(a.price)}</b>
        </div>
      ))}
    </div>
  );
}
