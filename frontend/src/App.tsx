import { useEffect, useState } from "react";
import { Mic, Plane, TrainFront, Bus, TramFront, Hotel, ShieldCheck, Ticket, Briefcase, Search } from "lucide-react";

const services = [
  { label: "Flights", icon: Plane },
  { label: "Trains", icon: TrainFront },
  { label: "Bus", icon: Bus },
  { label: "Metro", icon: TramFront },
  { label: "Hotels", icon: Hotel },
  { label: "Insurance", icon: ShieldCheck },
  { label: "Travel Pass", icon: Ticket },
  { label: "My Trips", icon: Briefcase },
];

export default function App() {
  const [health, setHealth] = useState<string>("checking…");
  useEffect(() => {
    fetch("/healthz").then((r) => r.json()).then((j) => setHealth(j.status)).catch(() => setHealth("offline"));
  }, []);

  return (
    <div className="min-h-screen flex justify-center bg-surface">
      <div className="w-full max-w-[420px] bg-white min-h-screen flex flex-col shadow-card">
        <header className="bg-sky-paytm px-5 pt-6 pb-16 text-white">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-extrabold tracking-tight">Raahi <span className="font-normal">राही</span></h1>
              <p className="text-xs opacity-90">for Paytm · Build for India prototype</p>
            </div>
            <span className="text-[10px] bg-white/20 rounded-full px-2 py-1">Demo data · no real bookings</span>
          </div>
          <div className="mt-4 flex items-center gap-2 bg-white rounded-full px-4 py-3 text-slate-400 text-sm">
            <Search size={16} /> Search flights, trains, metro…
          </div>
        </header>

        <main className="px-4 -mt-10 flex-1">
          <section className="card p-4 overflow-hidden">
            <p className="text-xs font-semibold text-sky-paytm uppercase">Plan with Raahi</p>
            <p className="text-lg font-bold mt-1">Bolo, kahaan jaana hai?</p>
            <p className="text-sm text-slate-500">One sentence. One payment. Door to door.</p>
            <button className="mt-3 flex items-center gap-2 bg-navy text-white rounded-full px-4 py-2 text-sm font-semibold">
              <Mic size={16} /> Tap to speak
            </button>
            <img src="/brand/skyline.png" alt="Indian landmarks skyline" className="mt-4 -mx-4 w-[calc(100%+2rem)] max-w-none" />
          </section>

          <section className="grid grid-cols-4 gap-3 mt-5">
            {services.map(({ label, icon: Icon }) => (
              <button key={label} className="flex flex-col items-center gap-1 text-[11px] font-medium">
                <span className="w-14 h-14 rounded-2xl bg-white shadow-card flex items-center justify-center text-sky-paytm">
                  <Icon size={24} />
                </span>
                {label}
              </button>
            ))}
          </section>
        </main>

        <footer className="p-4 text-center text-[11px] text-slate-400">
          The model plans. Code checks. You pay once. A human handles exceptions. · API: {health}
        </footer>
      </div>
    </div>
  );
}
