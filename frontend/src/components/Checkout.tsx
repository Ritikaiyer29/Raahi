import { useMemo, useRef, useState } from "react";
import { ShieldCheck, X } from "lucide-react";
import { api, type Addon, type TripSnapshot } from "../lib/api";
import { inr } from "../lib/format";
import { useLang } from "../lib/i18n";

/** One cart, one simulated UPI approval. Never asks for a PIN, OTP or card. The idempotency key is fixed per cart,
 *  so a double tap or a retry can never book twice. */
export function CheckoutSheet({ trip, addons, onClose, onBooked }: {
  trip: TripSnapshot; addons: Addon[]; onClose: () => void; onBooked: () => void;
}) {
  const { t } = useLang();
  const cart = trip.cart!;
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const keyRef = useRef(`approve-${cart.id}-${Math.random().toString(36).slice(2, 10)}`);
  const selectedAddons = useMemo(() => new Set(cart.items.filter((i) => i.kind === "addon").map((i) => i.ref_id)), [cart.items]);
  const legs = cart.items.filter((i) => i.kind === "leg");

  async function toggle(code: string) {
    const next = new Set(selectedAddons);
    next.has(code) ? next.delete(code) : next.add(code);
    setBusy(true); setError(null);
    try { await api.setAddons(cart.id, [...next]); } catch (e: any) { setError(e.message); } finally { setBusy(false); }
  }

  async function approve(acceptNew = false) {
    setBusy(true); setError(null);
    try {
      const r = await api.approve(cart.id, keyRef.current + (acceptNew ? "-new" : ""), acceptNew);
      if (r.status === "ask") setAsk(r.say_en);
      else if (r.status === "booked") onBooked();
    } catch (e: any) {
      setError(e.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="absolute inset-0 z-30 bg-navy/40 flex items-end" role="dialog" aria-modal="true" aria-label={t("approveTitle")}>
      <div className="w-full bg-white rounded-t-3xl p-5 grid gap-4 max-h-[88%] overflow-y-auto shadow-2xl">
        <div className="flex justify-between items-start">
          <div>
            <p className="text-[11px] font-bold uppercase text-sky-paytm">Paytm · {t("approveTitle")}</p>
            <p className="text-lg font-extrabold">{inr(cart.total)}</p>
          </div>
          <button onClick={onClose} aria-label="Close" className="p-1"><X size={20} /></button>
        </div>

        <ul className="grid gap-2 text-sm">
          {legs.map((i) => (
            <li key={i.ref_id} className="flex justify-between gap-3">
              <span className="text-slate-600 min-w-0">{i.label}</span><span className="tabular-nums font-semibold shrink-0">{inr(i.price)}</span>
            </li>
          ))}
        </ul>

        <div className="grid gap-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{t("addons")}</p>
          {addons.map((a) => {
            const on = selectedAddons.has(a.code);
            return (
              <label key={a.code} htmlFor={`addon-${a.code}`} className={`flex gap-3 items-start rounded-xl border p-3 cursor-pointer ${on ? "border-sky-paytm bg-sky-50" : "border-slate-200"}`}>
                <input id={`addon-${a.code}`} type="checkbox" checked={on} disabled={busy} onChange={() => toggle(a.code)} className="mt-1 accent-[#00BAF2]" />
                <span className="flex-1">
                  <span className="flex justify-between text-sm font-semibold"><span>{a.name}</span><span className="tabular-nums">{inr(a.price)}</span></span>
                  <span className="block text-xs text-slate-500">{a.description}</span>
                </span>
              </label>
            );
          })}
        </div>

        {ask && (
          <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-sm grid gap-2">
            <p className="font-bold text-amber-800">{t("priceChanged")}</p>
            <p className="text-amber-900">{ask}</p>
            <div className="flex gap-2">
              <button className="flex-1 rounded-full bg-amber-500 text-white py-2 font-semibold" onClick={() => approve(true)} disabled={busy}>{t("acceptNew")}</button>
              <button className="flex-1 rounded-full border py-2" onClick={() => { setAsk(null); onClose(); }}>{t("cancel")}</button>
            </div>
          </div>
        )}
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}

        {!ask && (
          <button onClick={() => approve()} disabled={busy}
            className="rounded-full bg-navy text-white py-4 text-base font-bold flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-60">
            <ShieldCheck size={18} /> {busy ? t("approving") : `${t("approve")} ${inr(cart.total)} (demo)`}
          </button>
        )}
        <p className="text-[11px] text-center text-slate-400">{t("demoApproval")}</p>
      </div>
    </div>
  );
}
