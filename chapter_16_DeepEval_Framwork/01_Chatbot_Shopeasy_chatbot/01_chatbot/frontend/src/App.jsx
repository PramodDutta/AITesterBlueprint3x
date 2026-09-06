import { useEffect, useRef, useState } from "react";

const SUGGESTIONS = [
  "What's your refund policy?",
  "How long does standard shipping take?",
  "Tell me about the SP-EARBUDS-01.",
  "How do I reset my password?",
  "Can I return a hoodie after 35 days?",
];

const API_BASE = ""; // proxied by Vite to :8201

export default function App() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Hi! I'm ShopBot, your ShopSphere support assistant. Ask me about orders, shipping, refunds, or products.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState("");
  const [mode, setMode] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((r) => r.json())
      .then((d) => setModel(d.model))
      .catch(() => setModel("offline"));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  async function send(text) {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    const next = [...messages, { role: "user", content: msg }];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: msg,
          history: messages.filter((m) => m.role !== "system"),
        }),
      });
      const data = await res.json();
      setMode(data.mode);
      setMessages([...next, { role: "assistant", content: data.reply }]);
    } catch (e) {
      setMessages([...next, { role: "assistant", content: `Error: ${e.message}` }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="logo">◆</span>
          <div>
            <h1>ShopSphere</h1>
            <p className="tagline">Customer Support · ShopBot</p>
          </div>
        </div>
        <div className="status">
          <span className={`dot ${mode === "mock" ? "warn" : "ok"}`}></span>
          <span className="model">{model || "…"}</span>
          {mode === "mock" && <span className="badge">mock mode</span>}
        </div>
      </header>

      <main className="chat" ref={scrollRef}>
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            <div className="avatar">{m.role === "user" ? "🙂" : "🤖"}</div>
            <div className="content">{m.content}</div>
          </div>
        ))}
        {loading && (
          <div className="bubble assistant">
            <div className="avatar">🤖</div>
            <div className="content typing"><span></span><span></span><span></span></div>
          </div>
        )}
      </main>

      <div className="suggestions">
        {SUGGESTIONS.map((s) => (
          <button key={s} className="chip" onClick={() => send(s)} disabled={loading}>
            {s}
          </button>
        ))}
      </div>

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about orders, shipping, refunds, products…"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !input.trim()}>
          {loading ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
