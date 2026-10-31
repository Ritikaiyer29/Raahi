import { Briefcase, Bus, CalendarHeart, Hotel, MessageSquare, Phone, Plane, Route, Search, ShieldCheck, Ticket, TrainFront, TramFront } from "lucide-react";
import { RAAHI_NUMBER, RAAHI_TEL } from "../lib/format";
import { useLang } from "../lib/i18n";

export const SERVICES = [
  { key: "flights", label: "Flights", icon: Plane },
  { key: "trains", label: "Trains", icon: TrainFront },
  { key: "buses", label: "Bus", icon: Bus },
  { key: "metro", label: "Metro", icon: TramFront },
  { key: "hotels", label: "Hotels", icon: Hotel },
  { key: "addons", label: "Insurance", icon: ShieldCheck },
  { key: "addons", label: "Travel Pass", icon: Ticket },
  { key: "trips", label: "My Trips", icon: Briefcase },
  { key: "commute", label: "My Commute", icon: Route, soon: true },
  { key: "day", label: "Plan my day", icon: CalendarHeart, soon: true },
];

export function Home({ code, onStartChat, onService }: { code?: string; onStartChat: () => void; onService: (k: string, label: string) => void }) {
  const { t } = useLang();
  return (
    <div className="grid gap-5">
      <div className="flex items-center gap-2 bg-white rounded-full px-4 py-3 text-slate-400 text-sm shadow-card">
        <Search size={16} /> Search flights, trains, metro…
      </div>

      <section className="card overflow-hidden">
        <div className="p-4 grid gap-3">
          <div>
            <p className="text-[11px] font-bold uppercase text-sky-paytm">{t("planWithRaahi")}</p>
            <p className="text-xl font-extrabold">{t("bolo")}</p>
            <p className="text-sm text-slate-500">{t("oneSentence")}</p>
          </div>
          <div className="rounded-2xl bg-navy text-white p-3 flex items-center gap-3">
            <div className="flex-1">
              <p className="text-[11px] uppercase opacity-80">{t("yourCode")}</p>
              <p className="text-3xl font-black tracking-[0.3em] tabular-nums">{code || "····"}</p>
              <p className="text-[11px] opacity-80">{t("sayCode")}</p>
            </div>
            <a href={`tel:${RAAHI_TEL}`} className="flex flex-col items-center gap-1 bg-sky-paytm rounded-2xl px-3 py-2">
              <Phone size={20} /><span className="text-[11px] font-bold">{t("callRaahi")}</span>
            </a>
          </div>
          <p className="text-xs text-slate-500 text-center tabular-nums">{RAAHI_NUMBER}</p>
          <button onClick={onStartChat} className="rounded-full border-2 border-sky-paytm text-sky-paytm py-2.5 font-bold flex items-center justify-center gap-2">
            <MessageSquare size={16} /> {t("startChat")}
          </button>
        </div>
        <img src="/brand/skyline.png" alt="Illustrated skyline of Indian landmarks" className="w-full" />
      </section>

      <section className="grid gap-3">
        <p className="text-sm font-bold">{t("services")}</p>
        <div className="grid grid-cols-4 gap-3">
          {SERVICES.map(({ key, label, icon: Icon, soon }) => (
            <button key={label} onClick={() => !soon && onService(key, label)} disabled={soon}
              className="flex flex-col items-center gap-1 text-[11px] font-medium relative disabled:opacity-60">
              <span className="w-14 h-14 rounded-2xl bg-white shadow-card flex items-center justify-center text-sky-paytm"><Icon size={24} /></span>
              {label}
              {soon && <span className="absolute -top-1 right-0 text-[9px] bg-amber-100 text-amber-700 rounded-full px-1.5">{t("soon")}</span>}
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
