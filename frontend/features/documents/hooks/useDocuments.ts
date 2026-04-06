"use client";

import { useCallback, useDeferredValue, useEffect, useRef, useState } from "react";
import {
  deleteDocument,
  DocumentFacetOption,
  DocumentItem,
  DocumentPreview,
  getDocumentPreview,
  getDocuments,
  processDocument,
  reprocessAllDocuments,
  retryIncompleteDocuments,
  updateDocumentSecurity,
  uploadDocument,
} from "../../../lib/api";
import { siteConfig } from "../../../config/site";

export function useDocuments() {
  const PAGE_LIMIT = 200;
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMoreDocuments, setHasMoreDocuments] = useState(false);
  const [availableDocumentTypes, setAvailableDocumentTypes] = useState<string[]>([]);
  const [availableSources, setAvailableSources] = useState<string[]>([]);
  const [availableTypeFacets, setAvailableTypeFacets] = useState<DocumentFacetOption[]>([]);
  const [availableSourceFacets, setAvailableSourceFacets] = useState<DocumentFacetOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isRetryingIncomplete, setIsRetryingIncomplete] = useState(false);
  const [isReprocessingAll, setIsReprocessingAll] = useState(false);
  const [processingDocumentId, setProcessingDocumentId] = useState("");
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [sortOrder, setSortOrder] = useState("newest");
  const previewRequestKeyRef = useRef("");
  const refreshDocumentsRef = useRef<(options?: { background?: boolean }) => Promise<void>>(
    async () => {}
  );
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const refreshDocuments = useCallback(async (options?: { background?: boolean }) => {
    const isBackgroundRefresh = options?.background ?? false;
    if (!isBackgroundRefresh) {
      setIsLoading(true);
    }
    setError("");

    try {
      const payload = await getDocuments({
        limit: PAGE_LIMIT,
        offset: 0,
        query: deferredSearchQuery,
        statusFilter,
        typeFilter,
        sourceFilter,
        sortOrder,
      });
      setDocuments(payload.documents);
      setTotalCount(payload.total_count);
      setHasMoreDocuments(payload.has_more);
      setAvailableDocumentTypes(payload.available_types);
      setAvailableSources(payload.available_sources);
      setAvailableTypeFacets(payload.available_type_facets);
      setAvailableSourceFacets(payload.available_source_facets);
    } catch {
      setError(siteConfig.knowledge.messages.loadError);
    } finally {
      if (!isBackgroundRefresh) {
        setIsLoading(false);
      }
    }
  }, [PAGE_LIMIT, deferredSearchQuery, sortOrder, sourceFilter, statusFilter, typeFilter]);

  refreshDocumentsRef.current = refreshDocuments;

  async function addDocuments(files: File[]) {
    if (files.length === 0) {
      setError(siteConfig.knowledge.messages.noFileSelected);
      return false;
    }

    setIsUploading(true);
    setError("");
    setStatusMessage("");

    try {
      const uploadedDocuments: DocumentItem[] = [];

      for (const file of files) {
        const document = await uploadDocument(file);
        uploadedDocuments.push(document);
      }

      setDocuments((current) => [...uploadedDocuments.reverse(), ...current]);
      setTotalCount((current) => current + uploadedDocuments.length);
      setStatusMessage(
        uploadedDocuments.length > 1
          ? `${uploadedDocuments.length} ${siteConfig.knowledge.messages.uploadQueuedPlural}`
          : siteConfig.knowledge.messages.uploadQueued
      );
      return true;
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : siteConfig.knowledge.messages.uploadError;
      setError(message);
      return false;
    } finally {
      setIsUploading(false);
    }
  }

  async function removeDocument(documentId: string) {
    setError("");
    setStatusMessage("");

    try {
      await deleteDocument(documentId);
      const existed = documents.some((document) => document.id === documentId);
      setDocuments((current) =>
        current.filter((document) => document.id !== documentId)
      );
      if (existed) {
        setTotalCount((count) => Math.max(0, count - 1));
      }
    } catch {
      setError(siteConfig.knowledge.messages.deleteError);
    }
  }

  async function reprocessDocument(documentId: string) {
    setError("");
    setStatusMessage("");
    setProcessingDocumentId(documentId);

    try {
      const updatedDocument = await processDocument(documentId);
      setDocuments((current) =>
        current.map((document) =>
          document.id === documentId ? updatedDocument : document
        )
      );
      setStatusMessage(siteConfig.knowledge.messages.processQueued);
    } catch {
      setError(siteConfig.knowledge.messages.processError);
    } finally {
      setProcessingDocumentId("");
    }
  }

  async function setDocumentVisibility(
    documentId: string,
    visibility: "standard" | "hidden"
  ) {
    setError("");
    setStatusMessage("");

    try {
      const updatedDocument = await updateDocumentSecurity(documentId, visibility);
      setDocuments((current) => {
        if (
          visibility === "hidden" &&
          !current.some((document) => document.id === documentId)
        ) {
          return current;
        }

        return current
          .map((document) =>
            document.id === documentId ? updatedDocument : document
          )
          .filter((document) => document.id !== documentId || visibility !== "hidden" || updatedDocument.visibility === "hidden");
      });
      if (preview?.document.id === documentId) {
        setPreview((current) =>
          current
            ? {
                ...current,
                document: updatedDocument,
              }
            : current
        );
      }
      setStatusMessage(
        visibility === "hidden"
          ? siteConfig.knowledge.messages.hideSuccess
          : siteConfig.knowledge.messages.unhideSuccess
      );
      await refreshDocumentsRef.current({ background: true });
    } catch {
      setError(siteConfig.knowledge.messages.visibilityError);
    }
  }

  async function retryIncompleteIndexing() {
    setError("");
    setStatusMessage("");
    setIsRetryingIncomplete(true);

    try {
      const payload = await retryIncompleteDocuments();
      if (payload.retried_count === 0) {
        setStatusMessage(siteConfig.knowledge.messages.retryIncompleteNoop);
        return;
      }

      setDocuments((current) => {
        const updates = new Map(
          payload.documents.map((document) => [document.id, document])
        );

        return current.map((document) => updates.get(document.id) ?? document);
      });
      setStatusMessage(siteConfig.knowledge.messages.retryIncompleteSuccess);
    } catch {
      setError(siteConfig.knowledge.messages.retryIncompleteError);
    } finally {
      setIsRetryingIncomplete(false);
    }
  }

  async function reprocessEveryDocument() {
    setError("");
    setStatusMessage("");
    setIsReprocessingAll(true);

    try {
      const payload = await reprocessAllDocuments();
      if ((payload.queued_count ?? 0) === 0) {
        setStatusMessage(siteConfig.knowledge.messages.reprocessAllNoop);
        return;
      }

      setDocuments((current) => {
        const updates = new Map(
          payload.documents.map((document) => [document.id, document])
        );

        return current.map((document) => updates.get(document.id) ?? document);
      });
      setStatusMessage(siteConfig.knowledge.messages.reprocessAllQueued);
    } catch {
      setError(siteConfig.knowledge.messages.reprocessAllError);
    } finally {
      setIsReprocessingAll(false);
    }
  }

  async function reprocessDocuments(documentIds: string[]) {
    for (const documentId of documentIds) {
      await reprocessDocument(documentId);
    }
  }

  async function openDocumentPreview(
    documentId: string,
    focusChunkIndex?: number
  ) {
    const requestKey = `${documentId}:${focusChunkIndex ?? "default"}`;
    if (
      previewRequestKeyRef.current === requestKey &&
      (isPreviewLoading ||
        (preview?.document.id === documentId &&
          preview.focused_chunk_index === (focusChunkIndex ?? null)))
    ) {
      return;
    }

    previewRequestKeyRef.current = requestKey;
    setPreview((current) =>
      current?.document.id === documentId &&
      current.focused_chunk_index === (focusChunkIndex ?? null)
        ? current
        : null
    );
    setPreviewError("");
    setIsPreviewLoading(true);

    try {
      const nextPreview = await getDocumentPreview(documentId, focusChunkIndex);
      if (previewRequestKeyRef.current !== requestKey) {
        return;
      }
      setPreview(nextPreview);
    } catch {
      if (previewRequestKeyRef.current !== requestKey) {
        return;
      }
      setPreviewError(siteConfig.knowledge.messages.previewError);
    } finally {
      if (previewRequestKeyRef.current === requestKey) {
        setIsPreviewLoading(false);
      }
    }
  }

  function closeDocumentPreview() {
    previewRequestKeyRef.current = "";
    setPreview(null);
    setPreviewError("");
    setIsPreviewLoading(false);
  }

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  const hasActiveProcessing = documents.some(
    (document) =>
      document.processing_status === "pending" ||
      (document.processing_status === "processed" &&
        document.indexing_status === "pending")
  );

  useEffect(() => {
    if (!hasActiveProcessing) {
      return;
    }

    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== "visible") {
        return;
      }
      void refreshDocumentsRef.current({ background: true });
    }, 4000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [hasActiveProcessing]);

  return {
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
    error,
    statusMessage,
    preview,
    previewError,
    isPreviewLoading,
    hasActiveProcessing,
    refreshDocuments,
    setSearchQuery,
    setStatusFilter,
    setTypeFilter,
    setSourceFilter,
    setSortOrder,
    addDocuments,
    removeDocument,
    reprocessDocument,
    setDocumentVisibility,
    retryIncompleteIndexing,
    reprocessEveryDocument,
    reprocessDocuments,
    openDocumentPreview,
    closeDocumentPreview,
  };
}
