import { useEffect, useRef, useState } from "react";
import { Activity, ArrowLeft, Home as HomeIcon, Languages, Map, RotateCcw, Wallet as WalletIcon } from "lucide-react";
import { ActivityPanel } from "./components/Activity";
import { CheckoutSheet } from "./components/Checkout";
import { Home } from "./components/Home";
import { ServiceList } from "./components/Services";
import { TripView } from "./components/TripView";
import { Wallet } from "./components/Wallet";
import { useLang } from "./lib/i18n";
import { useSession } from "./lib/useSession";

type View = { name: "home" } | { name: "trip" } | { name: "wallet" } | { name: "activity" } | { name: "service"; kind: string; label: string };

export default function App() {
  const { t, lang, setLang } = useLang();
  const { state, connection, newTrip } = useSession();
  // #trip, #wallet and #activity open those screens directly (handy on the projector).
  const [view, setView] = useState<View>(() => {
    const h = window.location.hash.slice(1);
    return h === "trip" || h === "wallet" || h === "activity" ? ({ name: h } as View) : { name: "home" };
  });
  const [checkoutOpen, setCheckoutOpen] = useState(false);
  const seenCart = useRef<string | null>(null);
  const seenPlans = useRef<number>(0);
  const seenBooking = useRef<string | null>(null);

  const trip = state?.trip || null;

  // Realtime reactions: whatever the phone agent does shows up on screen without a tap.
  useEffect(() => {
    if (!state) return;
    const planCount = trip?.plans.length || 0;
    if (planCount && planCount !== seenPlans.current && view.name === "home") setView({ name: "trip" });
    seenPlans.current = planCount;
    const cart = trip?.cart;
    if (cart?.status === "awaiting_approval" && cart.id !== seenCart.current) {
      seenCart.current = cart.id;
      setCheckoutOpen(true);
      setView({ name: "trip" });
    }
    if (trip?.booking?.status === "confirmed" && trip.booking.id !== seenBooking.current) {
      if (seenBooking.current !== null || view.name !== "wallet") setView({ name: "wallet" });
      seenBooking.current = trip.booking.id;
      setCheckoutOpen(false);
    }
    if (state.messages.length && view.name === "home" && !planCount) setView({ name: "trip" });
  }, [state?.version]); // eslint-disable-line react-hooks/exhaustive-deps

  const nav = [
    { name: "home" as const, label: t("home"), icon: HomeIcon },
    { name: "trip" as const, label: t("trip"), icon: Map },
    { name: "wallet" as const, label: t("wallet"), icon: WalletIcon },
    { name: "activity" as const, label: t("activity"), icon: Activity, mobileOnly: true },
  ];

  return (
    <div className="min-h-screen bg-[#e9eef5] lg:py-6">
      <div className="mx-auto flex justify-center gap-6 lg:items-start">
        {/* phone frame */}
        <div className="relative w-full max-w-[420px] bg-surface min-h-screen lg:min-h-0 lg:h-[860px] lg:rounded-[2.5rem] lg:border-[10px] lg:border-navy lg:shadow-2xl flex flex-col overflow-hidden">
          <header className="bg-sky-paytm text-white px-4 pt-4 pb-3 shrink-0">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                {view.name === "service" && (
                  <button onClick={() => setView({ name: "home" })} aria-label="Back"><ArrowLeft size={20} /></button>
                )}
                <div className="min-w-0">
                  <h1 className="text-xl font-extrabold tracking-tight leading-none">Raahi <span className="font-normal">राही</span></h1>
                  <p className="text-[10px] opacity-90 truncate">{t("tagline")}</p>
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {state && <span className="text-[11px] font-bold bg-white/20 rounded-full px-2 py-1 tabular-nums">#{state.session_code}</span>}
                <button onClick={() => setLang(lang === "en" ? "hi" : "en")} className="text-[11px] font-bold bg-white/20 rounded-full px-2 py-1 flex items-center gap-1" aria-label="Switch language">
                  <Languages size={12} />{lang === "en" ? "हिंदी" : "EN"}
                </button>
                <button onClick={() => { newTrip(); setView({ name: "home" }); seenCart.current = null; seenBooking.current = null; }}
                  className="text-[11px] font-bold bg-white/20 rounded-full px-2 py-1 flex items-center gap-1" aria-label={t("newTrip")}>
                  <RotateCcw size={12} />
                </button>
              </div>
            </div>
            <p className="text-[10px] mt-2 inline-block bg-white/20 rounded-full px-2 py-0.5">{t("demoBadge")}</p>
          </header>

          <main className="flex-1 overflow-y-auto px-4 py-4">
            {!state && <div className="grid gap-3">{[0, 1, 2].map((i) => <div key={i} className="card h-24 animate-pulse" />)}</div>}
            {state && view.name === "home" && (
              <Home code={state.session_code} onStartChat={() => setView({ name: "trip" })}
                onService={(kind, label) => (kind === "trips" ? setView(trip?.tickets.length ? { name: "wallet" } : { name: "trip" }) : setView({ name: "service", kind, label }))} />
            )}
            {state && view.name === "trip" && <TripView state={state} onOpenCheckout={() => setCheckoutOpen(true)} />}
            {state && view.name === "wallet" && (<><h2 className="font-bold mb-3">{t("walletTitle")}</h2><Wallet trip={trip} /></>)}
            {state && view.name === "activity" && <ActivityPanel events={state.agent_events} connection={connection} />}
            {view.name === "service" && <ServiceList kind={view.kind} label={view.label} />}
          </main>

          <nav className="shrink-0 bg-white border-t border-slate-200 grid grid-cols-4 lg:grid-cols-3">
            {nav.map(({ name, label, icon: Icon, mobileOnly }) => (
              <button key={name} onClick={() => setView({ name } as View)}
                className={`py-2 flex flex-col items-center gap-0.5 text-[11px] ${mobileOnly ? "lg:hidden" : ""} ${view.name === name ? "text-sky-paytm font-bold" : "text-slate-500"}`}>
                <Icon size={18} />{label}
              </button>
            ))}
          </nav>

          {checkoutOpen && trip?.cart?.status === "awaiting_approval" && state && (
            <CheckoutSheet trip={trip} addons={state.addons} onClose={() => setCheckoutOpen(false)}
              onBooked={() => { setCheckoutOpen(false); setView({ name: "wallet" }); }} />
          )}
        </div>

        {/* desktop: agent activity beside the phone, for the projector */}
        <aside className="hidden lg:block w-[380px] h-[860px] overflow-y-auto bg-white/70 rounded-3xl p-5">
          {state && <ActivityPanel events={state.agent_events} connection={connection} />}
        </aside>
      </div>
    </div>
  );
}
