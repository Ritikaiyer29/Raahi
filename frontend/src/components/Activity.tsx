import type { AgentEvent } from "../lib/api";
import { useLang } from "../lib/i18n";

const COLOR: Record<string, string> = {
  Concierge: "bg-sky-500", Scouts: "bg-indigo-500", Planner: "bg-violet-500", Checker: "bg-emerald-600",
  Checkout: "bg-amber-500", Handoff: "bg-rose-500", Guardian: "bg-orange-500",
};

function actionLabel(a: string) {
  return a.replace("voice_tool:", "📞 ").replaceAll("_", " ");
}

export function ActivityPanel({ events, connection }: { events: AgentEvent[]; connection: string }) {
  const { t } = useLang();
  const shown = [...events].reverse();
  return (
    <section className="grid gap-3 content-start">
      <header className="flex items-center justify-between">
        <h2 className="font-bold">{t("agentActivity")}</h2>
        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${connection === "live" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
          ● {connection === "live" ? t("live") : connection}
        </span>
      </header>
      {!shown.length && <p className="text-sm text-slate-500">{t("noActivity")}</p>}
      <ol className="grid gap-2">
        {shown.map((e) => (
          <li key={e.seq} className="card p-3 grid gap-1 animate-[fadein_.3s_ease-out]">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${COLOR[e.agent] || "bg-slate-400"}`} />
              <span className="text-sm font-bold">{e.agent}</span>
              <span className="text-xs text-slate-500 truncate">{actionLabel(e.action)}</span>
              <span className="ml-auto text-[10px] tabular-nums text-slate-400">{e.at}</span>
            </div>
            {e.output && <p className="text-xs text-slate-600">{e.output}</p>}
            <div className="flex gap-2">
              <span className={`text-[10px] font-semibold px-1.5 rounded ${e.status === "ok" ? "bg-emerald-50 text-emerald-700" : e.status === "timeout" ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700"}`}>{e.status}</span>
              <span className="text-[10px] tabular-nums text-slate-400">{e.duration_ms} ms</span>
            </div>
          </li>
        ))}
      </ol>
      <p className="text-[11px] text-slate-400">{t("builtNote")}</p>
    </section>
  );
}
