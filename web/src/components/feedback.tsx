export function LoadingMessage({ children }: { children: string }) {
  return <p role="status" className="text-sm text-slate-600">{children}</p>;
}

export function ErrorMessage({ messages }: { messages: string[] }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      {messages.length === 1 ? (
        <p>{messages[0]}</p>
      ) : (
        <ul className="list-disc space-y-1 pl-5">
          {messages.map((message, index) => <li key={index}>{message}</li>)}
        </ul>
      )}
    </div>
  );
}
