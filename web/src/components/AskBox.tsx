import { type FormEvent, useState } from "react";
import { api } from "../api";
import type { Answer } from "../types";
import { CitationChip } from "./CitationChip";

const EXAMPLES = [
  "How much rain fell in Harris County in 2017?",
  "Average daily high in El Paso and Lubbock from 2020 to 2022",
  "Storms in Potter County in 2021",
  "Will it rain in Travis County tomorrow?",
];

const STATUS_TEXT: Record<Answer["status"], string> = {
  answered: "Answered",
  partial: "Partly answered",
  unknown: "No figure in the sources",
  declined: "Out of scope",
};

/** "cause: The platform ..." → "The platform ..." (the prefix is for the log). */
function reasonText(reason: string): string {
  const i = reason.indexOf(": ");
  return i >= 0 ? reason.slice(i + 2) : reason;
}

export function AskBox() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (q: string) => {
    if (q.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await api.ask(q));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit(question);
  };

  return (
    <section className="panel ask" aria-labelledby="ask-heading">
      <h2 id="ask-heading">Ask</h2>
      <form onSubmit={onSubmit}>
        <label htmlFor="question" className="visually-hidden">Question</label>
        <input id="question" value={question} onChange={(e) => setQuestion(e.target.value)}
               placeholder="e.g. rainfall in Hale County 2020" />
        <button type="submit" disabled={busy}>{busy ? "Asking…" : "Ask"}</button>
      </form>
      <div className="examples">
        {EXAMPLES.map((q) => (
          <button key={q} type="button" className="link"
                  onClick={() => { setQuestion(q); void submit(q); }}>
            {q}
          </button>
        ))}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {answer && (
        <div className="answer" aria-live="polite">
          <p>
            <span className={`status ${answer.status}`}>{STATUS_TEXT[answer.status]}</span>
            {answer.synthetic && <span className="tag">synthetic sample</span>}
          </p>
          {answer.statements.length > 0 && (
            <ul className="statements">
              {answer.statements.map((s, i) => (
                <li key={i}>{s.text} {s.citation && <CitationChip citation={s.citation} />}</li>
              ))}
            </ul>
          )}
          {answer.missing.length > 0 && (
            <>
              <p className="muted">Not in the sources:</p>
              <ul className="missing">{answer.missing.map((m) => <li key={m}>{m}</li>)}</ul>
            </>
          )}
          {answer.reason && <p className="reason">{reasonText(answer.reason)}</p>}
          {answer.notes.map((n) => <p key={n} className="note">{n}</p>)}
          {answer.log_id && <p className="muted small">Logged as {answer.log_id}</p>}
        </div>
      )}
    </section>
  );
}
