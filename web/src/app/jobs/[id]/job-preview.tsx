"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition, type FormEvent } from "react";
import { ErrorMessage, LoadingMessage } from "@/components/feedback";
import { RowsTable } from "@/components/rows-table";
import { apiFetch, apiPost, errorMessages, type FieldSpec, type Job, type Preview, type Schedule } from "@/lib/api";

export function JobPreview({ id, fields }: { id: number; fields: FieldSpec[] }) {
  const router = useRouter();
  const [preview, setPreview] = useState<Preview>();
  const [previewErrors, setPreviewErrors] = useState<string[]>([]);
  const [retryCount, setRetryCount] = useState(0);
  const [schedule, setSchedule] = useState<Schedule>("manual");
  const [approvalErrors, setApprovalErrors] = useState<string[]>([]);
  const [approving, startApproval] = useTransition();

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const result = await apiFetch<Preview>(`/jobs/${id}/preview`, { signal: controller.signal });
        if (controller.signal.aborted) return;

        setPreview(result);
        // Wait for the current request to finish so slow requests never overlap.
        if (result.state === "pending") timer = setTimeout(poll, 2000);
      } catch (error) {
        if (!controller.signal.aborted) setPreviewErrors(errorMessages(error));
      }
    }

    void poll();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, retryCount]);

  async function retryGeneration() {
    // Clears the error so the worker picks the job up again, then restarts polling.
    try {
      await apiPost(`/jobs/${id}/retry`);
      setPreview(undefined);
      setRetryCount((count) => count + 1);
    } catch (error) {
      setPreviewErrors(errorMessages(error));
    }
  }

  function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApprovalErrors([]);

    startApproval(async () => {
      try {
        await apiPost<Job>(`/jobs/${id}/approve`, { schedule });
        startApproval(() => router.refresh());
      } catch (error) {
        setApprovalErrors(errorMessages(error));
      }
    });
  }

  return (
    <section className="panel space-y-5">
      <h2 className="text-xl font-semibold">Live preview</h2>

      {previewErrors.length > 0 ? (
        <div className="space-y-3">
          <ErrorMessage messages={previewErrors} />
          <button
            type="button"
            className="button-secondary"
            onClick={() => {
              setPreviewErrors([]);
              setRetryCount((count) => count + 1);
            }}
          >
            Retry preview
          </button>
        </div>
      ) : !preview ? (
        <LoadingMessage>Loading preview…</LoadingMessage>
      ) : preview.state === "pending" ? (
        <LoadingMessage>Llama is writing rules…</LoadingMessage>
      ) : preview.state === "failed" ? (
        <div className="space-y-3">
          <ErrorMessage messages={[preview.error ?? "Rule generation failed."]} />
          <button type="button" className="button-secondary" onClick={retryGeneration}>
            Try again
          </button>
        </div>
      ) : (
        <>
          <p className="text-sm font-medium">
            {preview.row_count} {preview.row_count === 1 ? "row" : "rows"} found
          </p>

          {preview.warnings.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              <h3 className="font-semibold">Warnings</h3>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {preview.warnings.map((warning, index) => <li key={index}>{warning}</li>)}
              </ul>
            </div>
          )}

          <RowsTable
            fields={fields}
            rows={preview.rows.map((data, id) => ({ id, data }))}
            caption="Preview rows"
            emptyMessage="There are no preview rows."
          />

          {preview.rules && (
            <details>
              <summary className="w-fit cursor-pointer text-sm font-semibold">Generated rules</summary>
              <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-100 p-4 text-sm">
                {JSON.stringify(preview.rules, null, 2)}
              </pre>
            </details>
          )}

          <form onSubmit={approve} className="space-y-3 border-t border-slate-200 pt-5">
            {approvalErrors.length > 0 && <ErrorMessage messages={approvalErrors} />}
            <div className="flex flex-wrap items-end gap-3">
              <label className="text-sm font-medium">
                Schedule
                <select
                  value={schedule}
                  onChange={(event) => setSchedule(event.target.value as Schedule)}
                  disabled={approving}
                  className="input min-w-36"
                >
                  <option value="manual">Manual</option>
                  <option value="hourly">Hourly</option>
                  <option value="daily">Daily</option>
                </select>
              </label>
              <button type="submit" disabled={approving} className="button">
                {approving ? "Approving…" : "Approve"}
              </button>
            </div>
          </form>
        </>
      )}
    </section>
  );
}
