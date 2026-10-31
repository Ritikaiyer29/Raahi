import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { BedDouble, ChevronDown, Plane, ShieldCheck, TramFront } from "lucide-react";
import type { Ticket, TripSnapshot } from "../lib/api";
import { dayLabel, hhmm, inr } from "../lib/format";
import { useLang } from "../lib/i18n";
import { Timeline } from "./Plan";

const ICON: Record<string, any> = { flight: Plane, metro_qr: TramFront, hotel: BedDouble, addon: ShieldCheck };
const KIND: Record<string, string> = { flight: "Flight", metro_qr: "Metro QR", hotel: "Hotel voucher", addon: "Add-on" };

function Qr({ payload }: { payload: string }) {
  const { t } = useLang();
  const [src, setSrc] = useState<string>("");
  useEffect(() => { QRCode.toDataURL(payload, { margin: 1, width: 220 }).then(setSrc).catch(() => setSrc("")); }, [payload]);
  return (
    <div className="relative w-[220px] h-[220px] mx-auto">
      {src && <img src={src} alt="Demo ticket QR code" className="w-full h-full" />}
      <span className="absolute inset-0 flex items-center justify-center">
        <span className="rotate-[-24deg] bg-red-600/85 text-white text-[11px] font-black px-2 py-1 rounded">{t("notValid")}</span>
      </span>
    </div>
  );
}

function TicketCard({ ticket }: { ticket: Ticket }) {
  const [open, setOpen] = useState(false);
  const Icon = ICON[ticket.type] || ShieldCheck;
  return (
    <li className="card overflow-hidden">
      <button onClick={() => setOpen((v) => !v)} className="w-full p-3 flex gap-3 items-center text-left">
        <span className="w-10 h-10 rounded-xl bg-sky-50 text-sky-paytm flex items-center justify-center shrink-0"><Icon size={18} /></span>
        <span className="flex-1 min-w-0">
          <span className="block text-[11px] uppercase font-bold text-slate-400">{KIND[ticket.type] || ticket.type}{ticket.valid_from ? ` · ${dayLabel(ticket.valid_from)} ${hhmm(ticket.valid_from)}` : ""}</span>
          <span className="block text-sm font-semibold truncate">{ticket.title}</span>
          <span className="block font-mono text-xs text-slate-500">{ticket.ticket_no}</span>
        </span>
        <ChevronDown size={16} className={open ? "rotate-180 transition" : "transition"} />
      </button>
      {open && <div className="pb-4"><Qr payload={ticket.qr_payload} /></div>}
    </li>
  );
}

export function Wallet({ trip }: { trip: TripSnapshot | null }) {
  const { t } = useLang();
  if (!trip || !trip.tickets.length) {
    return <p className="text-sm text-slate-500 card p-6 text-center">{t("noTickets")}</p>;
  }
  const plan = trip.plans.find((p) => p.id === trip.trip.selected_plan_id);
  return (
    <div className="grid gap-4">
      <div className="card p-4 flex justify-between items-center">
        <div>
          <p className="text-[11px] font-bold uppercase text-emerald-600">{t("booked")} · {trip.tickets.length} tickets</p>
          <p className="font-bold">{trip.request?.origin} → {trip.request?.destination}</p>
        </div>
        <p className="text-lg font-extrabold tabular-nums">{inr(trip.cart?.total || 0)}</p>
      </div>
      <ul className="grid gap-2">{trip.tickets.map((tk) => <TicketCard key={tk.id} ticket={tk} />)}</ul>
      {plan && (
        <details className="card p-4">
          <summary className="text-sm font-semibold cursor-pointer">Trip timeline</summary>
          <div className="mt-3"><Timeline legs={plan.legs} /></div>
        </details>
      )}
    </div>
  );
}
