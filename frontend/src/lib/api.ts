// Types mirror app/api/session.py and app/snapshot.py.
export type Leg = {
  id: string; seq: number; direction: "outbound" | "return"; mode: string;
  from_label: string; to_label: string; start: string; end: string; price: number; details: Record<string, any>;
};
export type Check = { rule_id: string; passed: boolean; severity: "block" | "warn" | "info"; message_en: string; message_hi: string };
export type Plan = {
  id: string; rank: number; status: "proposed" | "rejected" | "selected"; is_pick: boolean; total_price: number;
  total_duration: number; explanation_en: string; explanation_hi: string; legs: Leg[]; checks: Check[];
};
export type CartItem = { kind: "leg" | "addon"; ref_id: string; label: string; price: number };
export type Ticket = { id: string; type: string; title: string; ticket_no: string; qr_payload: string; status: string; valid_from: string | null; valid_to: string | null };
export type TripSnapshot = {
  trip: { id: string; status: string; revision: number; selected_plan_id: string | null };
  request: Record<string, any> | null;
  plans: Plan[];
  cart: { id: string; status: string; total: number; plan_id: string; items: CartItem[] } | null;
  booking: { id: string; status: string; pnrs: Record<string, string> } | null;
  tickets: Ticket[];
  alerts: { id: string; cause: string; options: any[]; status: string }[];
};
export type Chip = { slot: string; value: any; label_en: string; label_hi: string; editable: boolean; assumed: boolean };
export type AgentEvent = { seq: number; agent: string; action: string; input: string; output: string; status: string; duration_ms: number; at: string | null };
export type Message = { role: "user" | "assistant"; text: string; channel: string; language: string | null };
export type Addon = { code: string; name: string; description: string; price: number };
export type SessionState = {
  conversation_id: string; session_code: string; version: string;
  messages: Message[]; slots: Record<string, any> | null; missing_slots: string[];
  assumptions: Chip[]; trip: TripSnapshot | null; agent_events: AgentEvent[]; addons: Addon[];
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = (body as any).detail;
    throw new Error(typeof d === "string" ? d : d?.message || `Request failed (${r.status})`);
  }
  return body as T;
}

export const api = {
  newSession: () => call<{ conversation_id: string; session_code: string }>("/api/sessions", { method: "POST" }),
  state: (conv: string) => call<SessionState>(`/api/conversations/${conv}/state`),
  chat: (conv: string, message: string) =>
    call<any>("/api/chat", { method: "POST", body: JSON.stringify({ message, conversation_id: conv }) }),
  editAssumptions: (conv: string, overrides: Record<string, any>) =>
    call<any>(`/api/conversations/${conv}/assumptions`, { method: "POST", body: JSON.stringify({ overrides }) }),
  selectPlan: (planId: string) => call<{ cart_id: string; total: number }>(`/api/plans/${planId}/select`, { method: "POST", body: "{}" }),
  setAddons: (cartId: string, codes: string[]) =>
    call<{ total: number }>(`/api/carts/${cartId}/addons`, { method: "POST", body: JSON.stringify({ codes }) }),
  approve: (cartId: string, key: string, acceptNewPrice = false) =>
    call<any>(`/api/carts/${cartId}/approve`, {
      method: "POST", headers: { "Idempotency-Key": key }, body: JSON.stringify({ accept_new_price: acceptNewPrice }),
    }),
  supportCase: (reason: string, trip_id?: string, conversation_id?: string) =>
    call<{ case_no: string }>("/api/support/cases", { method: "POST", body: JSON.stringify({ reason, trip_id, conversation_id }) }),
  inventory: (kind: string, query = "") => call<any[]>(`/api/inventory/${kind}${query}`),
};
