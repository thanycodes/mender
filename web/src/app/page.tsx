import Link from "next/link";
import { ErrorMessage } from "@/components/feedback";
import { JobStatusBadge } from "@/components/job-status";
import { apiFetch, errorMessages, type Job } from "@/lib/api";

const createdDate = new Intl.DateTimeFormat("en", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "UTC",
});

async function JobsTable() {
  let jobs: Job[];
  try {
    jobs = await apiFetch<Job[]>("/jobs");
  } catch (error) {
    return <ErrorMessage messages={errorMessages(error)} />;
  }

  if (jobs.length === 0) {
    return <p className="panel text-slate-600">No jobs yet. Create a job to start collecting data.</p>;
  }

  return (
    <div className="table-frame">
      <table className="data-table">
        <caption className="sr-only">Scraping jobs</caption>
        <thead>
          <tr>
            <th scope="col">URL</th>
            <th scope="col">Status</th>
            <th scope="col">Fields</th>
            <th scope="col">Schedule</th>
            <th scope="col">Created (UTC)</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.id}>
              <td className="min-w-48 max-w-sm wrap-break-word">
                <Link href={`/jobs/${job.id}`} className="font-medium text-blue-700 hover:underline">
                  {job.url}
                </Link>
              </td>
              <td><JobStatusBadge status={job.status} /></td>
              <td className="min-w-32 wrap-break-word">{job.fields.map(({ name }) => name).join(", ")}</td>
              <td className="capitalize">{job.schedule ?? "—"}</td>
              <td className="whitespace-nowrap">
                <time dateTime={job.created_at}>{createdDate.format(new Date(job.created_at))}</time>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function JobsPage() {
  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-3xl font-bold tracking-tight">Jobs</h1>
        <Link href="/jobs/new" className="button">New job</Link>
      </div>
      <JobsTable />
    </section>
  );
}
