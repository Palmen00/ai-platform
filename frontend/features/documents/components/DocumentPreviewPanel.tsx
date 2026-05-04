"use client";

import { useEffect, useRef } from "react";
import { siteConfig } from "../../../config/site";
import { DocumentPreview } from "../../../lib/api";

type DocumentPreviewPanelProps = {
  preview: DocumentPreview | null;
  isLoading: boolean;
  error: string;
  highlightExcerpt?: string;
  onClose: () => void;
  onUseInChat: (documentId: string) => void;
};

function buildHighlightTerms(excerpt: string) {
  return Array.from(
    new Set(
      excerpt
        .replace(/\.\.\./g, " ")
        .toLowerCase()
        .match(/[a-z0-9][a-z0-9_-]{2,}/gi)
        ?.filter((term) => term.length >= 4) ?? []
    )
  ).slice(0, 8);
}

function highlightText(content: string, terms: string[]) {
  if (terms.length === 0) {
    return content;
  }

  const escapedTerms = terms.map((term) =>
    term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  );
  const pattern = new RegExp(`(${escapedTerms.join("|")})`, "gi");
  const parts = content.split(pattern);

  if (parts.length === 1) {
    return content;
  }

  return parts.map((part, index) => {
    const isMatch = terms.some(
      (term) => part.toLowerCase() === term.toLowerCase()
    );

    if (!isMatch) {
      return <span key={`${part}-${index}`}>{part}</span>;
    }

    return (
      <mark
        key={`${part}-${index}`}
        className="rounded bg-amber-200/80 px-0.5 text-slate-900"
      >
        {part}
      </mark>
    );
  });
}

function formatFileSize(sizeBytes: number) {
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }

  const units = ["KB", "MB", "GB"];
  let value = sizeBytes / 1024;
  let unitIndex = 0;

  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }

  return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function formatDetectedType(value?: string | null) {
  if (!value || value === "document") {
    return siteConfig.knowledge.unknownTypeLabel;
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatDocumentDate(value?: string | null) {
  if (!value) {
    return siteConfig.knowledge.noDocumentDateLabel;
  }

  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleDateString();
}

function formatDocumentEntities(values?: string[]) {
  if (!values || values.length === 0) {
    return siteConfig.knowledge.noDocumentEntitiesLabel;
  }

  return values.join(", ");
}

function formatCommercialNumber(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) {
    return "";
  }

  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 2,
  }).format(value);
}

function formatCommercialMoney(value?: number | null, currency?: string | null) {
  const formatted = formatCommercialNumber(value);
  if (!formatted) {
    return "";
  }

  return currency ? `${formatted} ${currency}` : formatted;
}

function buildDocumentIntelligencePoints(document: DocumentPreview["document"]) {
  return [
    {
      label: "Family",
      value: document.document_family_label,
    },
    {
      label: "Version",
      value: document.document_version_label,
    },
    {
      label: "Anchor",
      value: document.document_summary_anchor,
    },
    {
      label: "Profile",
      value: document.similarity_profile,
    },
  ].filter((item) => item.value && item.value.trim().length > 0);
}

function formatSignalCategory(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatOcrEngine(value?: string | null) {
  if (!value) {
    return "";
  }

  if (value === "ocrmypdf") {
    return "OCRmyPDF";
  }

  if (value === "tesseract") {
    return "Tesseract";
  }

  return value.replace(/_/g, " ");
}

export function DocumentPreviewPanel({
  preview,
  isLoading,
  error,
  highlightExcerpt = "",
  onClose,
  onUseInChat,
}: DocumentPreviewPanelProps) {
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!scrollContainerRef.current) {
      return;
    }

    scrollContainerRef.current.scrollTo({
      top: 0,
      behavior: "auto",
    });
  }, [preview?.document.id, preview?.focused_chunk_index, highlightExcerpt]);

  if (!preview && !isLoading && !error) {
    return null;
  }

  const highlightTerms = buildHighlightTerms(highlightExcerpt);
  const focusedChunk =
    preview?.focused_chunk_index === undefined || preview?.focused_chunk_index === null
      ? null
      : preview?.chunks.find(
          (chunk) => chunk.index === preview.focused_chunk_index
        ) ?? null;
  const orderedChunks =
    preview?.focused_chunk_index === undefined || preview?.focused_chunk_index === null
      ? preview?.chunks ?? []
      : [...(preview?.chunks ?? [])].sort((left, right) => {
          if (left.index === preview.focused_chunk_index) {
            return -1;
          }
          if (right.index === preview.focused_chunk_index) {
            return 1;
          }
          return left.index - right.index;
        });
  const intelligencePoints = preview
    ? buildDocumentIntelligencePoints(preview.document)
    : [];
  const documentTopics = preview?.document.document_topics?.slice(0, 6) ?? [];
  const similarDocuments = preview?.document.similar_documents?.slice(0, 4) ?? [];
  const commercialSummary = preview?.document.commercial_summary ?? null;
  const visibleCommercialItems = commercialSummary?.line_items?.slice(0, 8) ?? [];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/30 backdrop-blur-[2px]">
      <button
        type="button"
        aria-label="Close preview"
        onClick={onClose}
        className="absolute inset-0 cursor-default"
      />

      <aside className="relative z-10 flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.24)]">
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              {siteConfig.knowledge.previewTitle}
            </p>
            <h3 className="mt-2 truncate text-xl font-semibold tracking-tight text-slate-950">
              {preview?.document.original_name ?? siteConfig.knowledge.previewLoadingLabel}
            </h3>
          </div>

          <div className="flex items-center gap-2">
            {preview && (
              <button
                type="button"
                onClick={() => onUseInChat(preview.document.id)}
                className="rounded-xl bg-slate-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
              >
                {siteConfig.knowledge.previewUseInChatLabel}
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
            >
              {siteConfig.knowledge.previewCloseLabel}
            </button>
          </div>
        </div>

        <div
          ref={scrollContainerRef}
          className="min-h-0 flex-1 overflow-y-auto px-6 py-5"
        >
          {isLoading && (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600">
              {siteConfig.knowledge.previewLoadingLabel}
            </div>
          )}

          {error && (
            <div className="rounded-2xl bg-red-50 px-4 py-4 text-sm text-red-700 ring-1 ring-red-200">
              {error}
            </div>
          )}

          {preview && !isLoading && !error && (
            <div className="space-y-6">
              <section className="grid gap-3 rounded-[1.5rem] border border-slate-200 bg-slate-50/80 p-4 sm:grid-cols-2">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.type}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {preview.document.content_type}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.detectedType}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {formatDetectedType(preview.document.detected_document_type)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.documentDate}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {formatDocumentDate(preview.document.document_date)}
                  </div>
                  {preview.document.document_date_label && (
                    <div className="mt-1 text-xs text-slate-500">
                      {preview.document.document_date_label}
                    </div>
                  )}
                </div>
                <div className="sm:col-span-2">
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.entities}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {formatDocumentEntities(preview.document.document_entities)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.size}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {formatFileSize(preview.document.size_bytes)}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.ocr}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {preview.document.ocr_used
                      ? siteConfig.knowledge.ocrUsedLabel
                      : preview.document.ocr_status === "unavailable"
                        ? siteConfig.knowledge.ocrUnavailableLabel
                        : preview.document.ocr_status === "failed"
                          ? siteConfig.knowledge.ocrFailedLabel
                          : siteConfig.knowledge.ocrNotNeededLabel}
                  </div>
                  {preview.document.ocr_used && preview.document.ocr_engine && (
                    <div className="mt-1 text-xs text-slate-500">
                      {formatOcrEngine(preview.document.ocr_engine)}
                    </div>
                  )}
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.characters}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {preview.document.character_count}
                  </div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                    {siteConfig.knowledge.previewMeta.chunks}
                  </div>
                  <div className="mt-1 text-sm text-slate-700">
                    {preview.document.chunk_count}
                  </div>
                </div>
              </section>

              {commercialSummary && (
                <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h4 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                      Commercial details
                    </h4>
                    {commercialSummary.total !== undefined &&
                      commercialSummary.total !== null && (
                        <span className="rounded-full bg-slate-950 px-3 py-1 text-xs font-semibold text-white">
                          {formatCommercialMoney(
                            commercialSummary.total,
                            commercialSummary.currency
                          )}
                        </span>
                      )}
                  </div>

                  <div className="mt-3 grid gap-x-4 gap-y-3 sm:grid-cols-3">
                    {[
                      ["Invoice", commercialSummary.invoice_number],
                      ["Invoice date", commercialSummary.invoice_date],
                      ["Due date", commercialSummary.due_date],
                      [
                        "Subtotal",
                        formatCommercialMoney(
                          commercialSummary.subtotal,
                          commercialSummary.currency
                        ),
                      ],
                      [
                        "Tax",
                        formatCommercialMoney(
                          commercialSummary.tax,
                          commercialSummary.currency
                        ),
                      ],
                      [
                        "Total",
                        formatCommercialMoney(
                          commercialSummary.total,
                          commercialSummary.currency
                        ),
                      ],
                    ]
                      .filter((item) => item[1])
                      .map(([label, value]) => (
                        <div key={label} className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                            {label}
                          </div>
                          <div className="mt-1 truncate text-sm text-slate-700">
                            {value}
                          </div>
                        </div>
                      ))}
                  </div>

                  {visibleCommercialItems.length > 0 && (
                    <div className="mt-4 overflow-x-auto">
                      <table className="w-full min-w-[34rem] text-left text-sm">
                        <thead>
                          <tr className="border-b border-slate-100 text-[11px] uppercase tracking-[0.14em] text-slate-400">
                            <th className="py-2 pr-3 font-semibold">Item</th>
                            <th className="py-2 pr-3 font-semibold">Qty</th>
                            <th className="py-2 pr-3 font-semibold">Unit</th>
                            <th className="py-2 pr-3 font-semibold">Total</th>
                            <th className="py-2 font-semibold">SKU</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {visibleCommercialItems.map((item, index) => (
                            <tr key={`${item.description}-${index}`}>
                              <td className="max-w-xs py-2 pr-3 text-slate-800">
                                <div className="truncate">{item.description}</div>
                              </td>
                              <td className="py-2 pr-3 text-slate-600">
                                {formatCommercialNumber(item.quantity)}
                              </td>
                              <td className="py-2 pr-3 text-slate-600">
                                {formatCommercialMoney(
                                  item.unit_price,
                                  item.currency ?? commercialSummary.currency
                                )}
                              </td>
                              <td className="py-2 pr-3 text-slate-600">
                                {formatCommercialMoney(
                                  item.total,
                                  item.currency ?? commercialSummary.currency
                                )}
                              </td>
                              <td className="py-2 text-xs text-slate-500">
                                {item.sku ?? ""}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {(commercialSummary.line_items?.length ?? 0) >
                        visibleCommercialItems.length && (
                        <div className="mt-2 text-xs text-slate-500">
                          Showing {visibleCommercialItems.length} of{" "}
                          {commercialSummary.line_items?.length ?? 0} extracted items.
                        </div>
                      )}
                    </div>
                  )}
                </section>
              )}

              {(intelligencePoints.length > 0 ||
                documentTopics.length > 0 ||
                similarDocuments.length > 0) && (
                <section className="rounded-2xl border border-slate-200 bg-white px-4 py-4">
                  <h4 className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">
                    Intelligence snapshot
                  </h4>

                  {intelligencePoints.length > 0 && (
                    <div className="mt-3 grid gap-x-4 gap-y-3 sm:grid-cols-2">
                      {intelligencePoints.map((item) => (
                        <div key={item.label} className="min-w-0">
                          <div className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                            {item.label}
                          </div>
                          <div className="mt-1 truncate text-sm text-slate-700">
                            {item.value}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {documentTopics.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {documentTopics.map((topic) => (
                        <span
                          key={topic}
                          className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-600"
                        >
                          {topic}
                        </span>
                      ))}
                    </div>
                  )}

                  {similarDocuments.length > 0 && (
                    <div className="mt-4 divide-y divide-slate-100">
                      {similarDocuments.map((document) => (
                        <div
                          key={document.document_id}
                          className="flex items-center justify-between gap-3 py-2 text-sm"
                        >
                          <div className="min-w-0">
                            <div className="truncate font-medium text-slate-700">
                              {document.document_name}
                            </div>
                            {document.reason && (
                              <div className="truncate text-xs text-slate-400">
                                {document.reason}
                              </div>
                            )}
                          </div>
                          <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
                            {Math.round(document.score * 100)}%
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              )}

              {focusedChunk && (
                <section>
                  <div className="flex items-center justify-between gap-3">
                    <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-500">
                      Matched source
                    </h4>
                    <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                      Chunk {focusedChunk.index}
                    </span>
                  </div>

                  <div className="mt-3 rounded-[1.5rem] border border-emerald-300 bg-emerald-50/70 px-4 py-4">
                    {highlightExcerpt && (
                      <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-6 text-amber-900">
                        <span className="mr-2 font-semibold uppercase tracking-[0.12em] text-amber-700">
                          Matched excerpt
                        </span>
                        {highlightExcerpt}
                      </div>
                    )}
                    <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-700">
                      {highlightText(focusedChunk.content, highlightTerms)}
                    </div>
                  </div>
                </section>
              )}

              <section>
                <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-500">
                  {siteConfig.knowledge.previewSignalsTitle}
                </h4>

                <div className="mt-3 flex flex-wrap gap-2">
                  {(preview.document.document_signals ?? []).slice(0, 12).map((signal) => (
                    <div
                      key={`${signal.category}-${signal.normalized}`}
                      className="rounded-2xl border border-slate-200 bg-white px-3 py-2"
                    >
                      <div className="text-sm font-medium text-slate-800">{signal.value}</div>
                      <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-slate-400">
                        {formatSignalCategory(signal.category)} · {signal.score.toFixed(2)}
                      </div>
                    </div>
                  ))}
                  {(preview.document.document_signals ?? []).length === 0 && (
                    <div className="rounded-[1.5rem] border border-slate-200 bg-white px-4 py-4 text-sm text-slate-600">
                      {siteConfig.knowledge.previewEmptySignals}
                    </div>
                  )}
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between gap-3">
                  <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-500">
                    {siteConfig.knowledge.previewTextTitle}
                  </h4>
                  {preview.extracted_text_truncated && (
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium text-slate-500">
                      {siteConfig.knowledge.previewTruncatedLabel}
                    </span>
                  )}
                </div>

                <div className="mt-3 rounded-[1.5rem] border border-slate-200 bg-white px-4 py-4 text-sm leading-7 text-slate-700">
                  {preview.extracted_text || siteConfig.knowledge.previewEmptyText}
                </div>
              </section>

              <section>
                <h4 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-500">
                  {siteConfig.knowledge.previewChunksTitle}
                </h4>

                <div className="mt-3 space-y-3">
                  {preview.chunks.length === 0 && (
                    <div className="rounded-[1.5rem] border border-slate-200 bg-white px-4 py-4 text-sm text-slate-600">
                      {siteConfig.knowledge.previewEmptyChunks}
                    </div>
                  )}

                  {orderedChunks.map((chunk) => (
                    <div
                      key={chunk.index}
                      className={`rounded-[1.5rem] border px-4 py-4 ${
                        preview.focused_chunk_index === chunk.index
                          ? "border-emerald-300 bg-emerald-50/70"
                          : "border-slate-200 bg-white"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                          Chunk {chunk.index}
                        </div>
                        {preview.focused_chunk_index === chunk.index && (
                          <span className="rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-emerald-700 ring-1 ring-emerald-200">
                            {siteConfig.knowledge.previewFocusedChunkLabel}
                          </span>
                        )}
                      </div>
                      <div className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-700">
                        {preview.focused_chunk_index === chunk.index
                          ? highlightText(chunk.content, highlightTerms)
                          : chunk.content}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
