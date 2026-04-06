"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { siteConfig } from "../../config/site";
import { ConnectorManager } from "../../features/connectors/components/ConnectorManager";
import { useConnectors } from "../../features/connectors/hooks/useConnectors";
import {
  AuthStatusResponse,
  cleanupStorageTargets,
  getAuthStatus,
  getBackupExport,
  importBackup,
  loginAdmin,
  logoutAdmin,
  getModels,
  getRuntimeSettings,
  getSystemStatus,
  BackupExportPayload,
  BackupImportResponse,
  CleanupTargetResult,
  ModelItem,
  RuntimeSettings,
  StorageUsageItem,
  SystemStatusResponse,
  updateRuntimeSettings,
} from "../../lib/api";

const initialRuntimeSettings: RuntimeSettings = {
  ollama_base_url: "",
  ollama_default_model: "",
  ollama_embed_model: "",
  qdrant_url: "",
  retrieval_limit: 4,
  retrieval_min_score: 0.45,
  document_chunk_size: 1000,
  document_chunk_overlap: 150,
};

type SettingsTab =
  | "overview"
  | "storage"
  | "runtime"
  | "connectors"
  | "security"
  | "debug"
  | "models";
type StorageSort = "largest" | "smallest" | "name";
type StorageFilter = "all" | "cleanable" | "persistent";

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("overview");
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(
    null
  );
  const [systemStatusError, setSystemStatusError] = useState("");
  const [models, setModels] = useState<ModelItem[]>([]);
  const [runtimeSettings, setRuntimeSettings] =
    useState<RuntimeSettings>(initialRuntimeSettings);
  const [runtimeError, setRuntimeError] = useState("");
  const [runtimeMessage, setRuntimeMessage] = useState("");
  const [isSavingRuntime, setIsSavingRuntime] = useState(false);
  const [storageSort, setStorageSort] = useState<StorageSort>("largest");
  const [storageFilter, setStorageFilter] = useState<StorageFilter>("all");
  const [cleanupError, setCleanupError] = useState("");
  const [cleanupMessage, setCleanupMessage] = useState("");
  const [cleanupPendingKey, setCleanupPendingKey] = useState<string | null>(null);
  const [exportError, setExportError] = useState("");
  const [isExporting, setIsExporting] = useState(false);
  const [importError, setImportError] = useState("");
  const [importMessage, setImportMessage] = useState("");
  const [isImporting, setIsImporting] = useState(false);
  const [selectedBackupFile, setSelectedBackupFile] = useState<File | null>(null);
  const {
    connectors,
    isLoading: areConnectorsLoading,
    isRefreshing: areConnectorsRefreshing,
    isCreating: isCreatingConnector,
    savingConnectorId,
    deletingConnectorId,
    syncingConnectorId,
    previewingConnectorId,
    isBrowsing,
    error: connectorsError,
    statusMessage: connectorsStatusMessage,
    lastBrowseResult,
    lastSyncResult,
    addConnector,
    saveConnector,
    removeConnector,
    refreshConnectors,
    runSync,
    previewSync,
    browseFolders,
  } = useConnectors(activeTab === "connectors");

  const isAdminAuthRequired =
    !!authStatus?.auth_enabled && !!authStatus?.auth_configured;
  const isAdminUnlocked = !isAdminAuthRequired || !!authStatus?.authenticated;

  async function loadSystemOverview() {
    try {
      const status = await getSystemStatus();
      setSystemStatus(status);
      setSystemStatusError("");
    } catch {
      setSystemStatus(null);
      setSystemStatusError(siteConfig.settings.statusLoadError);
    }

    try {
      const modelsResponse = await getModels();
      setModels(modelsResponse.models);
    } catch {
      setModels([]);
    }
  }

  useEffect(() => {
    let isMounted = true;

    async function loadInitialState() {
      let nextAuthStatus: AuthStatusResponse | null = null;
      try {
        nextAuthStatus = await getAuthStatus();
        if (isMounted) {
          setAuthStatus(nextAuthStatus);
          setAuthError("");
        }
      } catch {
        if (isMounted) {
          setAuthError(siteConfig.settings.auth.loginError);
        }
      } finally {
        if (isMounted) {
          setIsAuthLoading(false);
        }
      }

      try {
        const status = await getSystemStatus();
        if (isMounted) {
          setSystemStatus(status);
          setSystemStatusError("");
        }
      } catch {
        if (isMounted) {
          setSystemStatus(null);
          setSystemStatusError(siteConfig.settings.statusLoadError);
        }
      }

      try {
        const modelsResponse = await getModels();
        if (isMounted) {
          setModels(modelsResponse.models);
        }
      } catch {
        if (isMounted) {
          setModels([]);
        }
      }

      try {
        const shouldLoadProtectedRuntime =
          !nextAuthStatus?.auth_enabled ||
          !nextAuthStatus?.auth_configured ||
          !!nextAuthStatus?.authenticated;
        if (shouldLoadProtectedRuntime) {
          const settings = await getRuntimeSettings();
          if (isMounted) {
            setRuntimeSettings(settings);
          }
        }
      } catch {
        if (isMounted) {
          setRuntimeError(siteConfig.settings.loadError);
        }
      }
    }

    void loadInitialState();

    const intervalId = window.setInterval(() => {
      if (isMounted) {
        void loadSystemOverview();
      }
    }, 30000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  async function refreshProtectedState() {
    try {
      const nextRuntimeSettings = await getRuntimeSettings();
      setRuntimeSettings(nextRuntimeSettings);
      setRuntimeError("");
    } catch {
      setRuntimeError(siteConfig.settings.loadError);
    }
  }

  async function handleAdminLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    setIsLoggingIn(true);

    try {
      const nextAuthStatus = await loginAdmin(adminPassword);
      setAuthStatus(nextAuthStatus);
      setAdminPassword("");
      await refreshProtectedState();
    } catch {
      setAuthError(siteConfig.settings.auth.loginError);
    } finally {
      setIsLoggingIn(false);
    }
  }

  async function handleAdminLogout() {
    await logoutAdmin();
    setAuthStatus((current) =>
      current
        ? {
            ...current,
            authenticated: false,
            session_expires_at: null,
          }
        : current
    );
  }

  function updateField<K extends keyof RuntimeSettings>(
    key: K,
    value: RuntimeSettings[K]
  ) {
    setRuntimeSettings((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function buildCleanupMessage(results: CleanupTargetResult[], removedBytes: number) {
    if (results.length === 1) {
      return `${results[0].label} cleaned. ${formatBytes(removedBytes)} removed.`;
    }

    return `Safe cleanup completed. ${formatBytes(removedBytes)} removed.`;
  }

  async function handleCleanup(targets: string[], confirmMessage: string) {
    if (!window.confirm(confirmMessage)) {
      return;
    }

    setCleanupError("");
    setCleanupMessage("");
    setCleanupPendingKey(targets.length > 1 ? "all" : targets[0]);

    try {
      const payload = await cleanupStorageTargets(targets);
      setCleanupMessage(
        buildCleanupMessage(payload.cleaned_targets, payload.removed_bytes)
      );
      await loadSystemOverview();
    } catch {
      setCleanupError(siteConfig.settings.storageControls.cleanupError);
    } finally {
      setCleanupPendingKey(null);
    }
  }

  async function handleRuntimeSave(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRuntimeError("");
    setRuntimeMessage("");
    setIsSavingRuntime(true);

    try {
      const savedSettings = await updateRuntimeSettings(runtimeSettings);
      setRuntimeSettings(savedSettings);
      setRuntimeMessage(siteConfig.settings.savedMessage);
    } catch {
      setRuntimeError(siteConfig.settings.saveError);
    } finally {
      setIsSavingRuntime(false);
    }
  }

  async function handleExportBackup() {
    setExportError("");
    setIsExporting(true);

    try {
      const payload = await getBackupExport();
      const blob = new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      });
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `local-ai-backup-${new Date()
        .toISOString()
        .replace(/[:.]/g, "-")}.json`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch {
      setExportError(siteConfig.settings.exportError);
    } finally {
      setIsExporting(false);
    }
  }

  function buildImportMessage(payload: BackupImportResponse) {
    return `${payload.message} Imported conversations: ${payload.imported_conversations}. Skipped documents: ${payload.skipped_documents}.`;
  }

  async function handleImportBackup() {
    if (!selectedBackupFile) {
      setImportError(siteConfig.settings.importNoFileLabel);
      setImportMessage("");
      return;
    }

    setImportError("");
    setImportMessage("");
    setIsImporting(true);

    try {
      const fileText = await selectedBackupFile.text();
      const payload = JSON.parse(fileText) as BackupExportPayload;
      const response = await importBackup(payload);
      setImportMessage(buildImportMessage(response));
      setSelectedBackupFile(null);
      await loadSystemOverview();
      try {
        const settings = await getRuntimeSettings();
        setRuntimeSettings(settings);
      } catch {
        // Keep current state if runtime settings reload fails after import.
      }
    } catch {
      setImportError(siteConfig.settings.importError);
    } finally {
      setIsImporting(false);
    }
  }

  const tabs: Array<{ id: SettingsTab; label: string }> = [
    { id: "overview", label: siteConfig.settings.tabs.overview },
    { id: "storage", label: siteConfig.settings.tabs.storage },
    { id: "runtime", label: siteConfig.settings.tabs.runtime },
    { id: "connectors", label: siteConfig.settings.tabs.connectors },
    { id: "security", label: siteConfig.settings.tabs.security },
    { id: "debug", label: siteConfig.settings.tabs.debug },
    { id: "models", label: siteConfig.settings.tabs.models },
  ];

  const statusLabels = siteConfig.settings.statusLabels;
  const overallStatusLabel = systemStatus
    ? statusLabels[
        (systemStatus.status as keyof typeof siteConfig.settings.statusLabels) ??
          "unknown"
      ] ?? systemStatus.status
    : statusLabels.unknown;
  const storageItems = systemStatus?.storage.usage_items ?? [];

  const filteredStorageItems = storageItems
    .filter((item) => {
      if (storageFilter === "cleanable") {
        return item.cleanable;
      }

      if (storageFilter === "persistent") {
        return !item.cleanable;
      }

      return true;
    })
    .sort((left, right) => compareStorageItems(left, right, storageSort));
  const cleanableStorageItems = storageItems.filter((item) => item.cleanable);

  function formatBytes(sizeBytes: number) {
    if (sizeBytes < 1024) {
      return `${sizeBytes} B`;
    }

    const units = ["KB", "MB", "GB", "TB"];
    let value = sizeBytes / 1024;
    let unitIndex = 0;

    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex += 1;
    }

    return `${value.toFixed(1)} ${units[unitIndex]}`;
  }

  function compareStorageItems(
    left: StorageUsageItem,
    right: StorageUsageItem,
    sort: StorageSort
  ) {
    if (sort === "smallest") {
      return left.size_bytes - right.size_bytes;
    }

    if (sort === "name") {
      return left.label.localeCompare(right.label);
    }

    return right.size_bytes - left.size_bytes;
  }

  if (isAuthLoading) {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-10 text-sm text-slate-600 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8">
          Loading settings...
        </section>
      </AppShell>
    );
  }

  if (isAdminAuthRequired && !isAdminUnlocked) {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8">
        <div className="space-y-6">
          <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8 md:py-8">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              {siteConfig.dashboard.eyebrow}
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 md:text-[2.2rem]">
              {siteConfig.settings.auth.title}
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
              {siteConfig.settings.auth.subtitle}
            </p>
          </section>

          <form
            onSubmit={handleAdminLogin}
            className="max-w-xl rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8"
          >
            {(authError || (!authStatus?.auth_configured && authStatus?.auth_enabled)) && (
              <div
                className={`mb-5 rounded-2xl px-4 py-3 text-sm ${
                  authStatus?.auth_enabled && !authStatus?.auth_configured
                    ? "bg-amber-50 text-amber-800 ring-1 ring-amber-200"
                    : "bg-red-50 text-red-700 ring-1 ring-red-200"
                }`}
              >
                {authStatus?.auth_enabled && !authStatus?.auth_configured
                  ? siteConfig.settings.auth.configurationWarning
                  : authError}
              </div>
            )}

            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">
                {siteConfig.settings.auth.passwordLabel}
              </span>
              <input
                type="password"
                value={adminPassword}
                onChange={(event) => setAdminPassword(event.target.value)}
                placeholder={siteConfig.settings.auth.passwordPlaceholder}
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
              />
            </label>

            <div className="mt-5 flex justify-end">
              <button
                type="submit"
                disabled={isLoggingIn}
                className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {isLoggingIn
                  ? siteConfig.settings.auth.loggingInButton
                  : siteConfig.settings.auth.loginButton}
              </button>
            </div>
          </form>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell contentClassName="p-4 md:p-6 xl:p-8">
      <div className="space-y-6">
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8 md:py-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {siteConfig.dashboard.eyebrow}
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 md:text-[2.2rem]">
            {siteConfig.dashboard.title}
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
            {siteConfig.dashboard.subtitle}
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {authStatus?.authenticated && (
              <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">
                {siteConfig.settings.auth.unlockedBadge}
              </span>
            )}
            {authStatus?.safe_mode_enabled && (
              <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">
                {siteConfig.settings.auth.safeModeBadge}
              </span>
            )}
            {authStatus?.authenticated && (
              <button
                type="button"
                onClick={() => void handleAdminLogout()}
                className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-700 transition hover:bg-slate-100"
              >
                {siteConfig.settings.auth.logoutButton}
              </button>
            )}
          </div>
          {authStatus?.authenticated && (
            <p className="mt-3 text-sm text-slate-500">
              {siteConfig.settings.auth.lockHelp}
            </p>
          )}
          {authStatus?.auth_enabled && !authStatus?.auth_configured && (
            <div className="mt-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-amber-200">
              {siteConfig.settings.auth.configurationWarning}
            </div>
          )}
        </section>

        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-3 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur">
          <div className="flex flex-wrap gap-2">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={
                  activeTab === tab.id
                    ? "rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white"
                    : "rounded-2xl px-4 py-3 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
                }
              >
                {tab.label}
              </button>
            ))}
          </div>
        </section>

        {activeTab === "overview" && (
          <>
            <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
              <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                {siteConfig.settings.overviewTitle}
              </h3>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                {siteConfig.settings.overviewSubtitle}
              </p>

              {systemStatusError && (
                <div className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
                  {systemStatusError}
                </div>
              )}
            </section>

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.overallStatus}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {overallStatusLabel}
                </p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                  {systemStatus?.environment ?? "loading"}
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.conversations}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {systemStatus?.storage.conversations_total ?? 0}
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.processedDocuments}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {systemStatus?.storage.processed_documents ?? 0}
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.indexedDocuments}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {systemStatus?.storage.indexed_documents ?? 0}
                </p>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
                <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.dependenciesTitle}
                </h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                  {siteConfig.settings.dependenciesSubtitle}
                </p>

                <div className="mt-5 space-y-4">
                  {[
                    {
                      key: "ollama",
                      label: siteConfig.settings.dependencyLabels.ollama,
                      payload: systemStatus?.ollama,
                    },
                    {
                      key: "qdrant",
                      label: siteConfig.settings.dependencyLabels.qdrant,
                      payload: systemStatus?.qdrant,
                    },
                  ].map((dependency) => {
                    const payload = dependency.payload;
                    const dependencyStatus =
                      payload?.status ??
                      (systemStatusError ? "error" : "unknown");
                    const dependencyStatusLabel =
                      statusLabels[
                        dependencyStatus as keyof typeof siteConfig.settings.statusLabels
                      ] ?? dependencyStatus;

                    return (
                      <div
                        key={dependency.key}
                        className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.05)]"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">
                              {dependency.label}
                            </p>
                            <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">
                              {dependencyStatusLabel}
                            </p>
                          </div>
                        </div>

                        <dl className="mt-4 space-y-3 text-sm text-slate-600">
                          <div>
                            <dt className="text-xs uppercase tracking-[0.16em] text-slate-400">
                              {siteConfig.settings.dependencyLabels.url}
                            </dt>
                            <dd className="mt-1 break-all">{payload?.url ?? "-"}</dd>
                          </div>

                          <div>
                            <dt className="text-xs uppercase tracking-[0.16em] text-slate-400">
                              {siteConfig.settings.dependencyLabels.detail}
                            </dt>
                            <dd className="mt-1">{payload?.detail || "-"}</dd>
                          </div>

                          {dependency.key === "ollama" && (
                            <div>
                              <dt className="text-xs uppercase tracking-[0.16em] text-slate-400">
                                {siteConfig.settings.dependencyLabels.models}
                              </dt>
                              <dd className="mt-1">{payload?.model_count ?? 0}</dd>
                            </div>
                          )}

                          {dependency.key === "qdrant" && (
                            <>
                              <div>
                                <dt className="text-xs uppercase tracking-[0.16em] text-slate-400">
                                  {siteConfig.settings.dependencyLabels.collection}
                                </dt>
                                <dd className="mt-1">
                                  {payload?.collection_name ?? "-"}{" "}
                                  <span className="text-slate-400">
                                    (
                                    {payload?.collection_exists
                                      ? statusLabels.ready
                                      : statusLabels.missing}
                                    )
                                  </span>
                                </dd>
                              </div>
                              <div>
                                <dt className="text-xs uppercase tracking-[0.16em] text-slate-400">
                                  {siteConfig.settings.dependencyLabels.indexedPoints}
                                </dt>
                                <dd className="mt-1">
                                  {payload?.indexed_point_count ?? 0}
                                </dd>
                              </div>
                            </>
                          )}
                        </dl>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
                <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.storageTitle}
                </h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                  {siteConfig.settings.storageSubtitle}
                </p>

                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  <div className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5">
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.dashboard.cards.uploadedDocuments}
                    </p>
                    <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.documents_total ?? 0}
                    </p>
                  </div>

                  <div className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5">
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.conversations}
                    </p>
                    <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.conversations_total ?? 0}
                    </p>
                  </div>

                  <div className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5">
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.processedDocuments}
                    </p>
                    <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.processed_documents ?? 0}
                    </p>
                  </div>

                  <div className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5">
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.failedDocuments}
                    </p>
                    <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.failed_documents ?? 0}
                    </p>
                  </div>
                </div>

                <div className="mt-4 rounded-[1.5rem] border border-slate-200 bg-slate-50/80 p-5">
                  <p className="text-sm font-medium text-slate-500">
                    {siteConfig.settings.overviewCards.totalLocalStorage}
                  </p>
                  <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                    {formatBytes(systemStatus?.storage.total_size_bytes ?? 0)}
                  </p>
                </div>
              </div>
            </section>
          </>
        )}

        {activeTab === "storage" && (
          <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
            <div className="flex flex-col gap-4 border-b border-slate-200 pb-5 md:flex-row md:items-end md:justify-between">
              <div>
                <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.storageUsageTitle}
                </h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                  {siteConfig.settings.storageUsageSubtitle}
                </p>
              </div>

              <div className="flex flex-col gap-3 md:items-end">
                {cleanableStorageItems.length > 0 && (
                  <button
                    type="button"
                    onClick={() =>
                      void handleCleanup(
                        cleanableStorageItems.map((item) => item.key),
                        siteConfig.settings.storageControls.cleanupConfirmAll
                      )
                    }
                    disabled={cleanupPendingKey !== null}
                    className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    {cleanupPendingKey === "all"
                      ? siteConfig.settings.storageControls.cleaningLabel
                      : siteConfig.settings.storageControls.cleanAllLabel}
                  </button>
                )}

                <div className="grid gap-3 md:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {siteConfig.settings.storageControls.sortLabel}
                  </span>
                  <select
                    value={storageSort}
                    onChange={(event) =>
                      setStorageSort(event.target.value as StorageSort)
                    }
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                  >
                    <option value="largest">
                      {siteConfig.settings.storageControls.sortLargest}
                    </option>
                    <option value="smallest">
                      {siteConfig.settings.storageControls.sortSmallest}
                    </option>
                    <option value="name">
                      {siteConfig.settings.storageControls.sortName}
                    </option>
                  </select>
                </label>

                <label className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                    {siteConfig.settings.storageControls.filterLabel}
                  </span>
                  <select
                    value={storageFilter}
                    onChange={(event) =>
                      setStorageFilter(event.target.value as StorageFilter)
                    }
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                  >
                    <option value="all">
                      {siteConfig.settings.storageControls.filterAll}
                    </option>
                    <option value="cleanable">
                      {siteConfig.settings.storageControls.filterCleanable}
                    </option>
                    <option value="persistent">
                      {siteConfig.settings.storageControls.filterPersistent}
                    </option>
                  </select>
                </label>
                </div>
              </div>
            </div>

            <div className="mt-5 rounded-[1.5rem] border border-slate-200 bg-slate-50/80 p-5">
              <p className="text-sm font-medium text-slate-500">
                {siteConfig.settings.overviewCards.totalLocalStorage}
              </p>
              <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                {formatBytes(systemStatus?.storage.total_size_bytes ?? 0)}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {siteConfig.settings.storageControls.cleanupHint}
              </p>
            </div>

            {(cleanupError || cleanupMessage) && (
              <div
                className={`mt-5 rounded-2xl px-4 py-3 text-sm ${
                  cleanupError
                    ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                    : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                }`}
              >
                {cleanupError || cleanupMessage}
              </div>
            )}

            {filteredStorageItems.length > 0 ? (
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                {filteredStorageItems.map((item) => (
                  <div
                    key={item.key}
                    className="rounded-[1.5rem] border border-slate-200 bg-white/90 p-5 shadow-[0_12px_30px_rgba(15,23,42,0.05)]"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          {item.label}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">
                          {item.cleanable
                            ? statusLabels.cleanable
                            : statusLabels.persistent}
                        </p>
                      </div>

                      <div className="text-right">
                        <p className="text-lg font-semibold tracking-tight text-slate-950">
                          {formatBytes(item.size_bytes)}
                        </p>
                        {item.cleanable && (
                          <button
                            type="button"
                            onClick={() =>
                              void handleCleanup(
                                [item.key],
                                `${siteConfig.settings.storageControls.cleanupConfirmSingle}\n\n${item.label}`
                              )
                            }
                            disabled={cleanupPendingKey !== null}
                            className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                          >
                            {cleanupPendingKey === item.key
                              ? siteConfig.settings.storageControls.cleaningLabel
                              : siteConfig.settings.storageControls.cleanLabel}
                          </button>
                        )}
                      </div>
                    </div>

                    <p className="mt-3 text-sm leading-6 text-slate-600">
                      {item.description}
                    </p>
                    <p className="mt-3 break-all text-xs text-slate-400">
                      {item.path}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-5 rounded-[1.5rem] border border-dashed border-slate-300 bg-slate-50/80 px-5 py-10 text-center text-sm text-slate-500">
                {siteConfig.settings.storageControls.empty}
              </div>
            )}
          </section>
        )}

        {activeTab === "runtime" && (
          <form
            onSubmit={handleRuntimeSave}
            className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8"
          >
            <div className="mb-6">
              <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                {siteConfig.settings.runtimeTitle}
              </h3>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                {siteConfig.settings.runtimeSubtitle}
              </p>
            </div>

            {(runtimeError || runtimeMessage) && (
              <div
                className={`mb-5 rounded-2xl px-4 py-3 text-sm ${
                  runtimeError
                    ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                    : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                }`}
              >
                {runtimeError || runtimeMessage}
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.ollamaBaseUrl}
                </span>
                <input
                  value={runtimeSettings.ollama_base_url}
                  onChange={(event) =>
                    updateField("ollama_base_url", event.target.value)
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.qdrantUrl}
                </span>
                <input
                  value={runtimeSettings.qdrant_url}
                  onChange={(event) =>
                    updateField("qdrant_url", event.target.value)
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.defaultModel}
                </span>
                <input
                  value={runtimeSettings.ollama_default_model}
                  onChange={(event) =>
                    updateField("ollama_default_model", event.target.value)
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.embedModel}
                </span>
                <input
                  value={runtimeSettings.ollama_embed_model}
                  onChange={(event) =>
                    updateField("ollama_embed_model", event.target.value)
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.retrievalLimit}
                </span>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={runtimeSettings.retrieval_limit}
                  onChange={(event) =>
                    updateField("retrieval_limit", Number(event.target.value))
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.retrievalMinScore}
                </span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={runtimeSettings.retrieval_min_score}
                  onChange={(event) =>
                    updateField("retrieval_min_score", Number(event.target.value))
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.chunkSize}
                </span>
                <input
                  type="number"
                  min={200}
                  max={4000}
                  value={runtimeSettings.document_chunk_size}
                  onChange={(event) =>
                    updateField("document_chunk_size", Number(event.target.value))
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>

              <label className="space-y-2 md:col-span-2">
                <span className="text-sm font-medium text-slate-700">
                  {siteConfig.settings.fields.chunkOverlap}
                </span>
                <input
                  type="number"
                  min={0}
                  max={1000}
                  value={runtimeSettings.document_chunk_overlap}
                  onChange={(event) =>
                    updateField(
                      "document_chunk_overlap",
                      Number(event.target.value)
                    )
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 outline-none focus:border-slate-400"
                />
              </label>
            </div>

            <div className="mt-5 flex flex-col gap-3 border-t border-slate-200 pt-5 md:flex-row md:items-center md:justify-between">
              <p className="max-w-2xl text-sm text-slate-500">
                {siteConfig.settings.helperText}
              </p>
              <button
                type="submit"
                disabled={isSavingRuntime}
                className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {isSavingRuntime
                  ? siteConfig.settings.savingButton
                  : siteConfig.settings.saveButton}
              </button>
            </div>
          </form>
        )}

        {activeTab === "security" && (
          <div className="space-y-6">
            <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
              <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                {siteConfig.settings.securityTitle}
              </h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500">
                {siteConfig.settings.securitySubtitle}
              </p>
            </section>

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.adminAuth}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {authStatus?.auth_enabled
                    ? siteConfig.settings.securityValues.enabled
                    : siteConfig.settings.securityValues.disabled}
                </p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                  {authStatus?.auth_configured
                    ? siteConfig.settings.securityValues.configured
                    : siteConfig.settings.securityValues.notConfigured}
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.safeMode}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {authStatus?.safe_mode_enabled
                    ? siteConfig.settings.securityValues.enabled
                    : siteConfig.settings.securityValues.disabled}
                </p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                  {authStatus?.authenticated
                    ? siteConfig.settings.securityValues.unlocked
                    : siteConfig.settings.securityValues.locked}
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.protectedAreas}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityProtectedAreas.length}
                </p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                  Active protections
                </p>
              </div>

              <div className="rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.futureControls}
                </p>
                <p className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityFutureControls.length}
                </p>
                <p className="mt-2 text-xs uppercase tracking-[0.18em] text-slate-400">
                  Planned next
                </p>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityCards.protectedAreas}
                </h4>
                <div className="mt-5 space-y-3">
                  {siteConfig.settings.securityProtectedAreas.map((item) => (
                    <div
                      key={item}
                      className="rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 text-sm text-slate-700"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityCards.futureControls}
                </h4>
                <div className="mt-5 space-y-3">
                  {siteConfig.settings.securityFutureControls.map((item) => (
                    <div
                      key={item}
                      className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/80 px-4 py-3 text-sm text-slate-700"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityCards.howItWorks}
                </h4>
                <div className="mt-5 space-y-3 text-sm leading-6 text-slate-700">
                  <p>{siteConfig.settings.auth.lockHelp}</p>
                  <p>{siteConfig.settings.auth.envToggleHelp}</p>
                </div>
              </div>

              <div
                className={`rounded-[2rem] p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8 ${
                  authStatus?.auth_enabled
                    ? "border border-emerald-200 bg-emerald-50/90"
                    : "border border-amber-200 bg-amber-50/90"
                }`}
              >
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  Admin auth status
                </h4>
                <p className="mt-3 text-sm leading-6 text-slate-700">
                  {authStatus?.auth_enabled
                    ? authStatus?.auth_configured
                      ? siteConfig.settings.securityNotes.authEnabledConfigured
                      : siteConfig.settings.securityNotes.authEnabledNotConfigured
                    : siteConfig.settings.securityNotes.authDisabled}
                </p>
              </div>

              <div
                className={`rounded-[2rem] p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8 ${
                  authStatus?.safe_mode_enabled
                    ? "border border-emerald-200 bg-emerald-50/90"
                    : "border border-slate-200/80 bg-white/88"
                }`}
              >
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  Safe mode status
                </h4>
                <p className="mt-3 text-sm leading-6 text-slate-700">
                  {authStatus?.safe_mode_enabled
                    ? siteConfig.settings.securityNotes.safeModeEnabled
                    : siteConfig.settings.securityNotes.safeModeDisabled}
                </p>
              </div>
            </section>
          </div>
        )}

        {activeTab === "connectors" && (
          <ConnectorManager
            connectors={connectors}
            isLoading={areConnectorsLoading}
            isRefreshing={areConnectorsRefreshing}
            isCreating={isCreatingConnector}
            savingConnectorId={savingConnectorId}
            deletingConnectorId={deletingConnectorId}
            syncingConnectorId={syncingConnectorId}
            previewingConnectorId={previewingConnectorId}
            isBrowsing={isBrowsing}
            error={connectorsError}
            statusMessage={connectorsStatusMessage}
            lastBrowseResult={lastBrowseResult}
            lastSyncResult={lastSyncResult}
            onRefresh={refreshConnectors}
            onCreate={addConnector}
            onUpdate={saveConnector}
            onDelete={removeConnector}
            onPreviewSync={previewSync}
            onBrowse={browseFolders}
            onSync={async (connectorId) => {
              const result = await runSync(connectorId);
              if (result) {
                await loadSystemOverview();
              }
            }}
          />
        )}

        {activeTab === "debug" && (
          <div className="grid gap-4 xl:grid-cols-3">
            <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
              <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                    {siteConfig.settings.toolsTitle}
                  </h3>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                    {siteConfig.settings.toolsSubtitle}
                  </p>
                </div>

                <Link
                  href="/logs"
                  className="inline-flex rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
                >
                  {siteConfig.settings.openLogsLabel}
                </Link>
              </div>
            </section>

            <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
              <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                    {siteConfig.settings.exportTitle}
                  </h3>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                    {siteConfig.settings.exportSubtitle}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => void handleExportBackup()}
                  disabled={isExporting}
                  className="inline-flex rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {isExporting
                    ? siteConfig.settings.exportingButton
                    : siteConfig.settings.exportButton}
                </button>
              </div>

              {exportError && (
                <div className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
                  {exportError}
                </div>
              )}
            </section>

            <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
              <div className="flex flex-col gap-4">
                <div>
                  <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                    {siteConfig.settings.importTitle}
                  </h3>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                    {siteConfig.settings.importSubtitle}
                  </p>
                </div>

                <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  {siteConfig.settings.importWarning}
                </div>

                <div className="space-y-3">
                  <label className="inline-flex cursor-pointer rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100">
                    <input
                      type="file"
                      accept="application/json"
                      className="hidden"
                      onChange={(event) =>
                        setSelectedBackupFile(
                          event.target.files?.[0] ?? null
                        )
                      }
                    />
                    {siteConfig.settings.importFileButton}
                  </label>

                  <p className="text-sm text-slate-500">
                    {selectedBackupFile
                      ? selectedBackupFile.name
                      : siteConfig.settings.importNoFileLabel}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => void handleImportBackup()}
                  disabled={isImporting}
                  className="inline-flex rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {isImporting
                    ? siteConfig.settings.importingButton
                    : siteConfig.settings.importButton}
                </button>

                {(importError || importMessage) && (
                  <div
                    className={`rounded-2xl px-4 py-3 text-sm ${
                      importError
                        ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                        : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                    }`}
                  >
                    {importError || importMessage}
                  </div>
                )}
              </div>
            </section>
          </div>
        )}

        {activeTab === "models" && (
          <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8">
            <div className="mb-5">
              <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                {siteConfig.dashboard.modelsTitle}
              </h3>
              <p className="mt-2 text-sm text-slate-500">
                {siteConfig.dashboard.modelsSubtitle}
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full border-separate border-spacing-y-2">
                <thead>
                  <tr className="text-left text-sm text-slate-500">
                    <th className="px-3 py-2">Name</th>
                    <th className="px-3 py-2">ID</th>
                    <th className="px-3 py-2">Size</th>
                    <th className="px-3 py-2">Provider</th>
                    <th className="px-3 py-2">Installed</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((model) => (
                    <tr
                      key={model.id}
                      className="rounded-2xl bg-slate-50 text-slate-700 ring-1 ring-slate-200/70"
                    >
                      <td className="px-3 py-3 font-medium text-slate-900">
                        {model.name}
                      </td>
                      <td className="px-3 py-3 text-sm">{model.id}</td>
                      <td className="px-3 py-3 capitalize">{model.size}</td>
                      <td className="px-3 py-3">{model.provider}</td>
                      <td className="px-3 py-3">
                        {model.installed ? "Yes" : "No"}
                      </td>
                    </tr>
                  ))}

                  {models.length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="px-3 py-8 text-center text-slate-500"
                      >
                        {siteConfig.dashboard.emptyModels}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </AppShell>
  );
}
