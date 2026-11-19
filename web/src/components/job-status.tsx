import type { JobStatus } from "@/lib/api";

const statuses: Record<JobStatus, { label: string; color: string }> = {
  draft: { label: "Draft", color: "bg-slate-100 text-slate-700" },
  active: { label: "Active", color: "bg-emerald-100 text-emerald-800" },
  healing: { label: "Healing", color: "bg-sky-100 text-sky-800" },
  needs_human: { label: "Needs review", color: "bg-amber-100 text-amber-900" },
  paused: { label: "Paused", color: "bg-slate-100 text-slate-700" },
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { label, color } = statuses[status];
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${color}`}>
      {label}
    </span>
  );
}
