import Link from "next/link";
import { siteConfig } from "../../../config/site";
import { ChatSource } from "../../../lib/api";
import { ChatMessage as ChatMessageType } from "../types";

type ChatMessageProps = {
  msg: ChatMessageType;
  onOpenSource?: (
    documentId: string,
    chunkIndex: number,
    excerpt: string
  ) => void;
};

type DisplaySource = ChatSource & {
  chunkIndices: number[];
};

function normalizeExcerpt(excerpt: string) {
  return excerpt.toLowerCase().replace(/\s+/g, " ").trim().slice(0, 180);
}

function formatChunkLabel(chunkIndices: number[]) {
  if (chunkIndices.length === 1) {
    return `chunk ${chunkIndices[0]}`;
  }

  const sorted = [...chunkIndices].sort((left, right) => left - right);
  const contiguous = sorted.every((value, index) =>
    index === 0 ? true : value === sorted[index - 1] + 1
  );

  if (contiguous) {
    return `chunks ${sorted[0]}-${sorted[sorted.length - 1]}`;
  }

  return `chunks ${sorted.join(", ")}`;
}

function formatSourceLocation(source: ChatSource) {
  const parts: string[] = [];

  if (source.section_title) {
    parts.push(source.section_title);
  }

  if (source.page_number !== undefined && source.page_number !== null) {
    parts.push(`Page ${source.page_number}`);
  }

  return parts.join(" | ");
}

function formatDetectedType(value?: string | null) {
  if (!value || value === "document") {
    return "General document";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function getConfidenceTone(confidence: "low" | "medium" | "high") {
  if (confidence === "high") {
    return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  }

  if (confidence === "medium") {
    return "bg-amber-50 text-amber-700 ring-amber-200";
  }

  return "bg-rose-50 text-rose-700 ring-rose-200";
}

function collapseSources(sources: ChatSource[]) {
  const collapsed: DisplaySource[] = [];

  for (const source of sources) {
    const normalizedExcerpt = normalizeExcerpt(source.excerpt);
    const existing = collapsed.find(
      (candidate) =>
        candidate.document_id === source.document_id &&
        (Math.abs(candidate.chunk_index - source.chunk_index) <= 1 ||
          normalizeExcerpt(candidate.excerpt) === normalizedExcerpt)
    );

    if (!existing) {
      collapsed.push({
        ...source,
        chunkIndices: [source.chunk_index],
      });
      continue;
    }

    existing.chunkIndices = Array.from(
      new Set([...existing.chunkIndices, source.chunk_index])
    ).sort((left, right) => left - right);

    if (source.score > existing.score) {
      existing.score = source.score;
      existing.chunk_index = source.chunk_index;
    }

    if (source.excerpt.length > existing.excerpt.length) {
      existing.excerpt = source.excerpt;
    }
  }

  return collapsed;
}

export function ChatMessage({ msg, onOpenSource }: ChatMessageProps) {
  const isUser = msg.role === "user";
  const displaySources = msg.sources ? collapseSources(msg.sources) : [];

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-3xl rounded-[1.4rem] bg-slate-950 px-4 py-3 text-white shadow-[0_12px_30px_rgba(15,23,42,0.18)]">
          <div className="mb-1.5 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
            {siteConfig.chat.labels.user}
          </div>
          <div className="whitespace-pre-wrap text-[14px] leading-6">
            {msg.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-3xl">
        <div className="mb-2 text-[10px] font-medium uppercase tracking-[0.18em] text-slate-400">
          {siteConfig.chat.labels.assistant}
          {msg.model ? ` - ${msg.model}` : ""}
        </div>
        <div className="whitespace-pre-wrap text-[14px] leading-7 text-slate-800">
          {msg.content}
        </div>

        {msg.retrieval && (
          <details className="mt-3 rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 text-sm text-slate-600">
            <summary className="cursor-pointer list-none font-medium marker:hidden">
                <span className="inline-flex flex-wrap items-center gap-2">
                  <span>{siteConfig.chat.retrievalTitle}</span>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-slate-500">
                    {siteConfig.chat.retrievalModeLabels[msg.retrieval.mode]}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-slate-500">
                    {siteConfig.chat.retrievalLabels.confidence}:{" "}
                    {
                      siteConfig.chat.retrievalConfidenceLabels[
                        msg.retrieval.confidence
                      ]
                    }
                  </span>
                  {msg.retrieval.grounded_reply_used && (
                    <span className="rounded-full bg-emerald-50 px-2 py-1 text-[11px] uppercase tracking-[0.12em] text-emerald-700 ring-1 ring-emerald-200">
                      {siteConfig.chat.retrievalGroundedLabel}
                    </span>
                  )}
              </span>
            </summary>

            <div className="mt-3 grid gap-3 border-t border-slate-200 pt-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                  {siteConfig.chat.retrievalLabels.returned}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-800">
                  {msg.retrieval.returned_sources}
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                  {siteConfig.chat.retrievalLabels.semantic}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-800">
                  {msg.retrieval.semantic_candidates}
                </div>
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                  {siteConfig.chat.retrievalLabels.term}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-800">
                  {msg.retrieval.term_candidates}
                </div>
              </div>
            </div>

            <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
              <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                {siteConfig.chat.retrievalLabels.topScore}
              </div>
              <div className="mt-1 text-sm font-medium text-slate-800">
                {msg.retrieval.top_source_score.toFixed(2)}
              </div>
            </div>

            <div
              className={`mt-3 rounded-2xl px-3 py-2.5 text-xs leading-6 ring-1 ${getConfidenceTone(
                msg.retrieval.confidence
              )}`}
            >
              {
                siteConfig.chat.retrievalConfidenceDescriptions[
                  msg.retrieval.confidence
                ]
              }
            </div>

            {msg.retrieval.document_filter_active && (
              <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                  {siteConfig.chat.retrievalLabels.scoped}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-800">
                  {msg.retrieval.document_filter_count}
                </div>
              </div>
            )}

            {msg.retrieval.metadata_filter_active && (
              <div className="mt-3 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2.5">
                <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                  {siteConfig.chat.retrievalLabels.metadata}
                </div>
                <div className="mt-1 text-sm font-medium text-slate-800">
                  {msg.retrieval.metadata_filter_count}
                  {msg.retrieval.requested_document_type
                    ? ` • ${formatDetectedType(msg.retrieval.requested_document_type)}`
                    : ""}
                  {msg.retrieval.requested_document_year
                    ? ` • ${msg.retrieval.requested_document_year}`
                    : ""}
                </div>
              </div>
            )}

            {msg.retrieval.query_terms.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {msg.retrieval.query_terms.map((term) => (
                  <span
                    key={term}
                    className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-600"
                  >
                    {term}
                  </span>
                ))}
              </div>
            )}
          </details>
        )}

        {displaySources.length > 0 && (
          <details className="mt-3 rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
            <summary className="cursor-pointer list-none font-medium marker:hidden">
              <span className="inline-flex items-center gap-2">
                <span>{siteConfig.chat.sourcesTitle}</span>
                <span className="rounded-full bg-white px-2 py-1 text-xs text-slate-500 ring-1 ring-slate-200">
                  {displaySources.length}
                </span>
              </span>
            </summary>

            <div className="mt-3 space-y-3 border-t border-slate-200 pt-3">
              {displaySources.map((source) => (
                <div
                  key={`${source.document_id}-${source.chunkIndices.join("-")}`}
                  className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
                >
                  <div className="mb-1 flex items-start justify-between gap-3">
                    <div>
                      <Link
                        href="#"
                        onClick={(event) => {
                          event.preventDefault();
                          onOpenSource?.(
                            source.document_id,
                            source.chunk_index,
                            source.excerpt
                          );
                        }}
                        className="text-sm font-medium text-slate-800 underline-offset-4 transition hover:text-slate-950 hover:underline"
                      >
                        {source.document_name} - {formatChunkLabel(source.chunkIndices)}
                      </Link>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.14em] text-slate-400">
                        {siteConfig.chat.sourceScoreLabel}: {source.score.toFixed(2)}
                      </div>
                      {source.ocr_used && (
                        <div className="mt-2 inline-flex rounded-full bg-amber-50 px-2 py-1 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200">
                          {siteConfig.chat.sourceOcrLabel}
                        </div>
                      )}
                      {formatSourceLocation(source) && (
                        <div className="mt-1 text-xs text-slate-500">
                          {formatSourceLocation(source)}
                        </div>
                      )}
                      {(source.detected_document_type || source.document_date) && (
                        <div className="mt-1 text-xs text-slate-500">
                          {[formatDetectedType(source.detected_document_type), source.document_date]
                            .filter((value, index) => (index === 0 ? !!source.detected_document_type : !!value))
                            .join(" | ")}
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        onOpenSource?.(
                          source.document_id,
                          source.chunk_index,
                          source.excerpt
                        )
                      }
                      className="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                    >
                      {siteConfig.chat.sourceOpenLabel}
                    </button>
                  </div>
                  <div className="text-xs leading-6 text-slate-500">
                    {source.excerpt}
                  </div>
                  {source.ocr_used && (
                    <div className="mt-2 text-[11px] leading-5 text-amber-700">
                      {siteConfig.chat.sourceOcrHint}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </div>
  );
}
