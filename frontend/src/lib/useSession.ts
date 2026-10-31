import { useCallback, useEffect, useRef, useState } from "react";
import { api, type SessionState } from "./api";

const KEY = "raahi.conversation";

/** Opens (or resumes) a Raahi session and follows it live: SSE first, polling every 2 s if the stream fails. */
export function useSession() {
  const [state, setState] = useState<SessionState | null>(null);
  const [convId, setConvId] = useState<string | null>(() => {
    try { return localStorage.getItem(KEY); } catch { return null; }
  });
  const [connection, setConnection] = useState<"connecting" | "live" | "polling" | "offline">("connecting");
  const versionRef = useRef<string | null>(null);

  const accept = useCallback((s: SessionState) => {
    if (s.version !== versionRef.current) {
      versionRef.current = s.version;
      setState(s);
    }
  }, []);

  const start = useCallback(async () => {
    const s = await api.newSession();
    try { localStorage.setItem(KEY, s.conversation_id); } catch { /* ignore */ }
    versionRef.current = null;
    setState(null);
    setConvId(s.conversation_id);
  }, []);

  // ?session=4821 opens a session started elsewhere (e.g. by a phone call) on this screen.
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("session");
    if (!code) return;
    fetch(`/api/sessions/${encodeURIComponent(code)}`).then((r) => (r.ok ? r.json() : null)).then((s) => {
      if (!s) return;
      try { localStorage.setItem(KEY, s.conversation_id); } catch { /* ignore */ }
      versionRef.current = null;
      setConvId(s.conversation_id);
      window.history.replaceState(null, "", window.location.pathname);
    }).catch(() => {});
  }, []);

  // Create a session on first visit, or replace one the server no longer knows (e.g. after a demo reset).
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("session")) return; // handled above
    if (!convId) { start().catch(() => setConnection("offline")); return; }
    api.state(convId).then(accept).catch(() => start().catch(() => setConnection("offline")));
  }, [convId, start, accept]);

  useEffect(() => {
    if (!convId) return;
    let es: EventSource | null = null;
    let poll: number | null = null;
    let closed = false;

    const startPolling = () => {
      if (poll || closed) return;
      setConnection("polling");
      poll = window.setInterval(() => {
        api.state(convId).then((s) => { accept(s); setConnection("polling"); }).catch(() => setConnection("offline"));
      }, 2000);
    };

    try {
      es = new EventSource(`/api/conversations/${convId}/stream`);
      es.addEventListener("state", (ev) => {
        accept(JSON.parse((ev as MessageEvent).data));
        setConnection("live");
      });
      es.onerror = () => {
        // EventSource retries by itself; if it stays closed, fall back to polling.
        if (es && es.readyState === EventSource.CLOSED) { es = null; startPolling(); }
        else setConnection("connecting");
      };
    } catch {
      startPolling();
    }
    return () => { closed = true; es?.close(); if (poll) window.clearInterval(poll); };
  }, [convId, accept]);

  const refresh = useCallback(async () => { if (convId) accept(await api.state(convId)); }, [convId, accept]);

  return { state, convId, connection, refresh, newTrip: start };
}
