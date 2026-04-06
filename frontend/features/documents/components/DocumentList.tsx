"use client";

import { useEffect, useMemo, useState } from "react";
import { siteConfig } from "../../../config/site";
import { DocumentFacetOption, DocumentItem } from "../../../lib/api";

type DocumentListProps = {
  documents: DocumentItem[];
  totalCount: number;
  hasMoreOnServer: boolean;
  availableDocumentTypes: string[];
  availableSources: string[];
  availableTypeFacets: DocumentFacetOption[];
  availableSourceFacets: DocumentFacetOption[];
  searchQuery: string;
  statusFilter: string;
  typeFilter: string;
  sourceFilter: string;
  sortOrder: string;
  isLoading: boolean;
  processingDocumentId: string;
  isReprocessingAll?: boolean;
  onSearchChange: (value: string) => void;
  onStatusFilterChange: (value: string) => void;
  onTypeFilterChange: (value: string) => void;
  onSourceFilterChange: (value: string) => void;
  onSortChange: (value: string) => void;
  onDelete: (documentId: string) => Promise<void>;
  onReprocess: (documentId: string) => Promise<void>;
  onPreview: (documentId: string) => Promise<void>;
  canManageDocuments?: boolean;
  canManageVisibility?: boolean;
  onSetVisibility?: (
    documentId: string,
    payload: {
      visibility: "standard" | "hidden" | "restricted";
      accessUsernames?: string[];
    }
  ) => Promise<void>;
};

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

function getStatusLabel(status: string) {
  if (status === "processed") {
    return siteConfig.knowledge.processedLabel;
  }

  if (status === "failed") {
    return siteConfig.knowledge.failedLabel;
  }

  return siteConfig.knowledge.pendingLabel;
}

function getIndexLabel(status?: string) {
  if (status === "indexed") {
    return siteConfig.knowledge.indexedLabel;
  }

  if (status === "failed") {
    return siteConfig.knowledge.indexingFailedLabel;
  }

  return siteConfig.knowledge.indexingPendingLabel;
}

function formatRelativeTimestamp(value?: string | null) {
  if (!value) {
    return "";
  }

  const deltaMs = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(deltaMs) || deltaMs < 0) {
    return "";
  }

  const totalSeconds = Math.floor(deltaMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;

  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }

  return `${seconds}s`;
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
    return "";
  }

  return values.slice(0, 2).join(", ");
}

function formatDocumentSignals(values?: { value: string }[]) {
  if (!values || values.length === 0) {
    return "";
  }

  return values.slice(0, 3).map((item) => item.value).join(", ");
}

function getStageLabel(stage?: string) {
  switch (stage) {
    case "queued":
      return siteConfig.knowledge.stageQueuedLabel;
    case "extracting":
      return siteConfig.knowledge.stageExtractingLabel;
    case "chunking":
      return siteConfig.knowledge.stageChunkingLabel;
    case "indexing":
      return siteConfig.knowledge.stageIndexingLabel;
    case "completed":
      return siteConfig.knowledge.stageCompletedLabel;
    case "failed":
      return siteConfig.knowledge.stageFailedLabel;
    default:
      return "";
  }
}

function getOcrLabel(status?: string, used?: boolean) {
  if (used || status === "used") {
    return siteConfig.knowledge.ocrUsedLabel;
  }

  if (status === "unavailable") {
    return siteConfig.knowledge.ocrUnavailableLabel;
  }

  if (status === "failed") {
    return siteConfig.knowledge.ocrFailedLabel;
  }

  return siteConfig.knowledge.ocrNotNeededLabel;
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

function formatFacetLabel(
  value: string,
  facets: DocumentFacetOption[],
  formatValue: (input: string) => string
) {
  const count = facets.find((facet) => facet.value === value)?.count;
  if (count === undefined) {
    return formatValue(value);
  }

  return `${formatValue(value)} (${count})`;
}

export function DocumentList({
  documents,
  totalCount,
  hasMoreOnServer,
  availableDocumentTypes,
  availableSources,
  availableTypeFacets,
  availableSourceFacets,
  searchQuery,
  statusFilter,
  typeFilter,
  sourceFilter,
  sortOrder,
  isLoading,
  processingDocumentId,
  isReprocessingAll = false,
  onSearchChange,
  onStatusFilterChange,
  onTypeFilterChange,
  onSourceFilterChange,
  onSortChange,
  onDelete,
  onReprocess,
  onPreview,
  canManageDocuments = true,
  canManageVisibility = false,
  onSetVisibility,
}: DocumentListProps) {
  const PAGE_SIZE = 50;
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  function resetVisibleCount() {
    setVisibleCount(PAGE_SIZE);
  }

  function handleSearchChange(value: string) {
    onSearchChange(value);
    resetVisibleCount();
  }

  function handleSortChange(value: string) {
    onSortChange(value);
    resetVisibleCount();
  }

  function handleTypeFilterChange(value: string) {
    onTypeFilterChange(value);
    resetVisibleCount();
  }

  function handleSourceFilterChange(value: string) {
    onSourceFilterChange(value);
    resetVisibleCount();
  }

  function handleStatusFilterChange(value: string) {
    onStatusFilterChange(value);
    resetVisibleCount();
  }

  const hasPendingDocuments = documents.some(
    (document) =>
      document.processing_status === "pending" ||
      document.indexing_status === "pending"
  );

  useEffect(() => {
    if (!hasPendingDocuments) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 5000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [hasPendingDocuments]);

  const visibleDocuments = useMemo(
    () => documents.slice(0, visibleCount),
    [documents, visibleCount]
  );

  const hasMoreDocuments = documents.length > visibleCount;
  const hasActiveFilters =
    searchQuery.trim().length > 0 ||
    statusFilter !== "all" ||
    typeFilter !== "all" ||
    sourceFilter !== "all" ||
    sortOrder !== "newest";

  return (
    <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
      <div className="mb-5 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h3 className="text-xl font-semibold tracking-tight text-slate-950">
            {siteConfig.knowledge.listTitle}
          </h3>
        </div>

        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <input
            value={searchQuery}
            onChange={(event) => handleSearchChange(event.target.value)}
            placeholder={siteConfig.knowledge.searchPlaceholder}
            className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400 md:w-64"
          />

          <select
            value={sortOrder}
            onChange={(event) => handleSortChange(event.target.value)}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400"
            aria-label={siteConfig.knowledge.sortLabel}
          >
            <option value="newest">{siteConfig.knowledge.sortNewestLabel}</option>
            <option value="oldest">{siteConfig.knowledge.sortOldestLabel}</option>
            <option value="name">{siteConfig.knowledge.sortNameLabel}</option>
            <option value="largest">{siteConfig.knowledge.sortLargestLabel}</option>
            <option value="document_date_newest">
              {siteConfig.knowledge.sortDocumentDateNewestLabel}
            </option>
            <option value="document_date_oldest">
              {siteConfig.knowledge.sortDocumentDateOldestLabel}
            </option>
          </select>

          <select
            value={typeFilter}
            onChange={(event) => handleTypeFilterChange(event.target.value)}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400"
            aria-label={siteConfig.knowledge.typeFilterLabel}
          >
            <option value="all">{siteConfig.knowledge.filterAllTypesLabel}</option>
            {availableDocumentTypes.map((documentType) => (
              <option key={documentType} value={documentType}>
                {formatFacetLabel(
                  documentType,
                  availableTypeFacets,
                  formatDetectedType
                )}
              </option>
            ))}
          </select>

          <select
            value={sourceFilter}
            onChange={(event) => handleSourceFilterChange(event.target.value)}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400"
            aria-label={siteConfig.knowledge.sourceFilterLabel}
          >
            <option value="all">{siteConfig.knowledge.filterAllSourcesLabel}</option>
            {availableSources.map((source) => (
              <option key={source} value={source}>
                {formatFacetLabel(
                  source,
                  availableSourceFacets,
                  (input) => input.replace(/_/g, " ")
                )}
              </option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(event) => handleStatusFilterChange(event.target.value)}
            className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 outline-none transition focus:border-slate-400"
          >
            <option value="all">{siteConfig.knowledge.filterAllLabel}</option>
            <option value="processed">
              {siteConfig.knowledge.filterProcessedLabel}
            </option>
            <option value="pending">{siteConfig.knowledge.filterPendingLabel}</option>
            <option value="failed">{siteConfig.knowledge.filterFailedLabel}</option>
            <option value="index_failed">
              {siteConfig.knowledge.filterIndexFailedLabel}
            </option>
          </select>
        </div>
      </div>

      <div className="overflow-x-auto">
        {documents.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
            <span>
              {siteConfig.knowledge.visibleCountLabel
                .replace("{visible}", String(visibleDocuments.length))
                .replace("{total}", String(totalCount))}
            </span>
            {hasMoreOnServer && (
              <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5">
                {siteConfig.knowledge.serverWindowLabel
                  .replace("{loaded}", String(documents.length))
                  .replace("{total}", String(totalCount))}
              </span>
            )}
            {hasMoreDocuments && (
              <button
                type="button"
                onClick={() => setVisibleCount((current) => current + PAGE_SIZE)}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 font-medium text-slate-600 transition hover:bg-slate-100"
              >
                {siteConfig.knowledge.showMoreButton}
              </button>
            )}
          </div>
        )}
        <table className="w-full table-fixed border-separate border-spacing-y-2">
          <thead>
            <tr className="text-left text-sm text-slate-500">
              <th className="w-[8rem] px-3 py-2 sm:w-[10rem] lg:w-[13rem] xl:w-[16rem] 2xl:w-[20rem]">
                {siteConfig.knowledge.columns.name}
              </th>
              <th className="px-3 py-2">{siteConfig.knowledge.columns.type}</th>
              <th className="px-3 py-2">{siteConfig.knowledge.columns.size}</th>
              <th className="px-3 py-2">{siteConfig.knowledge.columns.status}</th>
              <th className="hidden px-3 py-2 lg:table-cell">{siteConfig.knowledge.columns.chunks}</th>
              <th className="hidden px-3 py-2 xl:table-cell">
                {siteConfig.knowledge.columns.documentDate}
              </th>
              <th className="hidden px-3 py-2 2xl:table-cell">
                {siteConfig.knowledge.columns.uploadedAt}
              </th>
              <th className="px-3 py-2">
                {siteConfig.knowledge.columns.actions}
              </th>
            </tr>
          </thead>
          <tbody>
            {visibleDocuments.map((document) => (
              <tr
                key={document.id}
                className="rounded-2xl bg-slate-50 text-slate-700 ring-1 ring-slate-200/70"
              >
                <td className="w-[8rem] max-w-0 overflow-hidden px-3 py-3 font-medium text-slate-900 sm:w-[10rem] lg:w-[13rem] xl:w-[16rem] 2xl:w-[20rem]">
                  <button
                    type="button"
                    onClick={() => void onPreview(document.id)}
                    className="group flex w-full min-w-0 overflow-hidden items-center gap-2 text-left text-slate-900 underline-offset-4 transition hover:text-slate-700 hover:underline"
                  >
                    <span
                      title={document.original_name}
                      className="block min-w-0 flex-1 truncate"
                    >
                      {document.original_name}
                    </span>
                    <span className="hidden shrink-0 text-xs text-slate-400 transition group-hover:text-slate-600 xl:inline">
                      Open
                    </span>
                  </button>
                  {document.document_title && (
                    <div
                      title={document.document_title}
                      className="mt-1 hidden max-w-full truncate text-xs font-normal text-slate-500 xl:block"
                    >
                      {document.document_title}
                    </div>
                  )}
                  <div className="mt-1 hidden max-w-full truncate text-[11px] text-slate-400 xl:block">
                    {(document.source_provider || document.source_origin).replace(
                      /_/g,
                      " "
                    )}
                  </div>
                  {document.visibility === "hidden" && (
                    <div className="mt-2">
                      <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-amber-800">
                        {siteConfig.knowledge.hiddenVisibilityLabel}
                      </span>
                    </div>
                  )}
                  {document.visibility === "restricted" && (
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-sky-200 bg-sky-50 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.12em] text-sky-800">
                        {siteConfig.knowledge.restrictedVisibilityLabel}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        {(document.access_usernames ?? []).length > 0
                          ? `${(document.access_usernames ?? []).length} user${(document.access_usernames ?? []).length === 1 ? "" : "s"}`
                          : "No users assigned"}
                      </span>
                    </div>
                  )}
                </td>
                <td className="px-3 py-3 text-sm">
                  <div className="font-medium text-slate-800">
                    {formatDetectedType(document.detected_document_type)}
                  </div>
                  <div className="mt-1 hidden text-xs text-slate-500 xl:block">
                    {document.content_type}
                  </div>
                  {document.document_entities && document.document_entities.length > 0 && (
                    <div className="mt-1 max-w-xs truncate text-xs text-slate-500">
                      {formatDocumentEntities(document.document_entities)}
                    </div>
                  )}
                  {document.document_signals && document.document_signals.length > 0 && (
                    <div className="mt-1 max-w-xs truncate text-[11px] text-slate-400">
                      {formatDocumentSignals(document.document_signals)}
                    </div>
                  )}
                </td>
                <td className="px-3 py-3 text-sm">
                  {formatFileSize(document.size_bytes)}
                </td>
                <td className="px-3 py-3 text-sm">
                  <div>{getStatusLabel(document.processing_status)}</div>
                  {document.processing_stage &&
                    document.processing_stage !== "completed" &&
                    document.processing_stage !== "failed" && (
                      <div className="mt-1 text-xs text-slate-500">
                        {getStageLabel(document.processing_stage)}
                      </div>
                    )}
                  {document.processing_status === "processed" && !document.processing_error && (
                    <div className="mt-1 text-xs text-slate-500">
                      {getIndexLabel(document.indexing_status)}
                    </div>
                  )}
                  {document.content_type === "application/pdf" && (
                    <div className="mt-1 text-xs text-slate-500">
                      {getOcrLabel(document.ocr_status, document.ocr_used)}
                      {document.ocr_used && document.ocr_engine && (
                        <span className="ml-2 text-slate-400">
                          via {formatOcrEngine(document.ocr_engine)}
                        </span>
                      )}
                    </div>
                  )}
                  {document.processing_status === "pending" &&
                    document.processing_started_at && (
                      <div className="mt-1 hidden text-xs text-slate-500 xl:block">
                        {siteConfig.knowledge.elapsedLabel}{" "}
                        {formatRelativeTimestamp(document.processing_started_at)}
                      </div>
                    )}
                  {document.processing_status === "pending" &&
                    document.processing_started_at &&
                    nowMs -
                      new Date(document.processing_started_at).getTime() >
                      120000 && (
                      <div className="mt-1 max-w-xs text-xs text-amber-700">
                        {siteConfig.knowledge.longRunningHint}
                      </div>
                    )}
                  {document.indexing_status === "skipped" &&
                    document.character_count === 0 && (
                      <div className="mt-1 max-w-xs text-xs text-amber-700">
                        {siteConfig.knowledge.noTextHint}
                      </div>
                    )}
                  {document.ocr_status === "unavailable" && (
                    <div className="mt-1 max-w-xs text-xs text-amber-700">
                      {siteConfig.knowledge.ocrUnavailableHint}
                    </div>
                  )}
                  {document.ocr_status === "failed" &&
                    !!document.ocr_error &&
                    document.character_count === 0 && (
                      <div className="mt-1 max-w-xs text-xs text-amber-700">
                        {siteConfig.knowledge.ocrFailedHint}
                      </div>
                    )}
                  {document.processing_error && (
                    <div className="mt-1 max-w-xs text-xs text-red-600">
                      {document.processing_error}
                    </div>
                  )}
                  {document.indexing_error &&
                    !(document.indexing_status === "skipped" &&
                      document.character_count === 0) && (
                    <div className="mt-1 max-w-xs text-xs text-amber-700">
                      {document.indexing_error}
                    </div>
                  )}
                </td>
                <td className="hidden px-3 py-3 text-sm lg:table-cell">
                  {document.chunk_count}
                </td>
                <td className="hidden px-3 py-3 text-sm xl:table-cell">
                  <div>{formatDocumentDate(document.document_date)}</div>
                  {document.document_date_label && (
                    <div className="mt-1 text-xs text-slate-500">
                      {document.document_date_label}
                    </div>
                  )}
                </td>
                <td className="hidden px-3 py-3 text-sm 2xl:table-cell">
                  <div>{new Date(document.uploaded_at).toLocaleString()}</div>
                  {document.last_processed_at && (
                    <div className="mt-1 text-xs text-slate-500">
                      Processed {new Date(document.last_processed_at).toLocaleString()}
                    </div>
                  )}
                  {document.indexed_at && (
                    <div className="mt-1 text-xs text-slate-500">
                      Indexed {new Date(document.indexed_at).toLocaleString()}
                    </div>
                  )}
                </td>
                <td className="px-3 py-3">
                  <div className="flex flex-wrap gap-2">
                    {canManageDocuments && (
                      <>
                        <button
                          onClick={() => void onReprocess(document.id)}
                          disabled={
                            processingDocumentId === document.id || isReprocessingAll
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {processingDocumentId === document.id || isReprocessingAll
                            ? siteConfig.knowledge.processingButton
                            : siteConfig.knowledge.reprocessButton}
                        </button>
                        <button
                          onClick={() => void onDelete(document.id)}
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                        >
                          {siteConfig.knowledge.deleteButton}
                        </button>
                      </>
                    )}
                    {canManageVisibility && onSetVisibility && (
                      <>
                        <button
                          onClick={() =>
                            void onSetVisibility(document.id, {
                              visibility:
                                document.visibility === "hidden"
                                  ? "standard"
                                  : "hidden",
                            })
                          }
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                        >
                          {document.visibility === "hidden"
                            ? siteConfig.knowledge.unhideButton
                            : siteConfig.knowledge.hideButton}
                        </button>
                        {document.visibility === "restricted" ? (
                          <>
                            <button
                              onClick={() =>
                                void onSetVisibility(document.id, {
                                  visibility: "standard",
                                })
                              }
                              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                            >
                              {siteConfig.knowledge.standardAccessButton}
                            </button>
                            <button
                              onClick={() => {
                                const nextUsers = window.prompt(
                                  siteConfig.knowledge.restrictPrompt,
                                  (document.access_usernames ?? []).join(", ")
                                );
                                if (nextUsers === null) {
                                  return;
                                }
                                const parsedUsers = nextUsers
                                  .split(",")
                                  .map((value) => value.trim())
                                  .filter(Boolean);
                                if (parsedUsers.length === 0) {
                                  window.alert(
                                    siteConfig.knowledge.restrictPromptEmpty
                                  );
                                  return;
                                }
                                void onSetVisibility(document.id, {
                                  visibility: "restricted",
                                  accessUsernames: parsedUsers,
                                });
                              }}
                              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                            >
                              {siteConfig.knowledge.editRestrictedAccessButton}
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => {
                              const nextUsers = window.prompt(
                                siteConfig.knowledge.restrictPrompt,
                                ""
                              );
                              if (nextUsers === null) {
                                return;
                              }
                              const parsedUsers = nextUsers
                                .split(",")
                                .map((value) => value.trim())
                                .filter(Boolean);
                              if (parsedUsers.length === 0) {
                                window.alert(
                                  siteConfig.knowledge.restrictPromptEmpty
                                );
                                return;
                              }
                              void onSetVisibility(document.id, {
                                visibility: "restricted",
                                accessUsernames: parsedUsers,
                              });
                            }}
                            className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                          >
                            {siteConfig.knowledge.restrictButton}
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}

            {!isLoading && documents.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-slate-500"
                >
                  {hasActiveFilters
                    ? siteConfig.knowledge.emptyFilteredState
                    : siteConfig.knowledge.emptyState}
                </td>
              </tr>
            )}

            {isLoading && (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-slate-500"
                >
                  Loading...
                </td>
              </tr>
            )}
          </tbody>
        </table>
        {documents.length > PAGE_SIZE && !hasMoreDocuments && (
          <div className="mt-4 flex justify-end">
            <button
              type="button"
              onClick={() => setVisibleCount(PAGE_SIZE)}
              className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
            >
              {siteConfig.knowledge.showLessButton}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
