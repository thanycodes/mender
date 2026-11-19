import type { Metadata } from "next";
import Link from "next/link";
import { JobForm } from "./job-form";

export const metadata: Metadata = { title: "New job" };

export default function NewJobPage() {
  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <Link href="/" className="text-sm font-medium text-blue-700 hover:underline">← Jobs</Link>
      <h1 className="text-3xl font-bold tracking-tight">Describe your data</h1>
      <JobForm />
    </section>
  );
}
