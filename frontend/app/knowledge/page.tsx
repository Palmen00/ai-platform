"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "../../components/AppShell";
import { siteConfig } from "../../config/site";
import { DocumentList } from "../../features/documents/components/DocumentList";
import { DocumentPreviewPanel } from "../../features/documents/components/DocumentPreviewPanel";
import { DocumentUploadForm } from "../../features/documents/components/DocumentUploadForm";
import { useDocuments } from "../../features/documents/hooks/useDocuments";
import { AuthStatusResponse, getAuthStatus } from "../../lib/api";

function KnowledgePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isFileTypesModalOpen, setIsFileTypesModalOpen] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const requestedPreviewId = searchParams.get("preview") ?? "";
  const requestedChunk = searchParams.get("chunk");
  const openedPreviewKeyRef = useRef("");
  const {
    documents,
    totalCount,
    hasMoreDocuments,
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
    isUploading,
    isRetryingIncomplete,
    isReprocessingAll,
    processingDocumentId,
    hasActiveProcessing,
    error,
    statusMessage,
    uploadWarnings,
    preview,
    previewError,
    isPreviewLoading,
    refreshDocuments,
    setSearchQuery,
    setStatusFilter,
    setTypeFilter,
    setSourceFilter,
    setSortOrder,
    addDocuments,
    removeDocument,
    reprocessDocument,
    reprocessEveryDocument,
    retryIncompleteIndexing,
    openDocumentPreview,
    closeDocumentPreview,
    setDocumentVisibility,
  } = useDocuments();

  useEffect(() => {
    let isMounted = true;

    async function loadAuthStatus() {
      try {
        const nextAuthStatus = await getAuthStatus();
        if (isMounted) {
          setAuthStatus(nextAuthStatus);
        }
      } catch {
        if (isMounted) {
          setAuthStatus(null);
        }
      } finally {
        if (isMounted) {
          setIsAuthLoading(false);
        }
      }
    }

    void loadAuthStatus();

    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    if (!requestedPreviewId) {
      openedPreviewKeyRef.current = "";
      return;
    }

    const parsedChunk =
      requestedChunk !== null && requestedChunk !== ""
        ? Number(requestedChunk)
        : undefined;
    const previewKey = `${requestedPreviewId}:${parsedChunk ?? "default"}`;
    if (openedPreviewKeyRef.current === previewKey) {
      return;
    }

    openedPreviewKeyRef.current = previewKey;
    void openDocumentPreview(
      requestedPreviewId,
      Number.isFinite(parsedChunk) ? parsedChunk : undefined
    );
  }, [openDocumentPreview, requestedChunk, requestedPreviewId]);

  const hasIncompleteDocuments = documents.some(
    (document) =>
      document.processing_status === "processed" &&
      document.indexing_status !== "indexed"
  );

  const fileTypeSummary = useMemo(() => {
    const counts = new Map<string, number>();

    documents.forEach((document) => {
      const originalName = document.original_name.trim();
      const extensionMatch = /\.([a-z0-9]+)$/i.exec(originalName);
      const normalizedType = extensionMatch?.[1]
        ? extensionMatch[1].toUpperCase()
        : document.content_type
            .split("/")
            .pop()
            ?.replace(/[^a-z0-9]+/gi, " ")
            .trim()
            .toUpperCase() || "UNKNOWN";

      counts.set(normalizedType, (counts.get(normalizedType) ?? 0) + 1);
    });

    return Array.from(counts.entries())
      .map(([type, count]) => ({ type, count }))
      .sort((left, right) => {
        if (right.count !== left.count) {
          return right.count - left.count;
        }

        return left.type.localeCompare(right.type);
      });
  }, [documents]);

  const canManageVisibility =
    authStatus === null
      ? false
      : !authStatus.auth_enabled || authStatus.role === "admin";
  const canManageDocuments =
    authStatus === null
      ? false
      : !authStatus.auth_enabled || authStatus.role === "admin";
  const requiresSignIn = !!authStatus?.auth_enabled && !authStatus?.authenticated;

  if (isAuthLoading) {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-10 text-sm text-slate-600 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8">
          Loading knowledge...
        </section>
      </AppShell>
    );
  }

  if (requiresSignIn) {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8 md:py-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {siteConfig.knowledge.title}
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
            Sign in to open Knowledge
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
            This workspace requires a signed-in account before documents can be listed or searched. Use Settings to sign in, then come back here.
          </p>
          <Link
            href="/login?next=/knowledge"
            className="mt-5 inline-flex rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Open Login
          </Link>
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell contentClassName="p-4 md:p-6 xl:p-8">
      <div className="space-y-6">
        <section className="flex flex-col gap-4 rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:flex-row md:items-end md:justify-between md:px-8 md:py-8">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              {siteConfig.knowledge.title}
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
              {siteConfig.knowledge.title}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-600">
              {siteConfig.knowledge.subtitle}
            </p>
            <Link
              href="/settings"
              className="mt-3 inline-flex text-sm font-medium text-slate-600 underline decoration-slate-300 underline-offset-4 transition hover:text-slate-900 hover:decoration-slate-500"
            >
              {siteConfig.knowledge.manageConnectorsLink}
            </Link>
            <button
              type="button"
              onClick={() => setIsFileTypesModalOpen(true)}
              className="mt-3 inline-flex w-fit items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-100 hover:text-slate-900"
            >
              {siteConfig.knowledge.totalFilesButton.replace(
                "{count}",
                totalCount.toString()
              )}
            </button>
          </div>

          <div className="flex flex-wrap gap-2">
            {canManageDocuments && documents.length > 0 && (
              <button
                onClick={() => void reprocessEveryDocument()}
                disabled={isReprocessingAll}
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isReprocessingAll
                  ? siteConfig.knowledge.reprocessingAllButton
                  : siteConfig.knowledge.reprocessAllButton}
              </button>
            )}

            {canManageDocuments && hasIncompleteDocuments && (
              <button
                onClick={() => void retryIncompleteIndexing()}
                disabled={isRetryingIncomplete}
                className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-medium text-amber-800 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isRetryingIncomplete
                  ? siteConfig.knowledge.retryingIncompleteButton
                  : siteConfig.knowledge.retryIncompleteButton}
              </button>
            )}

            <button
              onClick={() => void refreshDocuments()}
              className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            >
              {siteConfig.knowledge.refreshButton}
            </button>
          </div>
        </section>

        {(error || statusMessage) && (
          <div
            className={`rounded-2xl px-4 py-3 text-sm shadow-sm ${
              error
                ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
            }`}
          >
            {error || statusMessage}
          </div>
        )}

        {uploadWarnings.length > 0 && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-sm">
            <div className="font-semibold">
              {siteConfig.knowledge.messages.duplicateUploadTitle}
            </div>
            <p className="mt-1 text-amber-800">
              {siteConfig.knowledge.messages.duplicateUploadHint}
            </p>
            <div className="mt-3 space-y-2">
              {uploadWarnings.slice(0, 4).map((warning, index) => (
                <div
                  key={`${warning.type}-${index}`}
                  className="rounded-xl border border-amber-200/80 bg-white/70 px-3 py-2"
                >
                  <div>{warning.message}</div>
                  {warning.matches.length > 0 && (
                    <div className="mt-1 text-xs text-amber-700">
                      Matches:{" "}
                      {warning.matches
                        .slice(0, 3)
                        .map((match) => match.document_name)
                        .join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {hasActiveProcessing && (
          <div className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-amber-200">
            {siteConfig.knowledge.activeProcessingNotice}
          </div>
        )}

        <DocumentUploadForm
          isUploading={isUploading}
          disabled={!canManageDocuments}
          disabledMessage="Viewer accounts can explore Knowledge, but only admins can upload or reprocess files."
          onUpload={addDocuments}
        />
        <DocumentList
          documents={documents}
          totalCount={totalCount}
          hasMoreOnServer={hasMoreDocuments}
          availableDocumentTypes={availableDocumentTypes}
          availableSources={availableSources}
          availableTypeFacets={availableTypeFacets}
          availableSourceFacets={availableSourceFacets}
          searchQuery={searchQuery}
          statusFilter={statusFilter}
          typeFilter={typeFilter}
          sourceFilter={sourceFilter}
          sortOrder={sortOrder}
          isLoading={isLoading}
          processingDocumentId={processingDocumentId}
          isReprocessingAll={isReprocessingAll}
          onSearchChange={setSearchQuery}
          onStatusFilterChange={setStatusFilter}
          onTypeFilterChange={setTypeFilter}
          onSourceFilterChange={setSourceFilter}
          onSortChange={setSortOrder}
          onDelete={removeDocument}
          onReprocess={reprocessDocument}
          onPreview={openDocumentPreview}
          canManageDocuments={canManageDocuments}
          canManageVisibility={canManageVisibility}
          onSetVisibility={setDocumentVisibility}
        />
        <DocumentPreviewPanel
          preview={preview}
          isLoading={isPreviewLoading}
          error={previewError}
          onClose={() => {
            closeDocumentPreview();
            if (requestedPreviewId) {
              router.replace("/knowledge");
            }
          }}
          onUseInChat={(documentId) => {
            closeDocumentPreview();
            openedPreviewKeyRef.current = "";
            window.setTimeout(() => {
              router.push(`/chat?documents=${documentId}`);
            }, 0);
          }}
        />
        {isFileTypesModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-4 py-8 backdrop-blur-sm">
            <div className="w-full max-w-lg rounded-[2rem] border border-slate-200/80 bg-white p-6 shadow-[0_28px_70px_rgba(15,23,42,0.20)]">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                    {siteConfig.knowledge.title}
                  </p>
                  <h3 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                    {siteConfig.knowledge.fileTypesModalTitle}
                  </h3>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {siteConfig.knowledge.fileTypesModalSubtitle}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setIsFileTypesModalOpen(false)}
                  className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100 hover:text-slate-900"
                >
                  {siteConfig.knowledge.fileTypesModalClose}
                </button>
              </div>

              <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50/70">
                <div className="grid grid-cols-[1fr_auto] gap-3 border-b border-slate-200 px-4 py-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                  <span>{siteConfig.knowledge.fileTypesTypeLabel}</span>
                  <span>{siteConfig.knowledge.fileTypesCountLabel}</span>
                </div>

                {fileTypeSummary.length > 0 ? (
                  <div className="max-h-[55vh] overflow-y-auto">
                    {fileTypeSummary.map(({ type, count }) => (
                      <div
                        key={type}
                        className="grid grid-cols-[1fr_auto] gap-3 border-b border-slate-200/70 px-4 py-3 text-sm text-slate-700 last:border-b-0"
                      >
                        <span className="font-medium text-slate-900">{type}</span>
                        <span>{count}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="px-4 py-6 text-sm text-slate-500">
                    {siteConfig.knowledge.fileTypesEmptyState}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

export default function KnowledgePage() {
  return (
    <Suspense
      fallback={
        <AppShell contentClassName="p-4 md:p-6 xl:p-8">
          <section className="rounded-[1.25rem] border border-slate-200/80 bg-white/92 px-5 py-6 text-sm text-slate-600 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
            Loading knowledge...
          </section>
        </AppShell>
      }
    >
      <KnowledgePageContent />
    </Suspense>
  );
}
