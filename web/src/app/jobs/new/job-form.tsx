"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { ErrorMessage } from "@/components/feedback";
import { apiPost, errorMessages, type CreateResult, type FieldSpec, type FieldType } from "@/lib/api";

type FieldRow = { id: number; name: string; type: FieldType; description: string };
const fieldNamePattern = /^[a-z][a-z0-9_]{0,39}$/;

export function JobForm() {
  const router = useRouter();
  const nextFieldId = useRef(1);
  const [fields, setFields] = useState<FieldRow[]>([
    { id: 0, name: "", type: "text", description: "" },
  ]);
  const [errors, setErrors] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  function addField() {
    // Stable IDs keep the inputs and labels paired when a row is removed.
    const id = nextFieldId.current++;
    setFields((rows) => [...rows, { id, name: "", type: "text", description: "" }]);
  }

  function updateField(id: number, changes: Partial<Omit<FieldRow, "id">>) {
    setFields((rows) => rows.map((row) => row.id === id ? { ...row, ...changes } : row));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrors([]);

    const invalidNames = fields.flatMap((field, index) =>
      fieldNamePattern.test(field.name)
        ? []
        : [`Field ${index + 1}: Start with a lowercase letter and use up to 40 lowercase letters, digits, or underscores.`],
    );
    if (invalidNames.length > 0) {
      setErrors(invalidNames);
      return;
    }

    const formData = new FormData(event.currentTarget);
    const specs: FieldSpec[] = fields.map(({ name, type, description }) => ({
      name,
      type,
      description: description.trim() || undefined,
    }));

    setSubmitting(true);
    try {
      const result = await apiPost<CreateResult>("/jobs", { url: formData.get("url"), fields: specs });
      router.push(`/jobs/${result.job_id}`);
    } catch (error) {
      setErrors(errorMessages(error));
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="panel space-y-5">
      <fieldset disabled={submitting} className="min-w-0 space-y-6">
        <label className="block text-sm font-medium">
          Page URL
          <input name="url" type="url" className="input" placeholder="https://example.com/products" required />
        </label>
        <div className="space-y-3">
          <h2 className="text-lg font-semibold">Fields</h2>
          {fields.map((field, index) => (
            <fieldset key={field.id} className="min-w-0 rounded-lg border border-slate-200 px-3 pb-3">
              <legend className="px-1 text-sm font-semibold">Field {index + 1}</legend>
              <div className="grid gap-3 sm:grid-cols-[2fr_1fr_auto] sm:items-end">
                <label className="block text-sm font-medium">
                  Name
                  <input
                    value={field.name}
                    onChange={(event) => updateField(field.id, { name: event.target.value })}
                    className="input"
                    placeholder="e.g. product_name"
                    required
                  />
                </label>
                <label className="block text-sm font-medium">
                  Type
                  <select
                    value={field.type}
                    onChange={(event) => updateField(field.id, { type: event.target.value as FieldType })}
                    className="input"
                  >
                    <option value="text">text</option>
                    <option value="number">number</option>
                    <option value="exists">yes-no</option>
                  </select>
                </label>
                <button
                  type="button"
                  disabled={fields.length === 1}
                  onClick={() => setFields((rows) => rows.filter(({ id }) => id !== field.id))}
                  aria-label={`Remove field ${index + 1}`}
                  className="button-secondary justify-self-start"
                >
                  Remove
                </button>
                <label className="block text-sm font-medium sm:col-span-3">
                  Description <span className="font-normal text-slate-600">(optional)</span>
                  <input
                    value={field.description}
                    onChange={(event) => updateField(field.id, { description: event.target.value })}
                    className="input"
                  />
                </label>
              </div>
            </fieldset>
          ))}
          <button type="button" onClick={addField} className="button-secondary">Add field</button>
        </div>
      </fieldset>

      {errors.length > 0 && <ErrorMessage messages={errors} />}
      <button type="submit" disabled={submitting} className="button">
        {submitting ? "Creating job…" : "Generate rules"}
      </button>
    </form>
  );
}
