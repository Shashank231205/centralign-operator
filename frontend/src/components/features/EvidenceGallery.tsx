import { EmptyState } from "@/components/ui/EmptyState";
import { Section } from "@/components/ui/Section";
import { evidenceFileUrl } from "@/lib/api";
import type { EvidenceItem } from "@/types/api";

const IMAGE_KIND = "screenshot";

export function EvidenceGallery({ items }: { items: EvidenceItem[] }) {
  const screenshots = items.filter((item) => item.kind === IMAGE_KIND);
  const files = items.filter((item) => item.kind !== IMAGE_KIND);
  const latest = screenshots.at(-1);
  return (
    <Section
      label="Evidence"
      aside={<span className="font-mono text-label text-faint">{items.length} items</span>}
    >
      {items.length === 0 && (
        <EmptyState message="Screenshots and files appear as the run works." />
      )}
      {latest && (
        <figure>
          <a href={evidenceFileUrl(latest)} target="_blank" rel="noreferrer">
            {/* eslint-disable-next-line @next/next/no-img-element -- authenticated proxy stream, not a static asset */}
            <img
              src={evidenceFileUrl(latest)}
              alt={latest.description}
              className="w-full border border-rule transition-opacity duration-100 hover:opacity-90"
            />
          </a>
          <figcaption className="mt-2 font-mono text-label text-faint">
            Latest screen · {latest.description}
          </figcaption>
        </figure>
      )}
      {files.length > 0 && (
        <ul className="mt-6">
          {files.map((item) => (
            <li key={item.id} className="border-b border-rule last:border-0">
              <a
                className="grid grid-cols-[7rem_1fr] gap-3 py-2 transition-colors duration-100 hover:text-accent"
                href={evidenceFileUrl(item)}
              >
                <span className="font-mono text-label uppercase leading-6 text-faint">
                  {item.kind.replaceAll("_", " ")}
                </span>
                <span>{item.description}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
      {screenshots.length > 1 && (
        <details className="mt-6">
          <summary className="cursor-pointer font-mono text-label uppercase tracking-[0.14em] text-muted">
            All screens ({screenshots.length})
          </summary>
          <ol className="mt-2">
            {screenshots.map((item) => (
              <li key={item.id} className="border-b border-rule last:border-0">
                <a
                  className="grid grid-cols-[4.5rem_1fr] gap-3 py-2 transition-colors duration-100 hover:text-accent"
                  href={evidenceFileUrl(item)}
                  target="_blank"
                  rel="noreferrer"
                >
                  <time className="font-mono text-label leading-6 text-faint">
                    {new Date(item.created_at).toLocaleTimeString([], { hour12: false })}
                  </time>
                  <span>{item.description}</span>
                </a>
              </li>
            ))}
          </ol>
        </details>
      )}
    </Section>
  );
}
