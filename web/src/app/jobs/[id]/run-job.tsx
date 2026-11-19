"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ErrorMessage } from "@/components/feedback";
import { apiFetch, apiPost, errorMessages, type RecordPage, type RunQueued } from "@/lib/api";

const POLL_MS = 2000;
const GIVE_UP_MS = 60_000;

async function recordTotal(id: number): Promise<number> {
  return (await apiFetch<RecordPage>(`/jobs/${id}/records?limit=1`)).total;
}

export function RunJob({ id }: { id: number }) {
  const router = useRouter();
  const [status, setStatus] = useState<string>();
  const [errors, setErrors] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  async function run() {
    setErrors([]);
    setStatus(undefined);
    setRunning(true);
    try {
      // The API only queues the run and answers at once; the worker fetches the page and
      // saves the rows. We watch the record count until new rows appear.
      const before = await recordTotal(id);
      await apiPost<RunQueued>(`/jobs/${id}/run`);
      setStatus("Queued. The worker is fetching the page…");
      const started = Date.now();

      const poll = async () => {
        try {
          const total = await recordTotal(id);
          if (total !== before) {
            setStatus(`Saved ${total - before} new ${total - before === 1 ? "row" : "rows"}.`);
            setRunning(false);
            router.refresh();
          } else if (Date.now() - started > GIVE_UP_MS) {
            setStatus("No new rows yet. Is the worker running? The run may also have found 0 rows.");
            setRunning(false);
          } else {
            timer.current = setTimeout(poll, POLL_MS);
          }
        } catch (error) {
          setErrors(errorMessages(error));
          setRunning(false);
        }
      };
      timer.current = setTimeout(poll, POLL_MS);
    } catch (error) {
      setErrors(errorMessages(error));
      setRunning(false);
    }
  }

  return (
    <div className="space-y-3">
      <button type="button" className="button" onClick={run} disabled={running}>
        {running ? "Running…" : "Run now"}
      </button>
      {errors.length > 0 && <ErrorMessage messages={errors} />}
      {status && (
        <p role="status" className="text-sm text-slate-700">
          {status}
        </p>
      )}
    </div>
  );
}
