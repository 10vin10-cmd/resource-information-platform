import { useState } from "react";
import { api } from "../api";
import type { SourceLine } from "../types";

/** A citation that opens the exact source line it points to. */
export function CitationChip({ citation }: { citation: string }) {
  const [open, setOpen] = useState(false);
  const [source, setSource] = useState<SourceLine | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && !source) {
      try {
        setSource(await api.citation(citation));
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  };

  return (
    <span className="cite">
      <button type="button" className="chip" aria-expanded={open} onClick={toggle}
              title="Show the source line">
        {citation}
      </button>
      {open && (
        <span className="source" role="region" aria-label={`Source for ${citation}`}>
          {error && <span className="error">Couldn't load the source: {error}</span>}
          {!source && !error && <span className="muted">Loading source…</span>}
          {source && (
            <>
              <strong>{source.title}</strong>
              <span className="muted">
                {source.publisher} · captured {source.captured_at.slice(0, 10)} · line {source.line}
              </span>
              {source.synthetic && <span className="tag">synthetic sample</span>}
              <table className="row">
                <tbody>
                  {Object.entries(source.row).map(([k, v]) => (
                    <tr key={k}>
                      <th scope="row">{k}</th>
                      <td>{v === "" ? <em className="muted">blank</em> : v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <code className="digest" title="SHA-256 of the captured file">
                sha256 {source.sha256}
              </code>
            </>
          )}
        </span>
      )}
    </span>
  );
}
