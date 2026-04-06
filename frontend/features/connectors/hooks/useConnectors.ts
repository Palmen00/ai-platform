"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  browseConnector,
  ConnectorBrowseInput,
  ConnectorBrowseResponse,
  ConnectorCreateInput,
  ConnectorManifest,
  ConnectorSyncResponse,
  createConnector,
  deleteConnector,
  getConnectors,
  syncConnector,
  ConnectorUpdateInput,
  updateConnector,
} from "../../../lib/api";
import { siteConfig } from "../../../config/site";

const CONNECTORS_CACHE_KEY = "local-ai-connectors-cache-v1";

function normalizeConnector(connector: ConnectorManifest): ConnectorManifest {
  return {
    ...connector,
    document_visibility: connector.document_visibility ?? "standard",
    access_usernames: connector.access_usernames ?? [],
  };
}

function readCachedConnectors(): ConnectorManifest[] {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const rawValue = window.localStorage.getItem(CONNECTORS_CACHE_KEY);
    if (!rawValue) {
      return [];
    }

    const payload = JSON.parse(rawValue);
    return Array.isArray(payload)
      ? (payload as ConnectorManifest[]).map(normalizeConnector)
      : [];
  } catch {
    return [];
  }
}

function writeCachedConnectors(connectors: ConnectorManifest[]) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(CONNECTORS_CACHE_KEY, JSON.stringify(connectors));
  } catch {
    // Ignore local cache write failures and keep the live state authoritative.
  }
}

export function useConnectors(enabled = true) {
  const [connectors, setConnectors] = useState<ConnectorManifest[]>(() =>
    readCachedConnectors()
  );
  const [isLoading, setIsLoading] = useState(
    () => enabled && readCachedConnectors().length === 0
  );
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [savingConnectorId, setSavingConnectorId] = useState("");
  const [deletingConnectorId, setDeletingConnectorId] = useState("");
  const [syncingConnectorId, setSyncingConnectorId] = useState("");
  const [previewingConnectorId, setPreviewingConnectorId] = useState("");
  const [isBrowsing, setIsBrowsing] = useState(false);
  const [error, setError] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [lastSyncResult, setLastSyncResult] = useState<ConnectorSyncResponse | null>(
    null
  );
  const [lastBrowseResult, setLastBrowseResult] =
    useState<ConnectorBrowseResponse | null>(null);
  const retryTimeoutRef = useRef<number | null>(null);

  function clearRetryTimeout() {
    if (retryTimeoutRef.current !== null) {
      window.clearTimeout(retryTimeoutRef.current);
      retryTimeoutRef.current = null;
    }
  }

  const refreshConnectors = useCallback(async (options?: {
    background?: boolean;
    retryAttempt?: number;
  }) => {
    if (!enabled) {
      return;
    }

    const hasExistingConnectors = connectors.length > 0;
    const background = options?.background ?? hasExistingConnectors;
    const retryAttempt = options?.retryAttempt ?? 0;

    clearRetryTimeout();
    setError("");

    if (background && hasExistingConnectors) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    try {
      const payload = await getConnectors();
      const nextConnectors = payload.connectors.map(normalizeConnector);
      setConnectors(nextConnectors);
      writeCachedConnectors(nextConnectors);
    } catch {
      setError(siteConfig.connectors.messages.loadError);
      if (retryAttempt < 2 && typeof window !== "undefined") {
        retryTimeoutRef.current = window.setTimeout(() => {
          void refreshConnectors({
            background: true,
            retryAttempt: retryAttempt + 1,
          });
        }, 2000 * (retryAttempt + 1));
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [connectors.length, enabled]);

  async function addConnector(payload: ConnectorCreateInput) {
    setIsCreating(true);
    setError("");
    setStatusMessage("");

    try {
      const connector = await createConnector(payload);
      setConnectors((current) => [normalizeConnector(connector), ...current]);
      setStatusMessage(siteConfig.connectors.messages.createSuccess);
      return connector;
    } catch (error) {
      setError(
        error instanceof Error && error.message
          ? error.message
          : siteConfig.connectors.messages.createError
      );
      return null;
    } finally {
      setIsCreating(false);
    }
  }

  async function saveConnector(
    connectorId: string,
    payload: ConnectorUpdateInput
  ) {
    setSavingConnectorId(connectorId);
    setError("");
    setStatusMessage("");

    try {
      const connector = await updateConnector(connectorId, payload);
      setConnectors((current) => {
        const next = current.map((item) =>
          item.id === connector.id ? normalizeConnector(connector) : item
        );
        writeCachedConnectors(next);
        return next;
      });
      setStatusMessage(siteConfig.connectors.messages.updateSuccess);
      return connector;
    } catch (error) {
      setError(
        error instanceof Error && error.message
          ? error.message
          : siteConfig.connectors.messages.updateError
      );
      return null;
    } finally {
      setSavingConnectorId("");
    }
  }

  async function removeConnector(connectorId: string) {
    setDeletingConnectorId(connectorId);
    setError("");
    setStatusMessage("");

    try {
      await deleteConnector(connectorId);
      setConnectors((current) => {
        const next = current.filter((connector) => connector.id !== connectorId);
        writeCachedConnectors(next);
        return next;
      });
      setLastSyncResult((current) =>
        current?.connector_id === connectorId ? null : current
      );
      setStatusMessage(siteConfig.connectors.messages.deleteSuccess);
      return true;
    } catch {
      setError(siteConfig.connectors.messages.deleteError);
      return false;
    } finally {
      setDeletingConnectorId("");
    }
  }

  async function runSync(connectorId: string) {
    setSyncingConnectorId(connectorId);
    setError("");
    setStatusMessage("");
    setLastSyncResult(null);

    try {
      const result = await syncConnector(connectorId);
      setLastSyncResult(result);
      await refreshConnectors();
      setStatusMessage(
        `${siteConfig.connectors.messages.syncSuccessPrefix} ${result.imported_count} imported, ${result.updated_count} updated, ${result.skipped_count} skipped.`
      );
      return result;
    } catch {
      setError(siteConfig.connectors.messages.syncError);
      return null;
    } finally {
      setSyncingConnectorId("");
    }
  }

  async function previewSync(connectorId: string) {
    setPreviewingConnectorId(connectorId);
    setError("");
    setStatusMessage("");
    setLastSyncResult(null);

    try {
      const result = await syncConnector(connectorId, { dryRun: true });
      setLastSyncResult(result);
      setStatusMessage(
        `Preview ready. ${result.imported_count} would import, ${result.updated_count} would update, ${result.skipped_count} would skip.`
      );
      return result;
    } catch {
      setError(siteConfig.connectors.messages.syncError);
      return null;
    } finally {
      setPreviewingConnectorId("");
    }
  }

  async function browseFolders(payload: ConnectorBrowseInput) {
    setIsBrowsing(true);
    setError("");
    setStatusMessage("");
    setLastBrowseResult(null);

    try {
      const result = await browseConnector(payload);
      setLastBrowseResult(result);
      setStatusMessage(`Folder list ready. ${result.folders.length} folders found.`);
      return result;
    } catch {
      setError(siteConfig.connectors.messages.browseError);
      return null;
    } finally {
      setIsBrowsing(false);
    }
  }

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false);
      return;
    }

    void refreshConnectors({ background: connectors.length > 0 });
  }, [connectors.length, enabled, refreshConnectors]);

  useEffect(() => {
    writeCachedConnectors(connectors);
  }, [connectors]);

  useEffect(() => {
    return () => {
      clearRetryTimeout();
    };
  }, []);

  return {
    connectors,
    isLoading,
    isRefreshing,
    isCreating,
    savingConnectorId,
    deletingConnectorId,
    syncingConnectorId,
    previewingConnectorId,
    isBrowsing,
    error,
    statusMessage,
    lastSyncResult,
    lastBrowseResult,
    refreshConnectors,
    addConnector,
    saveConnector,
    removeConnector,
    runSync,
    previewSync,
    browseFolders,
  };
}
