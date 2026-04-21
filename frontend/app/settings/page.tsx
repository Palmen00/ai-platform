"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell";
import { siteConfig } from "../../config/site";
import { ConnectorManager } from "../../features/connectors/components/ConnectorManager";
import { useConnectors } from "../../features/connectors/hooks/useConnectors";
import {
  AuthStatusResponse,
  cleanupStorageTargets,
  createUser,
  CreateUserInput,
  DocumentIntelligenceResponse,
  refreshDocumentIntelligence,
  getAuthStatus,
  getBackupExport,
  getDocumentIntelligence,
  getLogs,
  getUsers,
  importBackup,
  LogEvent,
  LocalUserSummary,
  loginUser,
  logoutAdmin,
  getModels,
  getRuntimeSettings,
  getSystemStatus,
  BackupExportPayload,
  BackupImportResponse,
  CleanupTargetResult,
  LogsResponse,
  ModelItem,
  RuntimeSettings,
  StorageUsageItem,
  SystemStatusResponse,
  updateUser,
  UpdateUserInput,
  updateRuntimeSettings,
} from "../../lib/api";

const AUTH_UPDATED_EVENT = "auth:updated";

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
  | "documents"
  | "storage"
  | "cleanup"
  | "runtime"
  | "retrieval"
  | "connectors"
  | "users"
  | "security"
  | "audit"
  | "backups"
  | "logs"
  | "models";
type StorageSort = "largest" | "smallest" | "name";
type StorageFilter = "all" | "cleanable" | "persistent";
type SettingsTabGroup = "Workspace" | "Access" | "Operations";
type SettingsTabMeta = {
  id: SettingsTab;
  label: string;
  description: string;
  group: SettingsTabGroup;
  shortLabel: string;
};

function resolveSettingsTab(value: string | null): SettingsTab | null {
  if (!value) {
    return null;
  }

  const matchingTab = SETTINGS_TABS.find((tab) => tab.id === value);
  return matchingTab?.id ?? null;
}

const SETTINGS_TABS: SettingsTabMeta[] = [
  {
    id: "overview",
    label: siteConfig.settings.tabs.overview,
    shortLabel: "Status",
    description:
      "See health, dependencies, storage footprint, and overall app readiness.",
    group: "Workspace",
  },
  {
    id: "documents",
    label: siteConfig.settings.tabs.documents,
    shortLabel: "Families & versions",
    description:
      "Inspect document families, version readiness, topic tagging, and background enrichment state.",
    group: "Workspace",
  },
  {
    id: "runtime",
    label: siteConfig.settings.tabs.runtime,
    shortLabel: "Services & models",
    description:
      "Point the app at Ollama and Qdrant, and choose the primary models for this environment.",
    group: "Workspace",
  },
  {
    id: "retrieval",
    label: siteConfig.settings.tabs.retrieval,
    shortLabel: "Chunking & search",
    description:
      "Tune retrieval depth, score threshold, and document chunking without mixing it with base runtime wiring.",
    group: "Workspace",
  },
  {
    id: "models",
    label: siteConfig.settings.tabs.models,
    shortLabel: "Installed models",
    description:
      "Inspect currently available models and what is installed in this environment.",
    group: "Workspace",
  },
  {
    id: "connectors",
    label: siteConfig.settings.tabs.connectors,
    shortLabel: "External sources",
    description:
      "Control synced sources, folder scope, default access, and sync behavior.",
    group: "Access",
  },
  {
    id: "users",
    label: siteConfig.settings.tabs.users,
    shortLabel: "Accounts",
    description:
      "Create local accounts, assign roles, and keep admin access tightly controlled.",
    group: "Access",
  },
  {
    id: "security",
    label: siteConfig.settings.tabs.security,
    shortLabel: "Posture & policy",
    description:
      "Review auth posture, safe mode, and what security controls are active in this environment.",
    group: "Access",
  },
  {
    id: "audit",
    label: siteConfig.settings.tabs.audit,
    shortLabel: "Sensitive activity",
    description:
      "Track logins, permission changes, connector actions, and other high-impact events.",
    group: "Access",
  },
  {
    id: "storage",
    label: siteConfig.settings.tabs.storage,
    shortLabel: "Usage & volume",
    description:
      "Review what is taking space locally across documents, vectors, and conversations.",
    group: "Operations",
  },
  {
    id: "cleanup",
    label: siteConfig.settings.tabs.cleanup,
    shortLabel: "Safe cleanup",
    description:
      "Clean regenerable areas without mixing destructive-looking actions into the storage overview.",
    group: "Operations",
  },
  {
    id: "backups",
    label: siteConfig.settings.tabs.backups,
    shortLabel: "Import & export",
    description:
      "Export a portable snapshot of settings and chats, or restore a previous state.",
    group: "Operations",
  },
  {
    id: "logs",
    label: siteConfig.settings.tabs.logs,
    shortLabel: "Backend events",
    description:
      "Inspect recent backend events and raw log lines without mixing them into backup workflows.",
    group: "Operations",
  },
];

const settingsPanelClass =
  "rounded-[1.15rem] border border-slate-200/90 bg-white/95 p-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)]";
const settingsPanelCompactClass =
  "rounded-[1.15rem] border border-slate-200/90 bg-white/95 px-5 py-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)]";
const settingsTileClass =
  "rounded-[1rem] border border-slate-200 bg-white px-4 py-3";
const settingsSubtlePanelClass =
  "rounded-[1rem] border border-slate-200 bg-slate-50/85 p-4";
const settingsInputClass =
  "w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-800 outline-none focus:border-slate-400";
const settingsPrimaryButtonClass =
  "rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300";
const settingsSecondaryButtonClass =
  "rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60";

function SettingsPageContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [activeTab, setActiveTab] = useState<SettingsTab>(
    () => resolveSettingsTab(searchParams.get("tab")) ?? "overview"
  );
  const [settingsSearch, setSettingsSearch] = useState("");
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [authInfoMessage, setAuthInfoMessage] = useState("");
  const [username, setUsername] = useState("admin");
  const [adminPassword, setAdminPassword] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(
    null
  );
  const [systemStatusError, setSystemStatusError] = useState("");
  const [documentIntelligence, setDocumentIntelligence] =
    useState<DocumentIntelligenceResponse | null>(null);
  const [documentIntelligenceError, setDocumentIntelligenceError] = useState("");
  const [documentIntelligenceMessage, setDocumentIntelligenceMessage] =
    useState("");
  const [isRefreshingDocumentIntelligence, setIsRefreshingDocumentIntelligence] =
    useState(false);
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
  const [users, setUsers] = useState<LocalUserSummary[]>([]);
  const [usersError, setUsersError] = useState("");
  const [usersStatusMessage, setUsersStatusMessage] = useState("");
  const [isUsersLoading, setIsUsersLoading] = useState(false);
  const [isCreatingUser, setIsCreatingUser] = useState(false);
  const [savingUserId, setSavingUserId] = useState("");
  const [newUser, setNewUser] = useState<CreateUserInput>({
    username: "",
    password: "",
    role: "viewer",
    enabled: true,
  });
  const [editingUserId, setEditingUserId] = useState("");
  const [editingUserDraft, setEditingUserDraft] = useState<UpdateUserInput>({
    username: "",
    password: "",
    role: "viewer",
    enabled: true,
  });
  const [auditEvents, setAuditEvents] = useState<LogEvent[]>([]);
  const [isAuditLoading, setIsAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState("");
  const [logsPreview, setLogsPreview] = useState<LogsResponse | null>(null);
  const [isLogsLoading, setIsLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState("");
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
  const isAuthenticated = !isAdminAuthRequired || !!authStatus?.authenticated;
  const isAdminUnlocked =
    !isAdminAuthRequired || authStatus?.role === "admin";
  const enabledUsernames = users
    .filter((user) => user.enabled)
    .map((user) => user.username);
  const normalizedSettingsSearch = settingsSearch.trim().toLowerCase();
  const visibleTabs = SETTINGS_TABS.filter((tab) =>
    !normalizedSettingsSearch
      ? true
      : [tab.label, tab.shortLabel, tab.description, tab.group]
          .join(" ")
          .toLowerCase()
          .includes(normalizedSettingsSearch)
  );
  const activeTabMeta =
    SETTINGS_TABS.find((tab) => tab.id === activeTab) ?? SETTINGS_TABS[0];
  const tabsByGroup = (group: SettingsTabGroup) =>
    visibleTabs.filter((tab) => tab.group === group);

  useEffect(() => {
    const requestedTab = resolveSettingsTab(searchParams.get("tab"));
    if (!requestedTab || requestedTab === activeTab) {
      return;
    }

    setActiveTab(requestedTab);
  }, [activeTab, searchParams]);

  const navigateToTab = useCallback(
    (tabId: SettingsTab) => {
      setActiveTab(tabId);

      const params = new URLSearchParams(searchParams.toString());
      params.set("tab", tabId);
      const nextQuery = params.toString();
      const nextUrl = nextQuery ? `${pathname}?${nextQuery}` : pathname;
      router.replace(nextUrl, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  async function loadUsers(force = false) {
    if (!force && !isAdminUnlocked) {
      setUsers([]);
      return;
    }

    setIsUsersLoading(true);
    setUsersError("");

    try {
      const payload = await getUsers();
      setUsers(payload.users);
    } catch {
      setUsersError("Could not load users.");
    } finally {
      setIsUsersLoading(false);
    }
  }

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

  async function loadDocumentIntelligence() {
    try {
      const payload = await getDocumentIntelligence();
      setDocumentIntelligence(payload);
      setDocumentIntelligenceError("");
    } catch {
      setDocumentIntelligence(null);
      setDocumentIntelligenceError("Could not load document intelligence.");
    }
  }

  async function loadAuditEvents() {
    setIsAuditLoading(true);
    setAuditError("");

    try {
      const payload = await getLogs({
        eventLimit: 20,
        lineLimit: 10,
        auditOnly: true,
      });
      setAuditEvents(payload.events);
    } catch {
      setAuditError(siteConfig.settings.securityAuditLoadError);
    } finally {
      setIsAuditLoading(false);
    }
  }

  async function loadLogsPreview() {
    setIsLogsLoading(true);
    setLogsError("");

    try {
      const payload = await getLogs({
        eventLimit: 8,
        lineLimit: 16,
      });
      setLogsPreview(payload);
    } catch {
      setLogsError(siteConfig.logs.loadError);
    } finally {
      setIsLogsLoading(false);
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
        const payload = await getDocumentIntelligence();
        if (isMounted) {
          setDocumentIntelligence(payload);
          setDocumentIntelligenceError("");
        }
      } catch {
        if (isMounted) {
          setDocumentIntelligence(null);
          setDocumentIntelligenceError("Could not load document intelligence.");
        }
      }

      try {
        const shouldLoadProtectedRuntime =
          !nextAuthStatus?.auth_enabled ||
          !nextAuthStatus?.auth_configured ||
          nextAuthStatus?.role === "admin";
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

      try {
        const shouldLoadUsers =
          !nextAuthStatus?.auth_enabled ||
          !nextAuthStatus?.auth_configured ||
          nextAuthStatus?.role === "admin";
        if (shouldLoadUsers) {
          const payload = await getUsers();
          if (isMounted) {
            setUsers(payload.users);
            setUsersError("");
          }
        }
      } catch {
        if (isMounted) {
          setUsersError("Could not load users.");
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

  useEffect(() => {
    if (activeTab !== "documents" || !isAuthenticated) {
      return;
    }

    void loadDocumentIntelligence();
  }, [activeTab, isAuthenticated]);

  useEffect(() => {
    if (activeTab !== "audit" || !isAdminUnlocked) {
      return;
    }

    void loadAuditEvents();
  }, [activeTab, isAdminUnlocked]);

  useEffect(() => {
    if (activeTab !== "logs" || !isAdminUnlocked) {
      return;
    }

    void loadLogsPreview();
  }, [activeTab, isAdminUnlocked]);

  useEffect(() => {
    if (visibleTabs.length === 0) {
      return;
    }

    if (!visibleTabs.some((tab) => tab.id === activeTab)) {
      navigateToTab(visibleTabs[0].id);
    }
  }, [activeTab, navigateToTab, visibleTabs]);

  async function refreshProtectedState() {
    try {
      const nextRuntimeSettings = await getRuntimeSettings();
      setRuntimeSettings(nextRuntimeSettings);
      setRuntimeError("");
    } catch {
      setRuntimeError(siteConfig.settings.loadError);
    }

    await loadUsers(true);
  }

  async function handleAdminLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    setAuthInfoMessage("");
    setIsLoggingIn(true);

    try {
      const nextAuthStatus = await loginUser(username, adminPassword);
      setAuthStatus(nextAuthStatus);
      setAdminPassword("");
      window.dispatchEvent(new Event(AUTH_UPDATED_EVENT));
      if (!nextAuthStatus.auth_enabled || nextAuthStatus.role === "admin") {
        await refreshProtectedState();
      }
    } catch {
      setAuthError(siteConfig.settings.auth.loginError);
    } finally {
      setIsLoggingIn(false);
    }
  }

  async function handleAdminLogout() {
    await logoutAdmin();
    setAuthStatus((current) => {
      const nextStatus =
      current
        ? {
            ...current,
            authenticated: false,
            username: null,
            role: null,
            session_expires_at: null,
          }
        : current;

      return nextStatus;
    });
    setUsers([]);
    setAuthInfoMessage("Settings were locked for this browser session.");
    window.dispatchEvent(new Event(AUTH_UPDATED_EVENT));
  }

  function startEditingUser(user: LocalUserSummary) {
    setEditingUserId(user.id);
    setEditingUserDraft({
      username: user.username,
      password: "",
      role: user.role,
      enabled: user.enabled,
    });
    setUsersError("");
    setUsersStatusMessage("");
  }

  function cancelEditingUser() {
    setEditingUserId("");
    setEditingUserDraft({
      username: "",
      password: "",
      role: "viewer",
      enabled: true,
    });
  }

  async function handleCreateUser(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setUsersError("");
    setUsersStatusMessage("");
    setIsCreatingUser(true);

    try {
      await createUser(newUser);
      setNewUser({
        username: "",
        password: "",
        role: "viewer",
        enabled: true,
      });
      setUsersStatusMessage("User created.");
      await loadUsers();
    } catch {
      setUsersError("Could not create user.");
    } finally {
      setIsCreatingUser(false);
    }
  }

  async function handleSaveUser(
    event: React.FormEvent<HTMLFormElement>,
    userId: string
  ) {
    event.preventDefault();
    setUsersError("");
    setUsersStatusMessage("");
    setSavingUserId(userId);

    try {
      await updateUser(userId, editingUserDraft);
      setUsersStatusMessage("User updated.");
      cancelEditingUser();
      await loadUsers();
    } catch {
      setUsersError("Could not update user.");
    } finally {
      setSavingUserId("");
    }
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

  async function handleRefreshDocumentIntelligence() {
    setDocumentIntelligenceError("");
    setDocumentIntelligenceMessage("");
    setIsRefreshingDocumentIntelligence(true);

    try {
      const payload = await refreshDocumentIntelligence();
      setDocumentIntelligence(payload.status);
      setDocumentIntelligenceMessage(
        payload.refreshed_count > 0
          ? siteConfig.settings.documentsControls.refreshSuccess
          : siteConfig.settings.documentsControls.refreshNoop
      );
      await loadSystemOverview();
    } catch {
      setDocumentIntelligenceError(
        siteConfig.settings.documentsControls.refreshError
      );
    } finally {
      setIsRefreshingDocumentIntelligence(false);
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
  const auditErrorCount = auditEvents.filter((event) => event.status === "error").length;
  const auditWarningCount = auditEvents.filter((event) => event.status === "warning").length;
  const adminUserCount = users.filter((user) => user.role === "admin").length;
  const enabledUserCount = users.filter((user) => user.enabled).length;
  const totalConversationCount = users.reduce(
    (sum, user) => sum + (user.stats?.conversation_count ?? 0),
    0
  );
  const totalConversationStorageBytes = users.reduce(
    (sum, user) => sum + (user.stats?.conversation_storage_bytes ?? 0),
    0
  );
  const totalAccessibleDocumentStorageBytes = users.reduce(
    (sum, user) => sum + (user.stats?.accessible_document_storage_bytes ?? 0),
    0
  );

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

  function formatDateTime(value: string) {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }

    return parsed.toLocaleString([], {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
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

  function renderAuditActor(event: LogEvent) {
    if (event.actor_username) {
      return `${event.actor_username}${event.actor_role ? ` (${event.actor_role})` : ""}`;
    }

    return event.category === "audit" ? "System action" : "System";
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

  if (isAdminAuthRequired && !isAuthenticated) {
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
            {(authError ||
              authInfoMessage ||
              (!authStatus?.auth_configured && authStatus?.auth_enabled)) && (
              <div
                className={`mb-5 rounded-2xl px-4 py-3 text-sm ${
                  authStatus?.auth_enabled && !authStatus?.auth_configured
                    ? "bg-amber-50 text-amber-800 ring-1 ring-amber-200"
                    : authInfoMessage
                      ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                    : "bg-red-50 text-red-700 ring-1 ring-red-200"
                }`}
              >
                {authStatus?.auth_enabled && !authStatus?.auth_configured
                  ? siteConfig.settings.auth.configurationWarning
                  : authInfoMessage || authError}
              </div>
            )}

            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">
                Username
              </span>
              <input
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Enter username"
                className={settingsInputClass}
              />
            </label>

            <label className="mt-4 space-y-2">
              <span className="text-sm font-medium text-slate-700">
                {siteConfig.settings.auth.passwordLabel}
              </span>
              <input
                type="password"
                value={adminPassword}
                onChange={(event) => setAdminPassword(event.target.value)}
                placeholder={siteConfig.settings.auth.passwordPlaceholder}
                className={settingsInputClass}
              />
            </label>

            <div className="mt-5 flex justify-end">
              <button
                type="submit"
                disabled={isLoggingIn}
                className={settingsPrimaryButtonClass}
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

  if (isAdminAuthRequired && authStatus?.authenticated && authStatus.role !== "admin") {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8">
        <div className="space-y-6">
          <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8 md:py-8">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
              {siteConfig.dashboard.eyebrow}
            </p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 md:text-[2.2rem]">
              Settings
            </h2>
            <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
              You are signed in as <span className="font-medium text-slate-900">{authStatus.username}</span>, but this area requires an admin account.
            </p>
            <div className="mt-5 flex flex-wrap gap-3">
              <Link
                href="/chat"
                className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
              >
                Go to chat
              </Link>
              <button
                type="button"
                onClick={() => void handleAdminLogout()}
                className="rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800"
              >
                Sign out
              </button>
            </div>
          </section>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell contentClassName="p-3 md:p-4 xl:p-5">
      <div className="grid gap-4 xl:grid-cols-[176px_minmax(0,1fr)]">
        <aside className="xl:sticky xl:top-6 xl:self-start">
          <div className="space-y-3 rounded-[1rem] border border-slate-200/90 bg-white/95 p-3 shadow-[0_10px_24px_rgba(15,23,42,0.04)]">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                Admin console
              </p>
              <h2 className="mt-1 text-[1.4rem] font-semibold tracking-tight text-slate-950">
                Settings
              </h2>
              <p className="mt-1 text-[12px] leading-5 text-slate-500">
                Deep app controls.
              </p>
            </div>

            <label className="block">
              <span className="sr-only">Search settings</span>
              <input
                type="search"
                value={settingsSearch}
                onChange={(event) => setSettingsSearch(event.target.value)}
                placeholder="Search settings..."
                className="w-full rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-[12px] text-slate-800 outline-none transition focus:border-slate-400"
              />
            </label>

            {(["Workspace", "Access", "Operations"] as SettingsTabGroup[]).map(
              (group) => {
                const groupTabs = tabsByGroup(group);
                if (groupTabs.length === 0) {
                  return null;
                }

                return (
                  <section key={group} className="space-y-1.5">
                    <p className="px-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                      {group}
                    </p>
                    <div className="space-y-0.5">
                      {groupTabs.map((tab) => (
                        <button
                          key={tab.id}
                          type="button"
                          onClick={() => navigateToTab(tab.id)}
                          className={
                            activeTab === tab.id
                              ? "w-full border-l-2 border-slate-950 px-2 py-1 text-left text-[13px] font-semibold text-slate-950"
                              : "w-full border-l-2 border-transparent px-2 py-1 text-left text-[13px] text-slate-600 transition hover:text-slate-950"
                          }
                        >
                          <div className="leading-5">{tab.label}</div>
                        </button>
                      ))}
                    </div>
                  </section>
                );
              }
            )}

            {visibleTabs.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50/80 px-3 py-4 text-sm text-slate-500">
                No settings matched your search yet.
              </div>
            )}

            <div className="rounded-lg border border-slate-200 bg-slate-50/90 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                Environment
              </p>
              <div className="mt-2 space-y-1.5 text-[12px] text-slate-600">
                <div className="flex items-center justify-between gap-3">
                  <span>Mode</span>
                  <span className="font-medium text-slate-900">
                    {systemStatus?.environment ?? "local"}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>Admin session</span>
                  <span className="font-medium text-slate-900">
                    {authStatus?.authenticated
                      ? authStatus.username || siteConfig.settings.auth.unlockedBadge
                      : "Locked"}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span>Safe mode</span>
                  <span className="font-medium text-slate-900">
                    {authStatus?.safe_mode_enabled ? "On" : "Off"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div className="space-y-4">
          <section className={settingsPanelCompactClass}>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                  {activeTabMeta.group}
                </p>
                <h2 className="mt-2 text-[1.9rem] font-semibold tracking-tight text-slate-950">
                  {activeTabMeta.label}
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                  {activeTabMeta.description}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2 lg:max-w-sm lg:justify-end">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-700">
                  {overallStatusLabel}
                </span>
                {authStatus?.authenticated && (
                  <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald-700">
                    {siteConfig.settings.auth.unlockedBadge}
                  </span>
                )}
                {authStatus?.safe_mode_enabled && (
                  <span className="rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-700">
                    {siteConfig.settings.auth.safeModeBadge}
                  </span>
                )}
                {authStatus?.authenticated && (
                  <button
                    type="button"
                    onClick={() => void handleAdminLogout()}
                    className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-700 transition hover:bg-slate-100"
                  >
                    {siteConfig.settings.auth.logoutButton}
                  </button>
                )}
              </div>
            </div>

            {authStatus?.authenticated && (
              <p className="mt-4 text-sm text-slate-500">
                {siteConfig.settings.auth.lockHelp}
              </p>
            )}
            {authStatus?.auth_enabled && !authStatus?.auth_configured && (
              <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2.5 text-sm text-amber-800 ring-1 ring-amber-200">
                {siteConfig.settings.auth.configurationWarning}
              </div>
            )}
          </section>

        {activeTab === "overview" && (
          <>
            {systemStatusError && (
              <div className="rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-red-200">
                {systemStatusError}
              </div>
            )}

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.overallStatus}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {overallStatusLabel}
                </p>
                <p className="mt-1.5 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                  {systemStatus?.environment ?? "loading"}
                </p>
              </div>

              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.conversations}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {systemStatus?.storage.conversations_total ?? 0}
                </p>
              </div>

              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.processedDocuments}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {systemStatus?.storage.processed_documents ?? 0}
                </p>
              </div>

              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.indexedDocuments}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {systemStatus?.storage.indexed_documents ?? 0}
                </p>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className={settingsPanelClass}>
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
                        className={settingsSubtlePanelClass}
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

              <div className={settingsPanelClass}>
                <h3 className="text-xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.storageTitle}
                </h3>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
                  {siteConfig.settings.storageSubtitle}
                </p>

                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.dashboard.cards.uploadedDocuments}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.documents_total ?? 0}
                    </p>
                  </div>

                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.conversations}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.conversations_total ?? 0}
                    </p>
                  </div>

                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.processedDocuments}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.processed_documents ?? 0}
                    </p>
                  </div>

                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.failedDocuments}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.storage.failed_documents ?? 0}
                    </p>
                  </div>

                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.documentFamilies}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.document_intelligence.total_families ?? 0}
                    </p>
                  </div>

                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.versionedDocuments}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.document_intelligence.versioned_documents ?? 0}
                    </p>
                  </div>

                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.topicReadyDocuments}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.document_intelligence.topic_ready_documents ?? 0}
                    </p>
                  </div>

                  <div className={settingsTileClass}>
                    <p className="text-sm font-medium text-slate-500">
                      {siteConfig.settings.overviewCards.maintenanceBacklog}
                    </p>
                    <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                      {systemStatus?.maintenance.pending_documents ?? 0}
                    </p>
                  </div>
                </div>

                <div className={`mt-4 ${settingsSubtlePanelClass}`}>
                  <p className="text-sm font-medium text-slate-500">
                    {siteConfig.settings.overviewCards.totalLocalStorage}
                  </p>
                  <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                    {formatBytes(systemStatus?.storage.total_size_bytes ?? 0)}
                  </p>
                </div>
              </div>
            </section>
          </>
        )}

        {activeTab === "documents" && (
          <div className="space-y-4">
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.documentFamilies}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {documentIntelligence?.summary.total_families ?? 0}
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.versionedDocuments}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {documentIntelligence?.summary.versioned_documents ?? 0}
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.topicReadyDocuments}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {documentIntelligence?.summary.topic_ready_documents ?? 0}
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.overviewCards.maintenanceBacklog}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {documentIntelligence?.maintenance.pending_documents ?? 0}
                </p>
              </div>
            </section>

            {(documentIntelligenceError || documentIntelligenceMessage) && (
              <div
                className={`rounded-xl px-3 py-2.5 text-sm ${
                  documentIntelligenceError
                    ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                    : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                }`}
              >
                {documentIntelligenceError || documentIntelligenceMessage}
              </div>
            )}

            <section className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
              <div className={settingsPanelClass}>
                <div className="flex flex-col gap-4 border-b border-slate-200 pb-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                      {siteConfig.settings.documentsControls.familiesTitle}
                    </h3>
                    <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                      {siteConfig.settings.documentsSubtitle}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleRefreshDocumentIntelligence()}
                    disabled={!isAdminUnlocked || isRefreshingDocumentIntelligence}
                    className={settingsSecondaryButtonClass}
                  >
                    {isRefreshingDocumentIntelligence
                      ? siteConfig.settings.documentsControls.refreshingButton
                      : siteConfig.settings.documentsControls.refreshButton}
                  </button>
                </div>

                {documentIntelligence?.families?.length ? (
                  <div className="mt-4 space-y-3">
                    {documentIntelligence.families.map((family) => (
                      <div key={family.family_key} className={settingsSubtlePanelClass}>
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-slate-900">
                              {family.family_label}
                            </p>
                            <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">
                              {family.document_count} documents
                            </p>
                          </div>
                          <div className="text-right text-sm text-slate-500">
                            <p className="font-medium text-slate-900">
                              {family.latest_document_name}
                            </p>
                            <p>{family.latest_document_date || "No date"}</p>
                          </div>
                        </div>
                        {family.topics.length > 0 && (
                          <div className="mt-3 flex flex-wrap gap-2">
                            {family.topics.map((topic) => (
                              <span
                                key={`${family.family_key}-${topic}`}
                                className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500"
                              >
                                {topic}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="mt-3 space-y-2 text-sm text-slate-600">
                          {family.members.map((member) => (
                            <div
                              key={member.document_id}
                              className="flex items-center justify-between gap-3"
                            >
                              <span className="truncate">{member.document_name}</span>
                              <span className="shrink-0 text-xs uppercase tracking-[0.14em] text-slate-400">
                                {member.version_label || member.document_date || "tracked"}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50/80 px-4 py-8 text-center text-sm text-slate-500">
                    {siteConfig.settings.documentsControls.emptyFamilies}
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <section className={settingsPanelClass}>
                  <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                    {siteConfig.settings.documentsControls.maintenanceTitle}
                  </h3>
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className={settingsTileClass}>
                      <p className="text-sm font-medium text-slate-500">Mode</p>
                      <p className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                        {documentIntelligence?.maintenance.enabled ? "Enabled" : "Off"}
                      </p>
                    </div>
                    <div className={settingsTileClass}>
                      <p className="text-sm font-medium text-slate-500">Pending</p>
                      <p className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                        {documentIntelligence?.maintenance.pending_documents ?? 0}
                      </p>
                    </div>
                    <div className={settingsTileClass}>
                      <p className="text-sm font-medium text-slate-500">Idle threshold</p>
                      <p className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                        {documentIntelligence?.maintenance.user_idle_seconds ?? 0}s
                      </p>
                    </div>
                    <div className={settingsTileClass}>
                      <p className="text-sm font-medium text-slate-500">Batch size</p>
                      <p className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                        {documentIntelligence?.maintenance.batch_size ?? 0}
                      </p>
                    </div>
                  </div>
                  <div className={`mt-4 ${settingsSubtlePanelClass}`}>
                    <div className="flex items-center justify-between gap-3 text-sm text-slate-600">
                      <span>Last run</span>
                      <span className="font-medium text-slate-900">
                        {documentIntelligence?.maintenance.last_run_at
                          ? formatDateTime(documentIntelligence.maintenance.last_run_at)
                          : "Not yet"}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-3 text-sm text-slate-600">
                      <span>User idle for</span>
                      <span className="font-medium text-slate-900">
                        {Math.round(
                          documentIntelligence?.maintenance
                            .seconds_since_user_activity ?? 0
                        )}
                        s
                      </span>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-3 text-sm text-slate-600">
                      <span>Active jobs</span>
                      <span className="font-medium text-slate-900">
                        {Object.keys(
                          documentIntelligence?.maintenance.active_jobs ?? {}
                        ).length || 0}
                      </span>
                    </div>
                  </div>
                </section>

                <section className={settingsPanelClass}>
                  <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                    {siteConfig.settings.documentsControls.staleTitle}
                  </h3>
                  {documentIntelligence?.stale_documents?.length ? (
                    <div className="mt-4 space-y-2">
                      {documentIntelligence.stale_documents.map((document) => (
                        <div
                          key={document.document_id}
                          className="flex items-center justify-between gap-3 border-b border-slate-200/80 pb-2 text-sm text-slate-700 last:border-b-0 last:pb-0"
                        >
                          <span className="truncate">{document.document_name}</span>
                          <span className="shrink-0 text-xs uppercase tracking-[0.14em] text-slate-400">
                            {document.version_label || document.document_date || "queued"}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50/80 px-4 py-8 text-center text-sm text-slate-500">
                      {siteConfig.settings.documentsControls.emptyStale}
                    </div>
                  )}
                </section>
              </div>
            </section>
          </div>
        )}

        {activeTab === "storage" && (
          <section className={settingsPanelClass}>
            <div className="flex flex-col gap-4 border-b border-slate-200 pb-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.storageUsageTitle}
                </h3>
                <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                  {siteConfig.settings.storageUsageSubtitle}
                </p>
              </div>

              <div className="flex flex-col gap-3 md:items-end">
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
                      className={settingsInputClass}
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
                      className={settingsInputClass}
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

            <div className={`mt-4 ${settingsSubtlePanelClass}`}>
              <p className="text-sm font-medium text-slate-500">
                {siteConfig.settings.overviewCards.totalLocalStorage}
              </p>
              <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                {formatBytes(systemStatus?.storage.total_size_bytes ?? 0)}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                {siteConfig.settings.storageControls.cleanupHint}
              </p>
            </div>

            {filteredStorageItems.length > 0 ? (
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {filteredStorageItems.map((item) => (
                  <div
                    key={item.key}
                    className={settingsSubtlePanelClass}
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

        {activeTab === "cleanup" && (
          <section className={settingsPanelClass}>
            <div className="flex flex-col gap-4 border-b border-slate-200 pb-4 md:flex-row md:items-start md:justify-between">
              <div>
                <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                  Safe cleanup
                </h3>
                <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                  Remove regenerable data only. Uploaded source files, persistent vectors, and saved chats stay untouched.
                </p>
              </div>

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
                  className={settingsPrimaryButtonClass}
                >
                  {cleanupPendingKey === "all"
                    ? siteConfig.settings.storageControls.cleaningLabel
                    : siteConfig.settings.storageControls.cleanAllLabel}
                </button>
              )}
            </div>

            {(cleanupError || cleanupMessage) && (
              <div
                className={`mt-4 rounded-xl px-3 py-2.5 text-sm ${
                  cleanupError
                    ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                    : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                }`}
              >
                {cleanupError || cleanupMessage}
              </div>
            )}

            {cleanableStorageItems.length > 0 ? (
              <div className="mt-4 grid gap-4 lg:grid-cols-2">
                {cleanableStorageItems.map((item) => (
                  <div key={item.key} className={settingsSubtlePanelClass}>
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          {item.label}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.16em] text-slate-400">
                          {statusLabels.cleanable}
                        </p>
                      </div>

                      <div className="text-right">
                        <p className="text-lg font-semibold tracking-tight text-slate-950">
                          {formatBytes(item.size_bytes)}
                        </p>
                        <button
                          type="button"
                          onClick={() =>
                            void handleCleanup(
                              [item.key],
                              `${siteConfig.settings.storageControls.cleanupConfirmSingle}\n\n${item.label}`
                            )
                          }
                          disabled={cleanupPendingKey !== null}
                          className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
                        >
                          {cleanupPendingKey === item.key
                            ? siteConfig.settings.storageControls.cleaningLabel
                            : siteConfig.settings.storageControls.cleanLabel}
                        </button>
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
              <div className="mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50/80 px-4 py-8 text-center text-sm text-slate-500">
                No safe cleanup targets are available right now.
              </div>
            )}
          </section>
        )}

        {activeTab === "runtime" && (
          <form onSubmit={handleRuntimeSave} className={settingsPanelClass}>
            <div className="mb-5">
              <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                {siteConfig.settings.runtimeTitle}
              </h3>
              <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
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
                  className={settingsInputClass}
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
                  className={settingsInputClass}
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
                  className={settingsInputClass}
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
                  className={settingsInputClass}
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm font-medium text-slate-700">
                  Active wiring
                </span>
                <div className={`${settingsSubtlePanelClass} space-y-2 text-sm text-slate-600`}>
                  <div className="flex items-center justify-between gap-3">
                    <span>Chat model</span>
                    <span className="font-medium text-slate-900">
                      {runtimeSettings.ollama_default_model || "Not set"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>Embed model</span>
                    <span className="font-medium text-slate-900">
                      {runtimeSettings.ollama_embed_model || "Not set"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-3">
                    <span>Qdrant</span>
                    <span className="font-medium text-slate-900">
                      {runtimeSettings.qdrant_url || "Not set"}
                    </span>
                  </div>
                </div>
              </label>
            </div>

            <div className="mt-5 flex flex-col gap-3 border-t border-slate-200 pt-5 md:flex-row md:items-center md:justify-between">
              <p className="max-w-2xl text-sm text-slate-500">
                {siteConfig.settings.helperText}
              </p>
              <button
                type="submit"
                disabled={isSavingRuntime}
                className={settingsPrimaryButtonClass}
              >
                {isSavingRuntime
                  ? siteConfig.settings.savingButton
                  : siteConfig.settings.saveButton}
              </button>
            </div>
          </form>
        )}

        {activeTab === "retrieval" && (
          <form onSubmit={handleRuntimeSave} className={settingsPanelClass}>
            <div className="mb-5">
              <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                Retrieval and chunking
              </h3>
              <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                Tune how much context we pull in and how documents are split before indexing.
              </p>
            </div>

            {(runtimeError || runtimeMessage) && (
              <div
                className={`mb-4 rounded-xl px-3 py-2.5 text-sm ${
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
                  className={settingsInputClass}
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
                  className={settingsInputClass}
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
                  className={settingsInputClass}
                />
              </label>

              <label className="space-y-2">
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
                  className={settingsInputClass}
                />
              </label>
            </div>

            <div className={`mt-4 ${settingsSubtlePanelClass}`}>
              <p className="text-sm font-medium text-slate-500">What changes when you save</p>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                New retrieval requests use the updated limit and score threshold. New indexing runs use the updated chunk size and overlap.
              </p>
            </div>

            <div className="mt-5 flex flex-col gap-3 border-t border-slate-200 pt-5 md:flex-row md:items-center md:justify-between">
              <p className="max-w-2xl text-sm text-slate-500">
                {siteConfig.settings.helperText}
              </p>
              <button
                type="submit"
                disabled={isSavingRuntime}
                className={settingsPrimaryButtonClass}
              >
                {isSavingRuntime
                  ? siteConfig.settings.savingButton
                  : siteConfig.settings.saveButton}
              </button>
            </div>
          </form>
        )}

        {activeTab === "security" && (
          <div className="space-y-4">
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.adminAuth}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {authStatus?.auth_enabled
                    ? siteConfig.settings.securityValues.enabled
                    : siteConfig.settings.securityValues.disabled}
                </p>
                <p className="mt-1.5 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                  {authStatus?.auth_configured
                    ? siteConfig.settings.securityValues.configured
                    : siteConfig.settings.securityValues.notConfigured}
                </p>
              </div>

              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.safeMode}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {authStatus?.safe_mode_enabled
                    ? siteConfig.settings.securityValues.enabled
                    : siteConfig.settings.securityValues.disabled}
                </p>
                <p className="mt-1.5 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                  {authStatus?.authenticated
                    ? siteConfig.settings.securityValues.unlocked
                    : siteConfig.settings.securityValues.locked}
                </p>
              </div>

              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.protectedAreas}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityProtectedAreas.length}
                </p>
                <p className="mt-1.5 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                  Active protections
                </p>
              </div>

              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">
                  {siteConfig.settings.securityCards.futureControls}
                </p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityFutureControls.length}
                </p>
                <p className="mt-1.5 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                  Planned next
                </p>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className={settingsPanelClass}>
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityCards.protectedAreas}
                </h4>
                <div className="mt-4 space-y-2">
                  {siteConfig.settings.securityProtectedAreas.map((item) => (
                    <div
                      key={item}
                      className="border-b border-slate-200/80 pb-2 text-sm text-slate-700 last:border-b-0 last:pb-0"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>

              <div className={settingsPanelClass}>
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityCards.futureControls}
                </h4>
                <div className="mt-4 space-y-2">
                  {siteConfig.settings.securityFutureControls.map((item) => (
                    <div
                      key={item}
                      className="border-b border-dashed border-slate-300/90 pb-2 text-sm text-slate-700 last:border-b-0 last:pb-0"
                    >
                      {item}
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <div className={settingsPanelClass}>
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  {siteConfig.settings.securityCards.howItWorks}
                </h4>
                <div className="mt-4 space-y-2 text-sm leading-6 text-slate-700">
                  <p>{siteConfig.settings.auth.lockHelp}</p>
                  <p>{siteConfig.settings.auth.envToggleHelp}</p>
                </div>
              </div>

              <div
                className={`${settingsPanelClass} ${
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
                className={`${settingsPanelClass} ${
                  authStatus?.safe_mode_enabled
                    ? "border border-emerald-200 bg-emerald-50/90"
                    : "border border-slate-200/90 bg-white/95"
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

        {activeTab === "audit" && (
          <div className="space-y-4">
            <section className="grid gap-4 md:grid-cols-3">
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Events loaded</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {auditEvents.length}
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Warnings</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {auditWarningCount}
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Errors</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {auditErrorCount}
                </p>
              </div>
            </section>

            <section className={settingsPanelClass}>
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                    {siteConfig.settings.securityAuditTitle}
                  </h4>
                  <p className="mt-1.5 max-w-3xl text-sm leading-6 text-slate-500">
                    {siteConfig.settings.securityAuditSubtitle}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => void loadAuditEvents()}
                    disabled={isAuditLoading}
                    className={settingsSecondaryButtonClass}
                  >
                    {isAuditLoading
                      ? "Refreshing..."
                      : siteConfig.settings.securityAuditRefreshLabel}
                  </button>
                  <Link href="/logs" className={settingsSecondaryButtonClass}>
                    {siteConfig.settings.securityAuditOpenLogsLabel}
                  </Link>
                </div>
              </div>

              {auditError && (
                <div className="mt-4 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-red-200">
                  {auditError}
                </div>
              )}

              <div className="mt-4 space-y-2">
                {auditEvents.map((event) => (
                  <div
                    key={`${event.timestamp}-${event.event_type}-${event.message}`}
                    className="border-b border-slate-200/80 pb-3 last:border-b-0 last:pb-0"
                  >
                    <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-slate-950">
                            {event.message}
                          </p>
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                              event.status === "error"
                                ? "bg-red-100 text-red-700"
                                : event.status === "warning"
                                  ? "bg-amber-100 text-amber-700"
                                  : "bg-emerald-100 text-emerald-700"
                            }`}
                          >
                            {event.status}
                          </span>
                        </div>
                        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                          {event.event_type}
                        </p>
                        <p className="text-sm text-slate-600">
                          {renderAuditActor(event)}
                        </p>
                      </div>
                      <p className="text-sm text-slate-500">
                        {new Date(event.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </div>
                ))}

                {!isAuditLoading && auditEvents.length === 0 && !auditError && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-3 text-sm text-slate-500">
                    {siteConfig.settings.securityAuditEmpty}
                  </div>
                )}
              </div>
            </section>
          </div>
        )}

        {activeTab === "users" && (
          <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <section className={settingsPanelClass}>
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                    Local users
                  </h4>
                  <p className="mt-1.5 text-sm leading-6 text-slate-500">
                    Create admin and viewer accounts for this workspace. Admins control settings and connectors. Viewers use chat and knowledge.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void loadUsers()}
                  disabled={isUsersLoading}
                  className={settingsSecondaryButtonClass}
                >
                  {isUsersLoading ? "Refreshing..." : "Refresh"}
                </button>
              </div>

              {(usersError || usersStatusMessage) && (
                <div
                  className={`mt-4 rounded-xl px-3 py-2.5 text-sm ${
                    usersError
                      ? "bg-red-50 text-red-700 ring-1 ring-red-200"
                      : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                  }`}
                >
                  {usersError || usersStatusMessage}
                </div>
              )}

              <div className="mt-4 space-y-3">
                {users.map((user) => {
                  const isEditing = editingUserId === user.id;
                  const isSaving = savingUserId === user.id;

                  return (
                    <div key={user.id} className={settingsSubtlePanelClass}>
                      {isEditing ? (
                        <form
                          onSubmit={(event) => void handleSaveUser(event, user.id)}
                          className="space-y-3"
                        >
                          <div className="grid gap-3 md:grid-cols-2">
                            <label className="space-y-1.5">
                              <span className="text-sm font-medium text-slate-700">
                                Username
                              </span>
                              <input
                                type="text"
                                value={editingUserDraft.username ?? ""}
                                onChange={(event) =>
                                  setEditingUserDraft((current) => ({
                                    ...current,
                                    username: event.target.value,
                                  }))
                                }
                                className={settingsInputClass}
                              />
                            </label>

                            <label className="space-y-1.5">
                              <span className="text-sm font-medium text-slate-700">
                                Role
                              </span>
                              <select
                                value={editingUserDraft.role ?? "viewer"}
                                onChange={(event) =>
                                  setEditingUserDraft((current) => ({
                                    ...current,
                                    role: event.target.value as "admin" | "viewer",
                                  }))
                                }
                                className={settingsInputClass}
                              >
                                <option value="viewer">Viewer</option>
                                <option value="admin">Admin</option>
                              </select>
                            </label>
                          </div>

                          <label className="space-y-1.5">
                            <span className="text-sm font-medium text-slate-700">
                              New password
                            </span>
                            <input
                              type="password"
                              value={editingUserDraft.password ?? ""}
                              onChange={(event) =>
                                setEditingUserDraft((current) => ({
                                  ...current,
                                  password: event.target.value,
                                }))
                              }
                              placeholder="Leave blank to keep the current password"
                              className={settingsInputClass}
                            />
                          </label>

                          <label className="flex items-center gap-3 text-sm text-slate-700">
                            <input
                              type="checkbox"
                              checked={editingUserDraft.enabled ?? true}
                              onChange={(event) =>
                                setEditingUserDraft((current) => ({
                                  ...current,
                                  enabled: event.target.checked,
                                }))
                              }
                              className="h-4 w-4 rounded border-slate-300 text-slate-950 focus:ring-slate-400"
                            />
                            User enabled
                          </label>

                          <div className="flex flex-wrap gap-2">
                            <button
                              type="submit"
                              disabled={isSaving}
                              className={settingsPrimaryButtonClass}
                            >
                              {isSaving ? "Saving..." : "Save user"}
                            </button>
                            <button
                              type="button"
                              onClick={cancelEditingUser}
                              disabled={isSaving}
                              className={settingsSecondaryButtonClass}
                            >
                              Cancel
                            </button>
                          </div>
                        </form>
                      ) : (
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-sm font-semibold text-slate-950">
                                {user.username}
                              </p>
                              <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-600">
                                {user.role}
                              </span>
                              {!user.enabled && (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-700">
                                  disabled
                                </span>
                              )}
                              {user.locked_until && (
                                <span className="rounded-full border border-red-200 bg-red-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-red-700">
                                  locked
                                </span>
                              )}
                            </div>
                            <p className="mt-1.5 text-sm text-slate-500">
                              Last login: {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "Never"}
                            </p>
                            {user.locked_until ? (
                              <p className="mt-1 text-xs text-red-600">
                                Locked until {new Date(user.locked_until).toLocaleString()}
                              </p>
                            ) : (
                              <p className="mt-1 text-xs text-slate-400">
                                Failed login attempts: {user.failed_login_attempts ?? 0}
                              </p>
                            )}
                            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                              <span>Chats {user.stats?.conversation_count ?? 0}</span>
                              <span>Messages {user.stats?.message_count ?? 0}</span>
                              <span>Chat storage {formatBytes(user.stats?.conversation_storage_bytes ?? 0)}</span>
                              <span>Visible docs {user.stats?.accessible_document_count ?? 0}</span>
                              <span>Doc access {formatBytes(user.stats?.accessible_document_storage_bytes ?? 0)}</span>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => startEditingUser(user)}
                            className={settingsSecondaryButtonClass}
                          >
                            Edit
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}

                {!isUsersLoading && users.length === 0 && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-3 text-sm text-slate-500">
                    No local users found yet.
                  </div>
                )}
              </div>
            </section>

            <div className="space-y-4">
              <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
                <div className={settingsTileClass}>
                  <p className="text-sm font-medium text-slate-500">Total users</p>
                  <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                    {users.length}
                  </p>
                </div>
                <div className={settingsTileClass}>
                  <p className="text-sm font-medium text-slate-500">Enabled users</p>
                  <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                    {enabledUserCount}
                  </p>
                </div>
                <div className={settingsTileClass}>
                  <p className="text-sm font-medium text-slate-500">Admins</p>
                  <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                    {adminUserCount}
                  </p>
                </div>
                <div className={settingsTileClass}>
                  <p className="text-sm font-medium text-slate-500">Saved chats</p>
                  <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                    {totalConversationCount}
                  </p>
                </div>
                <div className={settingsTileClass}>
                  <p className="text-sm font-medium text-slate-500">Chat storage</p>
                  <p className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                    {formatBytes(totalConversationStorageBytes)}
                  </p>
                </div>
                <div className={settingsTileClass}>
                  <p className="text-sm font-medium text-slate-500">Accessible docs</p>
                  <p className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                    {formatBytes(totalAccessibleDocumentStorageBytes)}
                  </p>
                </div>
              </section>

              <section className={settingsPanelClass}>
                <h4 className="text-lg font-semibold tracking-tight text-slate-950">
                  Create user
                </h4>
                <p className="mt-1.5 text-sm leading-6 text-slate-500">
                  Start with viewers for everyday work, and keep admin accounts limited.
                </p>

                <form onSubmit={handleCreateUser} className="mt-4 space-y-3">
                  <label className="space-y-1.5">
                    <span className="text-sm font-medium text-slate-700">
                      Username
                    </span>
                    <input
                      type="text"
                      value={newUser.username}
                      onChange={(event) =>
                        setNewUser((current) => ({
                          ...current,
                          username: event.target.value,
                        }))
                      }
                      className={settingsInputClass}
                    />
                  </label>

                  <label className="space-y-1.5">
                    <span className="text-sm font-medium text-slate-700">
                      Password
                    </span>
                    <input
                      type="password"
                      value={newUser.password}
                      onChange={(event) =>
                        setNewUser((current) => ({
                          ...current,
                          password: event.target.value,
                        }))
                      }
                      className={settingsInputClass}
                    />
                  </label>

                  <label className="space-y-1.5">
                    <span className="text-sm font-medium text-slate-700">
                      Role
                    </span>
                    <select
                      value={newUser.role ?? "viewer"}
                      onChange={(event) =>
                        setNewUser((current) => ({
                          ...current,
                          role: event.target.value as "admin" | "viewer",
                        }))
                      }
                      className={settingsInputClass}
                    >
                      <option value="viewer">Viewer</option>
                      <option value="admin">Admin</option>
                    </select>
                  </label>

                  <label className="flex items-center gap-3 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={newUser.enabled ?? true}
                      onChange={(event) =>
                        setNewUser((current) => ({
                          ...current,
                          enabled: event.target.checked,
                        }))
                      }
                      className="h-4 w-4 rounded border-slate-300 text-slate-950 focus:ring-slate-400"
                    />
                    User enabled
                  </label>

                  <button
                    type="submit"
                    disabled={isCreatingUser}
                    className={`w-full ${settingsPrimaryButtonClass}`}
                  >
                    {isCreatingUser ? "Creating..." : "Create user"}
                  </button>
                </form>
              </section>
            </div>
          </div>
        )}

        {activeTab === "connectors" && (
          <ConnectorManager
            connectors={connectors}
            availableUsernames={enabledUsernames}
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

        {activeTab === "backups" && (
          <div className="space-y-4">
            <section className="grid gap-4 md:grid-cols-2">
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Backup export</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  Ready
                </p>
                <p className="mt-1.5 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                  Portable snapshot
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Restore file</p>
                <p className="mt-2 text-sm font-semibold tracking-tight text-slate-950">
                  {selectedBackupFile ? selectedBackupFile.name : "No file selected"}
                </p>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <section className={settingsPanelClass}>
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                      {siteConfig.settings.exportTitle}
                    </h3>
                    <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                      {siteConfig.settings.exportSubtitle}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => void handleExportBackup()}
                    disabled={isExporting}
                    className={settingsPrimaryButtonClass}
                  >
                    {isExporting
                      ? siteConfig.settings.exportingButton
                      : siteConfig.settings.exportButton}
                  </button>
                </div>

                {exportError && (
                  <div className="mt-4 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-red-200">
                    {exportError}
                  </div>
                )}
              </section>

              <section className={settingsPanelClass}>
                <div className="flex flex-col gap-3">
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                      {siteConfig.settings.importTitle}
                    </h3>
                    <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                      {siteConfig.settings.importSubtitle}
                    </p>
                  </div>

                  <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
                    {siteConfig.settings.importWarning}
                  </div>

                  <div className="space-y-2">
                    <label className={`inline-flex cursor-pointer ${settingsSecondaryButtonClass}`}>
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
                    className={settingsPrimaryButtonClass}
                  >
                    {isImporting
                      ? siteConfig.settings.importingButton
                      : siteConfig.settings.importButton}
                  </button>

                  {(importError || importMessage) && (
                    <div
                      className={`rounded-xl px-3 py-2.5 text-sm ${
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
            </section>
          </div>
        )}

        {activeTab === "logs" && (
          <div className="space-y-4">
            <section className="grid gap-4 md:grid-cols-3">
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Event preview</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {logsPreview?.events.length ?? 0}
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Raw lines</p>
                <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {logsPreview?.raw_lines.length ?? 0}
                </p>
              </div>
              <div className={settingsTileClass}>
                <p className="text-sm font-medium text-slate-500">Full viewer</p>
                <div className="mt-2">
                  <Link href="/logs" className={settingsSecondaryButtonClass}>
                    {siteConfig.settings.openLogsLabel}
                  </Link>
                </div>
              </div>
            </section>

            <section className="grid gap-4 xl:grid-cols-2">
              <section className={settingsPanelClass}>
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                      Recent events
                    </h3>
                    <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                      Quick preview of the latest backend activity without leaving settings.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void loadLogsPreview()}
                    disabled={isLogsLoading}
                    className={settingsSecondaryButtonClass}
                  >
                    {isLogsLoading ? "Refreshing..." : siteConfig.logs.refreshButton}
                  </button>
                </div>

                {logsError && (
                  <div className="mt-4 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-red-200">
                    {logsError}
                  </div>
                )}

                <div className="mt-4 space-y-2">
                  {logsPreview?.events.map((event) => (
                    <div
                      key={`${event.timestamp}-${event.event_type}-${event.message}`}
                      className="border-b border-slate-200/80 pb-3 last:border-b-0 last:pb-0"
                    >
                      <div className="flex flex-col gap-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-slate-950">
                            {event.message}
                          </p>
                          <span className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                            {event.status}
                          </span>
                        </div>
                        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">
                          {event.event_type}
                        </p>
                        <p className="text-sm text-slate-500">
                          {new Date(event.timestamp).toLocaleString()}
                        </p>
                      </div>
                    </div>
                  ))}

                  {!isLogsLoading && !logsError && (logsPreview?.events.length ?? 0) === 0 && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-3 text-sm text-slate-500">
                      {siteConfig.logs.emptyEvents}
                    </div>
                  )}
                </div>
              </section>

              <section className={settingsPanelClass}>
                <h3 className="text-lg font-semibold tracking-tight text-slate-950">
                  Raw backend log
                </h3>
                <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
                  Short preview of backend log lines. Use the full logs page when you need filtering or downloads.
                </p>

                <div className="mt-4 space-y-2 rounded-lg border border-slate-200 bg-slate-50/85 p-3 font-mono text-xs text-slate-700">
                  {logsPreview?.raw_lines.map((line, index) => (
                    <div key={`${index}-${line}`} className="border-b border-slate-200/80 pb-2 last:border-b-0 last:pb-0">
                      {line}
                    </div>
                  ))}

                  {!isLogsLoading && !logsError && (logsPreview?.raw_lines.length ?? 0) === 0 && (
                    <div className="text-sm font-sans text-slate-500">
                      {siteConfig.logs.emptyRaw}
                    </div>
                  )}
                </div>
              </section>
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
      </div>
    </AppShell>
  );
}

export default function SettingsPage() {
  return (
    <Suspense
      fallback={
        <AppShell contentClassName="p-4 md:p-5 xl:p-6">
          <section className="rounded-[1.25rem] border border-slate-200/80 bg-white/92 px-5 py-6 text-sm text-slate-600 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
            Loading settings...
          </section>
        </AppShell>
      }
    >
      <SettingsPageContent />
    </Suspense>
  );
}
