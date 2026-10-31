import { useEffect, useRef, useState } from "react";
import { LifeBuoy, Phone, Send } from "lucide-react";
import { api, type SessionState } from "../lib/api";
import { inr } from "../lib/format";
import { useLang } from "../lib/i18n";
import { Chips } from "./Chips";
import { PlanCard, RejectedCard } from "./Plan";

const DEMO = "I'm at Paytm's Marol office. I need to be at Connaught Place by lunch tomorrow, back on the 24th. Keep it cheap.";

export function TripView({ state, onOpenCheckout }: { state: SessionState; onOpenCheckout: () => void }) {
  const { t } = useLang();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const trip = state.trip;
  const proposals = trip?.plans.filter((p) => p.status !== "rejected") || [];
  const rejected = trip?.plans.filter((p) => p.status === "rejected") || [];
  const awaiting = trip?.cart?.status === "awaiting_approval";
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? state.messages : state.messages.slice(-2);
  const hidden = state.messages.length - visible.length;

  useEffect(() => { if (!trip?.plans.length) endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [state.messages.length]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run<T>(fn: () => Promise<T>) {
    setBusy(true); setError(null);
    try { return await fn(); } catch (e: any) { setError(e.message || "Something went wrong. Please retry."); } finally { setBusy(false); }
  }

  async function send(message: string) {
    if (!message.trim()) return;
    setText("");
    await run(() => api.chat(state.conversation_id, message));
  }

  return (
    <div className="grid gap-4">
      {/* conversation */}
      <section className="grid gap-2">
        {state.messages.length === 0 && (
          <button onClick={() => send(DEMO)} disabled={busy} className="card p-3 text-left text-sm text-slate-600 hover:border-sky-paytm border border-transparent">
            {t("tryDemo")}
          </button>
        )}
        {hidden > 0 && (
          <button onClick={() => setShowAll(true)} className="text-xs text-sky-paytm font-semibold w-fit mx-auto">Show {hidden} earlier message{hidden === 1 ? "" : "s"}</button>
        )}
        {visible.map((m, i) => (
          <div key={i} className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${m.role === "user" ? "ml-auto bg-sky-paytm text-white rounded-br-sm" : "bg-white shadow-card rounded-bl-sm"}`}>
            {m.channel === "voice" && <span className={`flex items-center gap-1 text-[10px] font-semibold mb-0.5 ${m.role === "user" ? "text-white/80" : "text-sky-paytm"}`}><Phone size={10} />{t("viaPhone")}</span>}
            {m.text}
          </div>
        ))}
        {busy && <div className="bg-white shadow-card rounded-2xl rounded-bl-sm px-3 py-2 text-sm text-slate-500 w-fit animate-pulse">{t("thinking")}</div>}
        {error && <p className="text-sm text-red-600" role="alert">{error}</p>}
        <div ref={endRef} />
      </section>


      <Chips chips={state.assumptions} busy={busy} onEdit={async (o) => { await run(() => api.editAssumptions(state.conversation_id, o)); }} />

      {awaiting && (
        <button onClick={onOpenCheckout} className="card p-3 flex justify-between items-center border-2 border-amber-300 bg-amber-50">
          <span className="text-sm font-bold text-amber-800">{t("awaiting")}</span>
          <span className="font-extrabold tabular-nums">{inr(trip!.cart!.total)}</span>
        </button>
      )}

      {proposals.length > 0 && (
        <section className="grid gap-3">
          <p className="text-sm font-bold">{t("options")}</p>
          {proposals.map((p, i) => (
            <PlanCard key={p.id} plan={p} index={i + 1} busy={busy || trip?.trip.status === "booked"}
              selected={p.status === "selected" && !!awaiting}
              onChoose={() => run(async () => { await api.selectPlan(p.id); onOpenCheckout(); })} />
          ))}
          {rejected.map((p) => <RejectedCard key={p.id} plan={p} />)}
        </section>
      )}

      {trip && (
        <button className="text-xs text-slate-500 flex items-center gap-1 justify-center py-2" disabled={busy}
          onClick={() => run(async () => { const c = await api.supportCase("Traveller asked for a person from the app", trip.trip.id, state.conversation_id); setNotice(`${t("caseOpened")}: ${c.case_no}`); })}>
          <LifeBuoy size={14} /> {t("needHelp")}
        </button>
      )}
      {notice && <p className="text-xs text-center text-emerald-700">{notice}</p>}

      <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2 sticky bottom-0 bg-surface/95 backdrop-blur py-2 -mx-1 px-1">
        <label htmlFor="chat-input" className="sr-only">{t("typeHere")}</label>
        <input id="chat-input" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("typeHere")}
          className="flex-1 rounded-full border border-slate-200 px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-sky-paytm" />
        <button disabled={busy || !text.trim()} className="w-11 h-11 rounded-full bg-sky-paytm text-white flex items-center justify-center disabled:opacity-50" aria-label="Send">
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
