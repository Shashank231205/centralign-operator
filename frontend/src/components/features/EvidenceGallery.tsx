import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { evidenceFileUrl } from "@/lib/api";
import type { EvidenceItem } from "@/types/api";

const IMAGE_KIND = "screenshot";

export function EvidenceGallery({ items }: { items: EvidenceItem[] }) {
  const screenshots = items.filter((item) => item.kind === IMAGE_KIND);
  const files = items.filter((item) => item.kind !== IMAGE_KIND);
  const latest = screenshots.at(-1);
  return (
    <Card title={`Evidence (${items.length})`}>
      {items.length === 0 && (
        <EmptyState message="Screenshots and files appear as the run works." />
      )}
      {latest && (
        <a href={evidenceFileUrl(latest)} target="_blank" rel="noreferrer">
          {/* eslint-disable-next-line @next/next/no-img-element -- authenticated proxy stream, not a static asset */}
          <img
            src={evidenceFileUrl(latest)}
            alt={latest.description}
            className="w-full rounded border border-slate-200"
          />
          <p className="mt-1 text-xs text-slate-500">Latest: {latest.description}</p>
        </a>
      )}
      {files.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {files.map((item) => (
            <li key={item.id}>
              <a className="text-sky-700 underline" href={evidenceFileUrl(item)}>
                {item.kind}: {item.description}
              </a>
            </li>
          ))}
        </ul>
      )}
      {screenshots.length > 1 && (
        <details className="mt-3">
          <summary className="cursor-pointer text-xs text-slate-600">
            All screenshots ({screenshots.length})
          </summary>
          <ul className="mt-1 space-y-1 text-xs">
            {screenshots.map((item) => (
              <li key={item.id}>
                <a
                  className="text-sky-700 underline"
                  href={evidenceFileUrl(item)}
                  target="_blank"
                  rel="noreferrer"
                >
                  {new Date(item.created_at).toLocaleTimeString()} — {item.description}
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  );
}
