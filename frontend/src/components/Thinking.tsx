import { useEffect, useState } from "react";

// The agent answers in one response, so these steps are paced to its usual 3-5 s run.
const STEPS = ["Routing your question…", "Searching the documents…", "Verifying the answer…"];

export function Thinking() {
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1300);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="thinking" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      {STEPS[step]}
    </div>
  );
}
