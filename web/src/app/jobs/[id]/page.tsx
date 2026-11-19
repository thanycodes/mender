import Link from "next/link";
import { Suspense } from "react";
import { ErrorMessage, LoadingMessage } from "@/components/feedback";
import { JobStatusBadge } from "@/components/job-status";
import { apiFetch, errorMessages, type Job } from "@/lib/api";
import { JobPreview } from "./job-preview";
import { JobRecords } from "./job-records";
import { RunJob } from "./run-job";

export default async function JobPage({ params, searchParams }: PageProps<"/jobs/[id]">) {
  const { id } = await params;
  let job: Job | undefined;
  let errors: string[] = [];

  if (/^\d+$/.test(id)) {
    try {
      job = await apiFetch<Job>(`/jobs/${id}`);
    } catch (error) {
      errors = errorMessages(error);
    }
  } else {
    errors = ["Invalid job ID."];
  }

  return (
    <section className="space-y-6">
      <Link href="/" className="text-sm font-medium text-blue-700 hover:underline">← Jobs</Link>
      {job ? (
        <>
          <div className="flex flex-wrap items-start gap-3">
            <h1 className="min-w-0 text-2xl font-bold tracking-tight wrap-break-word sm:text-3xl">{job.url}</h1>
            <JobStatusBadge status={job.status} />
          </div>

          {job.status === "draft" && <JobPreview key={job.id} id={job.id} fields={job.fields} />}
          {job.status === "active" && (
            <ActiveJob job={job} searchParams={searchParams} />
          )}
        </>
      ) : (
        <ErrorMessage messages={errors} />
      )}
    </section>
  );
}

async function ActiveJob({ job, searchParams }: {
  job: Job;
  searchParams: PageProps<"/jobs/[id]">["searchParams"];
}) {
  const { page: queryPage } = await searchParams;
  const requestedPage = typeof queryPage === "string" && /^\d+$/.test(queryPage)
    ? Number(queryPage)
    : 1;
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  return (
    <>
      <RunJob key={job.id} id={job.id} />
      <section className="panel space-y-4">
        <h2 className="text-xl font-semibold">Records</h2>
        <Suspense key={page} fallback={<LoadingMessage>Loading records…</LoadingMessage>}>
          <JobRecords job={job} page={page} />
        </Suspense>
      </section>
    </>
  );
}
