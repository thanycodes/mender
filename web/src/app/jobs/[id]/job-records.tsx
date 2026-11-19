import Link from "next/link";
import { ErrorMessage } from "@/components/feedback";
import { RowsTable } from "@/components/rows-table";
import { apiFetch, errorMessages, type Job, type RecordPage } from "@/lib/api";

const pageSize = 50;

export async function JobRecords({ job, page }: { job: Job; page: number }) {
  const offset = (page - 1) * pageSize;
  let records: RecordPage;
  try {
    records = await apiFetch<RecordPage>(`/jobs/${job.id}/records?limit=${pageSize}&offset=${offset}`);
  } catch (error) {
    return <ErrorMessage messages={errorMessages(error)} />;
  }

  const hasPrevious = page > 1;
  const hasNext = offset + pageSize < records.total;
  const hasRows = records.items.length > 0;

  return (
    <>
      <RowsTable
        fields={job.fields}
        rows={records.items}
        caption="Saved records"
        emptyMessage={records.total === 0 ? "No records yet." : "No records on this page."}
      />
      {hasRows && (
        <p className="text-sm text-slate-600">
          {offset + 1}–{offset + records.items.length} of {records.total} records
        </p>
      )}
      {(hasPrevious || hasNext) && (
        <nav aria-label="Records pagination" className="flex gap-2">
          {hasPrevious ? (
            <Link href={`/jobs/${job.id}?page=${page - 1}`} className="button-secondary" scroll={false}>Prev</Link>
          ) : (
            <button type="button" disabled className="button-secondary">Prev</button>
          )}
          {hasNext ? (
            <Link href={`/jobs/${job.id}?page=${page + 1}`} className="button-secondary" scroll={false}>Next</Link>
          ) : (
            <button type="button" disabled className="button-secondary">Next</button>
          )}
        </nav>
      )}
    </>
  );
}
