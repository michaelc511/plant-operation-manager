import { Fragment } from "react";

type Props = {
  text: string;
  citeIdPrefix: string; // anchors are `${citeIdPrefix}-${n}`
  citationCount: number;
};

/** Renders the answer, turning [1] markers into small tappable links to the source list. */
export function AnswerText({ text, citeIdPrefix, citationCount }: Props) {
  return (
    <div className="answer-text">
      {text.split(/\n{2,}/).map((para, p) => (
        <p key={p}>
          {para.split(/(\[\d+\])/).map((part, i) => {
            const m = /^\[(\d+)\]$/.exec(part);
            if (!m) return <Fragment key={i}>{part}</Fragment>;
            const n = Number(m[1]);
            if (n < 1 || n > citationCount) return null;
            return (
              <a key={i} className="cite-marker" href={`#${citeIdPrefix}-${n}`} aria-label={`Source ${n}`}>
                {n}
              </a>
            );
          })}
        </p>
      ))}
    </div>
  );
}
