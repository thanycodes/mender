import type { FieldSpec } from "@/lib/api";

function CellValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className="text-slate-500" aria-label="No value">—</span>;
  }

  if (typeof value === "boolean") {
    return <span aria-label={value ? "Yes" : "No"}>{value ? "✓" : "✗"}</span>;
  }

  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export function RowsTable({
  fields,
  rows,
  caption,
  emptyMessage,
}: {
  fields: FieldSpec[];
  rows: { id: number; data: Record<string, unknown> }[];
  caption: string;
  emptyMessage: string;
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-slate-600">{emptyMessage}</p>;
  }

  return (
    <div className="table-frame">
      <table className="data-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>{fields.map(({ name }) => <th key={name} scope="col">{name}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map(({ id, data }) => (
            <tr key={id}>
              {fields.map(({ name }) => (
                <td key={name} className="max-w-sm wrap-break-word">
                  <CellValue value={Object.hasOwn(data, name) ? data[name] : undefined} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
