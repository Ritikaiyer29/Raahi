const inrFmt = new Intl.NumberFormat("en-IN");

/** ₹6,840 · ₹1,24,500 (Indian digit grouping). */
export const inr = (n: number) => `₹${inrFmt.format(Math.round(n))}`;

export const hhmm = (iso: string | null) => (iso ? iso.slice(11, 16) : "");

export const dayLabel = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso.slice(0, 10) + "T00:00:00");
  return d.toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" });
};

export const minutesLabel = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`);

export const RAAHI_NUMBER = "+91 80642 69831";
export const RAAHI_TEL = "+918064269831";
