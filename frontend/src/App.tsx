import { FormEvent, PointerEvent, useEffect, useRef, useState } from "react";
import { history, recognize, Recognition, spells, trainSpell } from "./api";

export const trainedSpells = ["aguamenti", "alohomora", "incendio", "locomotor", "reparo", "revelio", "silencio", "specialis_revelio", "tarantallegra"];

function readImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.readAsDataURL(file);
  });
}

function label(name: string): string { return name.replaceAll("_", " "); }

function GesturePad({ onSample, disabled }: { onSample: (image: string) => void; disabled: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const moved = useRef(false);

  function clear() {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.fillStyle = "#000";
    context.fillRect(0, 0, canvas.width, canvas.height);
  }

  useEffect(clear, []);

  function point(event: PointerEvent<HTMLCanvasElement>) {
    const canvas = event.currentTarget;
    const bounds = canvas.getBoundingClientRect();
    return { x: (event.clientX - bounds.left) * canvas.width / bounds.width, y: (event.clientY - bounds.top) * canvas.height / bounds.height };
  }

  function start(event: PointerEvent<HTMLCanvasElement>) {
    if (disabled) return;
    const context = event.currentTarget.getContext("2d");
    if (!context) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    clear();
    const { x, y } = point(event);
    context.beginPath(); context.moveTo(x, y);
    context.strokeStyle = "#fff"; context.lineWidth = 16;
    context.lineCap = "round"; context.lineJoin = "round";
    drawing.current = true; moved.current = false;
  }

  function move(event: PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const context = event.currentTarget.getContext("2d");
    if (!context) return;
    const { x, y } = point(event);
    context.lineTo(x, y); context.stroke();
    moved.current = true;
  }

  function finish(event: PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    drawing.current = false;
    if (moved.current) onSample(event.currentTarget.toDataURL("image/png"));
    clear();
  }

  return <canvas ref={canvasRef} className="gesture-pad" width={300} height={300} aria-label="Draw one wand gesture" onPointerDown={start} onPointerMove={move} onPointerUp={finish} onPointerCancel={() => { drawing.current = false; clear(); }} />;
}

export function App() {
  const [availableSpells, setAvailableSpells] = useState(trainedSpells);
  const [spell, setSpell] = useState("");
  const [imageData, setImageData] = useState<string | undefined>();
  const [result, setResult] = useState<Recognition | null>(null);
  const [recent, setRecent] = useState<Recognition[]>([]);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");
  const [trainingChoice, setTrainingChoice] = useState("__new__");
  const [newName, setNewName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [drawnSamples, setDrawnSamples] = useState<string[]>([]);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [trainingStatus, setTrainingStatus] = useState<"idle" | "loading" | "error" | "success">("idle");
  const [trainingMessage, setTrainingMessage] = useState("");

  useEffect(() => {
    history().then(setRecent).catch(() => setMessage("History is unavailable right now."));
    spells().then(setAvailableSpells).catch(() => setTrainingMessage("Spell list is unavailable right now."));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!spell && !imageData) { setStatus("error"); setMessage("Choose a spell or upload a wand image before casting."); return; }
    setStatus("loading"); setMessage(""); setResult(null);
    try {
      const item = await recognize(spell ? { spell } : { image_base64: imageData });
      setResult(item); setRecent((items) => [item, ...items].slice(0, 20)); setStatus("idle");
    } catch (error) { setStatus("error"); setMessage(error instanceof Error ? error.message : "Recognition failed."); }
  }

  async function submitTraining(event: FormEvent) {
    event.preventDefault();
    const name = trainingChoice === "__new__" ? newName.trim() : trainingChoice;
    if (!name) { setTrainingStatus("error"); setTrainingMessage("Enter a name for your new spell."); return; }
    const count = files.length + drawnSamples.length;
    if (count < 1 || count > 5) { setTrainingStatus("error"); setTrainingMessage("Draw or choose 1 to 5 gesture examples."); return; }
    if (files.some((file) => !["image/png", "image/jpeg"].includes(file.type))) { setTrainingStatus("error"); setTrainingMessage("Choose PNG or JPEG images."); return; }
    if (files.some((file) => file.size > 4 * 1024 * 1024) || files.reduce((total, file) => total + file.size, 0) > 5.5 * 1024 * 1024) {
      setTrainingStatus("error"); setTrainingMessage("Images are too large. Keep each under 4 MB and the group under 5.5 MB."); return;
    }
    setTrainingStatus("loading"); setTrainingMessage("");
    try {
      const images = [...drawnSamples, ...await Promise.all(files.map(readImage))];
      const saved = await trainSpell({ name, images });
      setAvailableSpells((items) => [...new Set([...items, saved.spell])].sort());
      setTrainingChoice(saved.spell); setNewName(""); setSpell(saved.spell);
      setFiles([]); setDrawnSamples([]); setFileInputKey((key) => key + 1);
      setTrainingStatus("success");
      setTrainingMessage(`${saved.added} gesture ${saved.added === 1 ? "example" : "examples"} saved for ${label(saved.spell)}. You can add more or test recognition with an image above.`);
    } catch (error) { setTrainingStatus("error"); setTrainingMessage(error instanceof Error ? error.message : "Training failed."); }
  }

  return <main className="shell">
    <section className="hero"><p className="eyebrow">PY POTTER / LOCAL MAGIC LAB</p><h1>Cast a spell.<br /><em>Change the room.</em></h1><p className="lede">Choose a trained gesture to send it through PyPotter and keep a local history of every cast.</p></section>
    <section className="card" aria-labelledby="cast-title"><div className="card-heading"><span className="orb" aria-hidden="true">✦</span><div><p className="eyebrow">READY WHEN YOU ARE</p><h2 id="cast-title">Start a cast</h2></div></div>
      <form onSubmit={submit}><label htmlFor="spell">Spell</label><select id="spell" value={spell} onChange={(event) => { setSpell(event.target.value); setImageData(undefined); }}><option value="">Select a trained spell…</option>{availableSpells.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select><label htmlFor="image">Or upload a trained wand image</label><input id="image" type="file" accept="image/png,image/jpeg" onChange={(event) => { const file = event.target.files?.[0]; if (!file) return; setSpell(""); readImage(file).then(setImageData).catch((error) => { setStatus("error"); setMessage(error.message); }); }} /><button disabled={status === "loading"}>{status === "loading" ? "Processing…" : "Cast spell"}<span aria-hidden="true">↗</span></button></form>
      {status === "error" && <p className="error" role="alert">{message}</p>}
      {result && <div className="result" role="status"><span className="check">✓</span><div><p className="eyebrow">RECOGNIZED</p><h3>{label(result.spell)}</h3><p>Saved to local history{result.confidence ? ` · ${Math.round(result.confidence * 100)}% confidence` : ""}.</p></div></div>}
    </section>
    <section className="training" aria-labelledby="training-title">
      <div className="section-heading"><div><h2 id="training-title">Train a gesture</h2><p className="training-intro">Add examples to a spell you know, or name a new one. Draw the wand path a few times or upload path images.</p></div></div>
      <form className="training-form" onSubmit={submitTraining}>
        <label htmlFor="training-spell">Spell to train</label>
        <select id="training-spell" value={trainingChoice} onChange={(event) => { setTrainingChoice(event.target.value); setTrainingStatus("idle"); }}><option value="__new__">Create a new spell</option>{availableSpells.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select>
        {trainingChoice === "__new__" && <><label htmlFor="new-spell-name">New spell name</label><input id="new-spell-name" type="text" maxLength={48} value={newName} placeholder="e.g. Lumos Maxima" onChange={(event) => setNewName(event.target.value)} /><p className="field-help">Letters, numbers and spaces. Names start with a letter.</p></>}
        <p className="draw-label">Draw a wand path</p>
        <p className="field-help">Draw one gesture with a mouse or finger. Each stroke adds an example. Try a few natural variations.</p>
        <GesturePad disabled={drawnSamples.length + files.length >= 5 || trainingStatus === "loading"} onSample={(image) => { setDrawnSamples((samples) => [...samples, image]); setTrainingStatus("idle"); }} />
        {drawnSamples.length > 0 && <div className="sample-list" aria-label="Drawn examples">{drawnSamples.map((image, index) => <div className="sample" key={index}><img src={image} alt={`Drawn example ${index + 1}`} /><button type="button" onClick={() => setDrawnSamples((samples) => samples.filter((_, item) => item !== index))} aria-label={`Remove drawn example ${index + 1}`}>Remove</button></div>)}</div>}
        <label htmlFor="training-images">Or upload wand path images</label>
        <input key={fileInputKey} id="training-images" type="file" accept="image/png,image/jpeg" multiple onChange={(event) => { setFiles(Array.from(event.target.files ?? [])); setTrainingStatus("idle"); }} />
        <p className="field-help">PNG or JPEG. You can save up to 5 drawn and uploaded examples together.</p>
        {(files.length + drawnSamples.length) > 0 && <p className="selected-count">{files.length + drawnSamples.length} of 5 examples ready</p>}
        <button disabled={trainingStatus === "loading"}>{trainingStatus === "loading" ? "Saving examples…" : "Save training examples"}</button>
      </form>
      {trainingMessage && <p className={trainingStatus === "error" ? "error" : "training-message"} role={trainingStatus === "error" ? "alert" : "status"}>{trainingMessage}</p>}
    </section>
    <section className="history" aria-labelledby="history-title"><div className="section-heading"><div><p className="eyebrow">THE ARCHIVE</p><h2 id="history-title">Recent casts</h2></div><span>{recent.length} saved</span></div>{recent.length === 0 ? <p className="empty">Your first cast will appear here.</p> : <ul>{recent.map((item) => <li key={item.id}><span className="history-icon">✦</span><span><strong>{label(item.spell)}</strong><small>{new Date(item.created_at).toLocaleString()}</small></span><span className="source">{item.source}</span></li>)}</ul>}</section>
    <footer>PyPotter 2.1 · single-user local mode</footer>
  </main>;
}
