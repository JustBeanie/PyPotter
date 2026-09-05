import { FormEvent, useEffect, useState } from "react";
import { history, recognize, Recognition } from "./api";

export const trainedSpells = ["aguamenti", "alohomora", "incendio", "locomotor", "reparo", "revelio", "silencio", "specialis_revelio", "tarantallegra"];

export function App() {
  const [spell, setSpell] = useState("");
  const [imageData, setImageData] = useState<string | undefined>();
  const [result, setResult] = useState<Recognition | null>(null);
  const [recent, setRecent] = useState<Recognition[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => { history().then(setRecent).catch(() => setMessage("History is unavailable right now.")); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!spell && !imageData) { setStatus("error"); setMessage("Choose a spell or upload a wand image before casting."); return; }
    setStatus("loading"); setMessage(""); setResult(null);
    try {
      const item = await recognize(spell ? { spell } : { image_base64: imageData });
      setResult(item); setRecent((items) => [item, ...items].slice(0, 20)); setStatus("idle");
    } catch (error) { setStatus("error"); setMessage(error instanceof Error ? error.message : "Recognition failed."); }
  }

  return <main className="shell">
    <section className="hero"><p className="eyebrow">PY POTTER / LOCAL MAGIC LAB</p><h1>Cast a spell.<br /><em>Change the room.</em></h1><p className="lede">Choose a trained gesture to send it through PyPotter and keep a local history of every cast.</p></section>
    <section className="card" aria-labelledby="cast-title"><div className="card-heading"><span className="orb" aria-hidden="true">✦</span><div><p className="eyebrow">READY WHEN YOU ARE</p><h2 id="cast-title">Start a cast</h2></div></div>
      <form onSubmit={submit}><label htmlFor="spell">Spell</label><select id="spell" value={spell} onChange={(event) => { setSpell(event.target.value); setImageData(undefined); }}><option value="">Select a trained spell…</option>{trainedSpells.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}</select><label htmlFor="image">Or upload a trained wand image</label><input id="image" type="file" accept="image/png,image/jpeg" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; setSpell(""); const reader = new FileReader(); reader.onload = () => setImageData(String(reader.result)); reader.readAsDataURL(file); }} /><button disabled={status === "loading"}>{status === "loading" ? "Processing…" : "Cast spell"}<span aria-hidden="true">↗</span></button></form>
      {status === "error" && <p className="error" role="alert">{message}</p>}
      {result && <div className="result" role="status"><span className="check">✓</span><div><p className="eyebrow">RECOGNIZED</p><h3>{result.spell.replaceAll("_", " ")}</h3><p>Saved to local history{result.confidence ? ` · ${Math.round(result.confidence * 100)}% confidence` : ""}.</p></div></div>}
    </section>
    <section className="history" aria-labelledby="history-title"><div className="section-heading"><div><p className="eyebrow">THE ARCHIVE</p><h2 id="history-title">Recent casts</h2></div><span>{recent.length} saved</span></div>{recent.length === 0 ? <p className="empty">Your first cast will appear here.</p> : <ul>{recent.map((item) => <li key={item.id}><span className="history-icon">✦</span><span><strong>{item.spell.replaceAll("_", " ")}</strong><small>{new Date(item.created_at).toLocaleString()}</small></span><span className="source">{item.source}</span></li>)}</ul>}</section>
    <footer>PyPotter 2.0 · single-user local mode</footer>
  </main>;
}
