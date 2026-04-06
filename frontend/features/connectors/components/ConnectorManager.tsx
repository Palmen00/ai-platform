"use client";

import { FormEvent, useMemo, useState } from "react";
import { siteConfig } from "../../../config/site";
import { ConnectorManifest } from "../../../lib/api";

type ConnectorManagerProps = {
  connectors: ConnectorManifest[];
  availableUsernames: string[];
  isLoading: boolean;
  isRefreshing: boolean;
  isCreating: boolean;
  savingConnectorId: string;
  deletingConnectorId: string;
  syncingConnectorId: string;
  previewingConnectorId: string;
  isBrowsing: boolean;
  error: string;
  statusMessage: string;
  lastBrowseResult: {
    provider: string;
    folders: Array<{
      id: string;
      name: string;
      path: string;
      provider: string;
    }>;
  } | null;
  lastSyncResult: {
    connector_id: string;
    scanned_count: number;
    imported_count: number;
    updated_count: number;
    skipped_count: number;
    results: Array<{
      document_id: string;
      original_name: string;
      source_uri?: string | null;
      action: string;
    }>;
  } | null;
  onCreate: (payload: {
    name: string;
    provider: string;
    auth_mode: string;
    root_path?: string | null;
    container?: string | null;
    document_visibility?: "standard" | "hidden" | "restricted";
    access_usernames?: string[];
    include_patterns: string[];
    exclude_patterns: string[];
    export_formats: string[];
    provider_settings: Record<string, string>;
    notes?: string | null;
  }) => Promise<unknown>;
  onUpdate: (
    connectorId: string,
    payload: {
      name?: string;
      enabled?: boolean;
      auth_mode?: string;
      root_path?: string | null;
      container?: string | null;
      document_visibility?: "standard" | "hidden" | "restricted";
      access_usernames?: string[];
      include_patterns?: string[];
      exclude_patterns?: string[];
      export_formats?: string[];
      provider_settings?: Record<string, string>;
      notes?: string | null;
    }
  ) => Promise<unknown>;
  onDelete: (connectorId: string) => Promise<unknown>;
  onRefresh: () => Promise<void>;
  onSync: (connectorId: string) => Promise<unknown>;
  onPreviewSync: (connectorId: string) => Promise<unknown>;
  onBrowse: (payload: {
    provider: string;
    auth_mode?: string;
    root_path?: string | null;
    provider_settings?: Record<string, string>;
  }) => Promise<unknown>;
};

const RECOMMENDED_INCLUDE_PATTERNS = [
  "*.pdf",
  "*.docx",
  "*.xlsx",
  "*.pptx",
  "*.txt",
  "*.text",
  "*.md",
  "*.markdown",
  "*.mdx",
  "*.json",
  "*.jsonl",
  "*.ndjson",
  "*.csv",
  "*.tsv",
  "*.yml",
  "*.yaml",
  "*.toml",
  "*.ini",
  "*.cfg",
  "*.conf",
  "*.env",
  "*.properties",
  "*.xml",
  "*.py",
  "*.js",
  "*.jsx",
  "*.ts",
  "*.tsx",
  "*.java",
  "*.cs",
  "*.go",
  "*.rs",
  "*.php",
  "*.rb",
  "*.c",
  "*.cc",
  "*.cpp",
  "*.cxx",
  "*.h",
  "*.hpp",
  "*.swift",
  "*.kt",
  "*.kts",
  "*.scala",
  "*.sh",
  "*.bash",
  "*.zsh",
  "*.ps1",
  "*.psm1",
  "*.psd1",
  "*.sql",
  "*.html",
  "*.htm",
  "*.css",
  "*.scss",
  "*.less",
  "*.vue",
  "*.svelte",
];

const IMAGE_EXCLUDE_PATTERNS = [
  "*.jpg",
  "*.jpeg",
  "*.png",
  "*.bmp",
  "*.tif",
  "*.tiff",
  "*.webp",
  "*.zip",
];

const OFFICE_ONLY_INCLUDE_PATTERNS = [
  "*.pdf",
  "*.docx",
  "*.xlsx",
  "*.pptx",
  "*.txt",
  "*.md",
  "*.json",
  "*.csv",
];

const CODE_AND_TEXT_INCLUDE_PATTERNS = [
  "*.txt",
  "*.text",
  "*.md",
  "*.markdown",
  "*.json",
  "*.jsonl",
  "*.csv",
  "*.tsv",
  "*.xml",
  "*.yml",
  "*.yaml",
  "*.toml",
  "*.ini",
  "*.cfg",
  "*.conf",
  "*.env",
  "*.properties",
  "*.py",
  "*.js",
  "*.jsx",
  "*.ts",
  "*.tsx",
  "*.java",
  "*.cs",
  "*.go",
  "*.rs",
  "*.php",
  "*.rb",
  "*.c",
  "*.cc",
  "*.cpp",
  "*.h",
  "*.hpp",
  "*.swift",
  "*.kt",
  "*.scala",
  "*.sh",
  "*.ps1",
  "*.sql",
  "*.html",
  "*.css",
  "*.scss",
  "*.less",
];

type SyncPreset = "recommended" | "office_only" | "code_and_text" | "all_text_like";

function formatProvider(provider: string) {
  if (provider === "google_drive") {
    return "Google Drive";
  }
  if (provider === "sharepoint") {
    return "SharePoint";
  }
  if (provider === "local") {
    return "Local folder";
  }
  return provider.replace(/_/g, " ");
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return siteConfig.connectors.neverSyncedLabel;
  }

  return new Date(value).toLocaleString();
}

function getPresetConfig(preset: SyncPreset) {
  if (preset === "office_only") {
    return {
      include_patterns: OFFICE_ONLY_INCLUDE_PATTERNS,
      exclude_patterns: IMAGE_EXCLUDE_PATTERNS,
      export_formats: ["docx", "xlsx", "pptx", "pdf"],
      helpText: siteConfig.connectors.presetHelpOfficeOnly,
    };
  }

  if (preset === "code_and_text") {
    return {
      include_patterns: CODE_AND_TEXT_INCLUDE_PATTERNS,
      exclude_patterns: IMAGE_EXCLUDE_PATTERNS,
      export_formats: ["docx", "xlsx", "pptx", "pdf"],
      helpText: siteConfig.connectors.presetHelpCodeAndText,
    };
  }

  if (preset === "all_text_like") {
    return {
      include_patterns: RECOMMENDED_INCLUDE_PATTERNS,
      exclude_patterns: IMAGE_EXCLUDE_PATTERNS,
      export_formats: ["docx", "xlsx", "pptx", "pdf"],
      helpText: siteConfig.connectors.presetHelpAllTextLike,
    };
  }

  return {
    include_patterns: RECOMMENDED_INCLUDE_PATTERNS,
    exclude_patterns: IMAGE_EXCLUDE_PATTERNS,
    export_formats: ["docx", "xlsx", "pptx", "pdf"],
    helpText: siteConfig.connectors.presetHelpRecommended,
  };
}

function inferPreset(connector: ConnectorManifest): SyncPreset {
  const includes = [...connector.include_patterns].sort().join("|");
  if (includes === [...OFFICE_ONLY_INCLUDE_PATTERNS].sort().join("|")) {
    return "office_only";
  }
  if (includes === [...CODE_AND_TEXT_INCLUDE_PATTERNS].sort().join("|")) {
    return "code_and_text";
  }
  if (includes === [...RECOMMENDED_INCLUDE_PATTERNS].sort().join("|")) {
    return "recommended";
  }
  return "all_text_like";
}

const connectorPanelClass =
  "rounded-[1.15rem] border border-slate-200/90 bg-white/95 p-4 shadow-[0_10px_24px_rgba(15,23,42,0.04)]";
const connectorSubtlePanelClass =
  "rounded-[1rem] border border-slate-200 bg-slate-50/85 p-4";
const connectorInputClass =
  "w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-slate-400";
const connectorMutedInputClass =
  "w-full rounded-xl border border-slate-200 bg-slate-100 px-3 py-2.5 text-sm text-slate-500 outline-none";
const connectorSecondaryButtonClass =
  "rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60";
const connectorPrimaryButtonClass =
  "rounded-xl border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60";

export function ConnectorManager({
  connectors,
  availableUsernames,
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
  lastBrowseResult,
  lastSyncResult,
  onCreate,
  onUpdate,
  onDelete,
  onRefresh,
  onSync,
  onPreviewSync,
  onBrowse,
}: ConnectorManagerProps) {
  const [provider, setProvider] = useState("google_drive");
  const [name, setName] = useState("Google Drive Root");
  const [rootPath, setRootPath] = useState("");
  const [container, setContainer] = useState("");
  const [documentVisibility, setDocumentVisibility] = useState<
    "standard" | "hidden" | "restricted"
  >("standard");
  const [accessUsernames, setAccessUsernames] = useState("");
  const [notes, setNotes] = useState("");
  const [folderId, setFolderId] = useState("");
  const [driveId, setDriveId] = useState("");
  const [maxFiles, setMaxFiles] = useState("");
  const [selectedPreset, setSelectedPreset] = useState<SyncPreset>("recommended");
  const [editingConnectorId, setEditingConnectorId] = useState("");
  const [editingName, setEditingName] = useState("");
  const [editingContainer, setEditingContainer] = useState("");
  const [editingDocumentVisibility, setEditingDocumentVisibility] = useState<
    "standard" | "hidden" | "restricted"
  >("standard");
  const [editingAccessUsernames, setEditingAccessUsernames] = useState("");
  const [editingRootPath, setEditingRootPath] = useState("");
  const [editingNotes, setEditingNotes] = useState("");
  const [editingFolderId, setEditingFolderId] = useState("");
  const [editingDriveId, setEditingDriveId] = useState("");
  const [editingMaxFiles, setEditingMaxFiles] = useState("");
  const [editingEnabled, setEditingEnabled] = useState(true);
  const [editingPreset, setEditingPreset] = useState<SyncPreset>("recommended");
  const [folderPickerTarget, setFolderPickerTarget] = useState("");

  const suggestedAuthMode =
    provider === "google_drive"
      ? "refresh_token"
      : provider === "sharepoint"
        ? "graph"
        : "manual";

  const suggestedContainer = useMemo(() => {
    if (container.trim()) {
      return container.trim();
    }
    if (provider === "google_drive") {
      return "Google Drive";
    }
    if (provider === "sharepoint") {
      return "SharePoint Library";
    }
    return "Local Folder";
  }, [container, provider]);

  const selectedPresetConfig = useMemo(
    () => getPresetConfig(selectedPreset),
    [selectedPreset]
  );

  function resetEditingState() {
    setEditingConnectorId("");
    setEditingName("");
    setEditingContainer("");
    setEditingDocumentVisibility("standard");
    setEditingAccessUsernames("");
    setEditingRootPath("");
    setEditingNotes("");
    setEditingFolderId("");
    setEditingDriveId("");
    setEditingMaxFiles("");
    setEditingEnabled(true);
    setEditingPreset("recommended");
  }

  function startEditing(connector: ConnectorManifest) {
    setEditingConnectorId(connector.id);
    setEditingName(connector.name);
    setEditingContainer(connector.container ?? "");
    setEditingDocumentVisibility(connector.document_visibility);
    setEditingAccessUsernames(connector.access_usernames.join(", "));
    setEditingRootPath(connector.root_path ?? "");
    setEditingNotes(connector.notes ?? "");
    setEditingFolderId(connector.provider_settings.folder_id ?? "");
    setEditingDriveId(connector.provider_settings.drive_id ?? "");
    setEditingMaxFiles(connector.provider_settings.max_files ?? "");
    setEditingEnabled(connector.enabled);
    setEditingPreset(inferPreset(connector));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    await onCreate({
      name: name.trim(),
      provider,
      auth_mode: suggestedAuthMode,
      root_path: provider === "local" ? rootPath.trim() || null : null,
      container: suggestedContainer,
      document_visibility: documentVisibility,
      access_usernames: parseAccessUsernames(accessUsernames),
      include_patterns: selectedPresetConfig.include_patterns,
      exclude_patterns: selectedPresetConfig.exclude_patterns,
      export_formats: selectedPresetConfig.export_formats,
      provider_settings: {
        ...(folderId.trim() ? { folder_id: folderId.trim() } : {}),
        ...(driveId.trim() ? { drive_id: driveId.trim() } : {}),
        ...(maxFiles.trim() ? { max_files: maxFiles.trim() } : {}),
      },
      notes: notes.trim() || null,
    });
  }

  async function handleSave(connector: ConnectorManifest) {
    const presetConfig = getPresetConfig(editingPreset);
    const updated = await onUpdate(connector.id, {
      name: editingName.trim() || connector.name,
      enabled: editingEnabled,
      root_path:
        connector.provider === "local" ? editingRootPath.trim() || null : null,
      container: editingContainer.trim() || null,
      document_visibility: editingDocumentVisibility,
      access_usernames: parseAccessUsernames(editingAccessUsernames),
      include_patterns: presetConfig.include_patterns,
      exclude_patterns: presetConfig.exclude_patterns,
      export_formats: presetConfig.export_formats,
      provider_settings: {
        ...(editingFolderId.trim() ? { folder_id: editingFolderId.trim() } : {}),
        ...(editingDriveId.trim() ? { drive_id: editingDriveId.trim() } : {}),
        ...(editingMaxFiles.trim() ? { max_files: editingMaxFiles.trim() } : {}),
      },
      notes: editingNotes.trim() || null,
    });

    if (updated) {
      resetEditingState();
    }
  }

  function parseAccessUsernames(value: string) {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function handleCreateBrowse() {
    setFolderPickerTarget("create");
    void onBrowse({
      provider,
      auth_mode: suggestedAuthMode,
      root_path: provider === "local" ? rootPath.trim() || null : null,
      provider_settings: {
        ...(folderId.trim() ? { folder_id: folderId.trim() } : {}),
        ...(driveId.trim() ? { drive_id: driveId.trim() } : {}),
      },
    });
  }

  function handleEditBrowse(connector: ConnectorManifest) {
    setFolderPickerTarget(connector.id);
    void onBrowse({
      provider: connector.provider,
      auth_mode: connector.auth_mode,
      root_path:
        connector.provider === "local" ? editingRootPath.trim() || null : null,
      provider_settings: {
        ...(editingFolderId.trim() ? { folder_id: editingFolderId.trim() } : {}),
        ...(editingDriveId.trim() ? { drive_id: editingDriveId.trim() } : {}),
      },
    });
  }

  function applyBrowsedFolder(
    target: "create" | "edit",
    connector: ConnectorManifest | null,
    folder: { id: string; path: string }
  ) {
    const effectiveProvider = target === "create" ? provider : connector?.provider;

    if (effectiveProvider === "google_drive") {
      if (target === "create") {
        setFolderId(folder.id);
      } else {
        setEditingFolderId(folder.id);
      }
      return;
    }

    if (effectiveProvider === "local") {
      if (target === "create") {
        setRootPath(folder.path);
      } else {
        setEditingRootPath(folder.path);
      }
    }
  }

  function renderFolderPicker(
    target: "create" | "edit",
    connector: ConnectorManifest | null = null
  ) {
    const isActive =
      folderPickerTarget === (target === "create" ? "create" : connector?.id);
    if (!isActive || !lastBrowseResult) {
      return null;
    }

    const selectedFolderId =
      target === "create" ? folderId : editingFolderId;
    const selectedFolderPath =
      target === "create" ? rootPath : editingRootPath;
    const selectedFolder = lastBrowseResult.folders.find((folder) =>
      lastBrowseResult.provider === "local"
        ? folder.path === selectedFolderPath
        : folder.id === selectedFolderId
    );

    return (
      <div className="mt-3 rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-600">
        <p className="font-semibold text-slate-900">
          {siteConfig.connectors.folderPickerTitle}
        </p>
        {selectedFolder && (
          <p className="mt-1 text-xs text-slate-500">
            {siteConfig.connectors.folderPickerSelectedPrefix}: {selectedFolder.path}
          </p>
        )}

        {lastBrowseResult.folders.length > 0 ? (
          <div className="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1">
            {lastBrowseResult.folders.map((folder) => (
              <div
                key={`${folder.provider}:${folder.id}`}
                className="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium text-slate-900">
                    {folder.name}
                  </div>
                  <div className="truncate text-xs text-slate-500">
                    {folder.path}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => applyBrowsedFolder(target, connector, folder)}
                  className="shrink-0 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100"
                >
                  {siteConfig.connectors.folderPickerPick}
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            {siteConfig.connectors.folderPickerEmpty}
          </p>
        )}
      </div>
    );
  }

  return (
    <section className={connectorPanelClass}>
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {siteConfig.connectors.title}
          </p>
          <h3 className="mt-1.5 text-lg font-semibold tracking-tight text-slate-950">
            {siteConfig.connectors.title}
          </h3>
          <p className="mt-1.5 max-w-3xl text-sm leading-6 text-slate-600">
            {siteConfig.connectors.subtitle}
          </p>
        </div>

        <button
          type="button"
          onClick={() => void onRefresh()}
          className={connectorSecondaryButtonClass}
        >
          {siteConfig.connectors.refreshButton}
        </button>
      </div>

      {(error || statusMessage) && (
        <div
          className={`mt-4 rounded-xl px-3 py-2.5 text-sm ${
            error
              ? "bg-red-50 text-red-700 ring-1 ring-red-200"
              : "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
          }`}
        >
          {error || statusMessage}
        </div>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
        <form
          onSubmit={(event) => void handleSubmit(event)}
          className={connectorSubtlePanelClass}
        >
          <div className="mb-4">
            <h4 className="text-base font-semibold text-slate-900">
              {siteConfig.connectors.createTitle}
            </h4>
            <p className="mt-1 text-sm text-slate-600">
              {siteConfig.connectors.createSubtitle}
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="block text-sm text-slate-700">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.fields.name}
              </span>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                className={connectorInputClass}
                required
              />
            </label>

            <label className="block text-sm text-slate-700">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.fields.provider}
              </span>
              <select
                value={provider}
                onChange={(event) => {
                  const nextProvider = event.target.value;
                  setProvider(nextProvider);
                  if (nextProvider === "google_drive") {
                    setName("Google Drive Root");
                  } else if (nextProvider === "sharepoint") {
                    setName("SharePoint Library");
                  } else {
                    setName("Local Folder");
                  }
                }}
                className={connectorInputClass}
              >
                <option value="google_drive">Google Drive</option>
                <option value="sharepoint">SharePoint</option>
                <option value="local">Local folder</option>
              </select>
            </label>

            <label className="block text-sm text-slate-700">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.fields.authMode}
              </span>
              <input
                value={suggestedAuthMode}
                readOnly
                className={connectorMutedInputClass}
              />
            </label>

                        <label className="block text-sm text-slate-700">
                          <span className="mb-2 block font-medium">
                            {siteConfig.connectors.fields.container}
                          </span>
              <input
                value={container}
                onChange={(event) => setContainer(event.target.value)}
                placeholder={suggestedContainer}
                className={connectorInputClass}
              />
            </label>

            <label className="block text-sm text-slate-700">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.fields.documentVisibility}
              </span>
              <select
                value={documentVisibility}
                onChange={(event) =>
                  setDocumentVisibility(
                    event.target.value as "standard" | "hidden" | "restricted"
                  )
                }
                className={connectorInputClass}
              >
                <option value="standard">
                  {siteConfig.connectors.documentVisibilityOptions.standard}
                </option>
                <option value="hidden">
                  {siteConfig.connectors.documentVisibilityOptions.hidden}
                </option>
                <option value="restricted">
                  {siteConfig.connectors.documentVisibilityOptions.restricted}
                </option>
              </select>
            </label>

            <label className="block text-sm text-slate-700 md:col-span-2">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.fields.accessUsers}
              </span>
              <input
                value={accessUsernames}
                onChange={(event) => setAccessUsernames(event.target.value)}
                placeholder={siteConfig.connectors.accessUsersPlaceholder}
                disabled={documentVisibility !== "restricted"}
                className={`${connectorInputClass} disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400`}
              />
              <p className="mt-2 text-xs leading-6 text-slate-500">
                {documentVisibility === "restricted"
                  ? siteConfig.connectors.accessUsersHelp
                  : siteConfig.connectors.accessUsersDisabledHelp}
                {availableUsernames.length > 0
                  ? ` ${siteConfig.connectors.availableUsersLabel}: ${availableUsernames.join(", ")}`
                  : ""}
              </p>
            </label>

            {provider === "local" && (
              <label className="block text-sm text-slate-700 md:col-span-2">
                <span className="mb-2 block font-medium">
                  {siteConfig.connectors.fields.rootPath}
                </span>
                <div className="flex gap-2">
                  <input
                    value={rootPath}
                    onChange={(event) => setRootPath(event.target.value)}
                    placeholder="C:\\Documents\\Knowledge"
                    className={connectorInputClass}
                    required={provider === "local"}
                  />
                  <button
                    type="button"
                    onClick={handleCreateBrowse}
                    disabled={isBrowsing || !rootPath.trim()}
                    className={`shrink-0 ${connectorSecondaryButtonClass}`}
                  >
                    {isBrowsing
                      ? siteConfig.connectors.browsingFoldersButton
                      : siteConfig.connectors.browseFoldersButton}
                  </button>
                </div>
              </label>
            )}

            {provider === "google_drive" && (
              <>
                <label className="block text-sm text-slate-700">
                  <span className="mb-2 block font-medium">
                    {siteConfig.connectors.fields.folderId}
                  </span>
                  <div className="flex gap-2">
                    <input
                      value={folderId}
                      onChange={(event) => setFolderId(event.target.value)}
                      placeholder={siteConfig.connectors.folderIdPlaceholder}
                      className={connectorInputClass}
                    />
                    <button
                      type="button"
                      onClick={handleCreateBrowse}
                      disabled={isBrowsing}
                      className={`shrink-0 ${connectorSecondaryButtonClass}`}
                    >
                      {isBrowsing
                        ? siteConfig.connectors.browsingFoldersButton
                        : siteConfig.connectors.browseFoldersButton}
                    </button>
                  </div>
                </label>

                <label className="block text-sm text-slate-700">
                  <span className="mb-2 block font-medium">
                    {siteConfig.connectors.fields.driveId}
                  </span>
                  <input
                    value={driveId}
                    onChange={(event) => setDriveId(event.target.value)}
                    placeholder={siteConfig.connectors.driveIdPlaceholder}
                    className={connectorInputClass}
                  />
                </label>
              </>
            )}

            <label className="block text-sm text-slate-700">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.fields.maxFiles}
              </span>
              <input
                value={maxFiles}
                onChange={(event) =>
                  setMaxFiles(event.target.value.replace(/[^\d]/g, ""))
                }
                inputMode="numeric"
                placeholder={siteConfig.connectors.maxFilesPlaceholder}
                className={connectorInputClass}
              />
            </label>

            <label className="block text-sm text-slate-700 md:col-span-2">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.presetLabel}
              </span>
              <select
                value={selectedPreset}
                onChange={(event) =>
                  setSelectedPreset(event.target.value as SyncPreset)
                }
                className={connectorInputClass}
              >
                <option value="recommended">
                  {siteConfig.connectors.presetRecommended}
                </option>
                <option value="office_only">
                  {siteConfig.connectors.presetOfficeOnly}
                </option>
                <option value="code_and_text">
                  {siteConfig.connectors.presetCodeAndText}
                </option>
                <option value="all_text_like">
                  {siteConfig.connectors.presetAllTextLike}
                </option>
              </select>
            </label>

            <label className="block text-sm text-slate-700 md:col-span-2">
              <span className="mb-2 block font-medium">
                {siteConfig.connectors.fields.notes}
              </span>
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={3}
                className={connectorInputClass}
                placeholder={siteConfig.connectors.notesPlaceholder}
              />
            </label>
          </div>

          {renderFolderPicker("create")}

          <div className="mt-4 rounded-lg border border-slate-200 bg-white px-3 py-3 text-xs leading-6 text-slate-500">
            <p className="font-medium text-slate-600">
              {siteConfig.connectors.setupTitle}
            </p>
            <p className="mt-1">{siteConfig.connectors.setupDescription}</p>
            <p className="mt-2">{selectedPresetConfig.helpText}</p>
            <p className="mt-2">{siteConfig.connectors.patternsHint}</p>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={isCreating}
              className={connectorPrimaryButtonClass}
            >
              {isCreating
                ? siteConfig.connectors.creatingButton
                : siteConfig.connectors.createButton}
            </button>
          </div>
        </form>

        <div className={connectorSubtlePanelClass}>
          <div className="mb-4">
            <h4 className="text-base font-semibold text-slate-900">
              {siteConfig.connectors.savedTitle}
            </h4>
            <p className="mt-1 text-sm text-slate-600">
              {siteConfig.connectors.savedSubtitle}
            </p>
          </div>

          <div className="space-y-3">
            {isLoading && connectors.length === 0 && (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-500">
                {siteConfig.connectors.loadingLabel}
              </div>
            )}

            {isRefreshing && connectors.length > 0 && (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-500">
                {siteConfig.connectors.refreshingLabel}
              </div>
            )}

            {!isLoading && connectors.length === 0 && (
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-500">
                {siteConfig.connectors.emptyState}
              </div>
            )}

            {connectors.map((connector) => (
              <div
                key={connector.id}
                className="rounded-lg border border-slate-200 bg-white px-3 py-3"
              >
                {editingConnectorId === connector.id ? (
                  <div className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      <label className="block text-sm text-slate-700">
                        <span className="mb-2 block font-medium">
                          {siteConfig.connectors.fields.name}
                        </span>
                        <input
                          value={editingName}
                          onChange={(event) => setEditingName(event.target.value)}
                          className={connectorInputClass}
                        />
                      </label>

                      <label className="block text-sm text-slate-700">
                        <span className="mb-2 block font-medium">
                          {siteConfig.connectors.fields.container}
                        </span>
                        <input
                          value={editingContainer}
                          onChange={(event) =>
                            setEditingContainer(event.target.value)
                          }
                            className={connectorInputClass}
                          />
                        </label>

                        <label className="block text-sm text-slate-700">
                          <span className="mb-2 block font-medium">
                            {siteConfig.connectors.fields.documentVisibility}
                          </span>
                          <select
                            value={editingDocumentVisibility}
                            onChange={(event) =>
                              setEditingDocumentVisibility(
                                event.target.value as
                                  | "standard"
                                  | "hidden"
                                  | "restricted"
                              )
                            }
                            className={connectorInputClass}
                          >
                            <option value="standard">
                              {siteConfig.connectors.documentVisibilityOptions.standard}
                            </option>
                            <option value="hidden">
                              {siteConfig.connectors.documentVisibilityOptions.hidden}
                            </option>
                            <option value="restricted">
                              {siteConfig.connectors.documentVisibilityOptions.restricted}
                            </option>
                          </select>
                        </label>

                        <label className="block text-sm text-slate-700 md:col-span-2">
                          <span className="mb-2 block font-medium">
                            {siteConfig.connectors.fields.accessUsers}
                          </span>
                          <input
                            value={editingAccessUsernames}
                            onChange={(event) =>
                              setEditingAccessUsernames(event.target.value)
                            }
                            placeholder={siteConfig.connectors.accessUsersPlaceholder}
                            disabled={editingDocumentVisibility !== "restricted"}
                            className={`${connectorInputClass} disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400`}
                          />
                          <p className="mt-2 text-xs leading-6 text-slate-500">
                            {editingDocumentVisibility === "restricted"
                              ? siteConfig.connectors.accessUsersHelp
                              : siteConfig.connectors.accessUsersDisabledHelp}
                            {availableUsernames.length > 0
                              ? ` ${siteConfig.connectors.availableUsersLabel}: ${availableUsernames.join(", ")}`
                              : ""}
                          </p>
                        </label>

                        {connector.provider === "local" && (
                          <label className="block text-sm text-slate-700 md:col-span-2">
                          <span className="mb-2 block font-medium">
                            {siteConfig.connectors.fields.rootPath}
                          </span>
                          <div className="flex gap-2">
                            <input
                              value={editingRootPath}
                              onChange={(event) =>
                                setEditingRootPath(event.target.value)
                              }
                              className={connectorInputClass}
                            />
                            <button
                              type="button"
                              onClick={() => handleEditBrowse(connector)}
                              disabled={isBrowsing || !editingRootPath.trim()}
                              className={`shrink-0 ${connectorSecondaryButtonClass}`}
                            >
                              {isBrowsing
                                ? siteConfig.connectors.browsingFoldersButton
                                : siteConfig.connectors.browseFoldersButton}
                            </button>
                          </div>
                        </label>
                      )}

                      {connector.provider === "google_drive" && (
                        <>
                          <label className="block text-sm text-slate-700">
                            <span className="mb-2 block font-medium">
                              {siteConfig.connectors.fields.folderId}
                            </span>
                            <div className="flex gap-2">
                              <input
                                value={editingFolderId}
                                onChange={(event) =>
                                  setEditingFolderId(event.target.value)
                                }
                                className={connectorInputClass}
                              />
                              <button
                                type="button"
                                onClick={() => handleEditBrowse(connector)}
                                disabled={isBrowsing}
                                className={`shrink-0 ${connectorSecondaryButtonClass}`}
                              >
                                {isBrowsing
                                  ? siteConfig.connectors.browsingFoldersButton
                                  : siteConfig.connectors.browseFoldersButton}
                              </button>
                            </div>
                          </label>

                          <label className="block text-sm text-slate-700">
                            <span className="mb-2 block font-medium">
                              {siteConfig.connectors.fields.driveId}
                            </span>
                            <input
                              value={editingDriveId}
                              onChange={(event) =>
                                setEditingDriveId(event.target.value)
                              }
                              className={connectorInputClass}
                            />
                          </label>
                        </>
                      )}

                      <label className="block text-sm text-slate-700">
                        <span className="mb-2 block font-medium">
                          {siteConfig.connectors.fields.maxFiles}
                        </span>
                        <input
                          value={editingMaxFiles}
                          onChange={(event) =>
                            setEditingMaxFiles(
                              event.target.value.replace(/[^\d]/g, "")
                            )
                          }
                          inputMode="numeric"
                          placeholder={siteConfig.connectors.maxFilesPlaceholder}
                          className={connectorInputClass}
                        />
                      </label>

                      <label className="block text-sm text-slate-700 md:col-span-2">
                        <span className="mb-2 block font-medium">
                          {siteConfig.connectors.presetLabel}
                        </span>
                        <select
                          value={editingPreset}
                          onChange={(event) =>
                            setEditingPreset(event.target.value as SyncPreset)
                          }
                          className={connectorInputClass}
                        >
                          <option value="recommended">
                            {siteConfig.connectors.presetRecommended}
                          </option>
                          <option value="office_only">
                            {siteConfig.connectors.presetOfficeOnly}
                          </option>
                          <option value="code_and_text">
                            {siteConfig.connectors.presetCodeAndText}
                          </option>
                          <option value="all_text_like">
                            {siteConfig.connectors.presetAllTextLike}
                          </option>
                        </select>
                      </label>

                      <label className="flex items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-700 md:col-span-2">
                        <input
                          type="checkbox"
                          checked={editingEnabled}
                          onChange={(event) =>
                            setEditingEnabled(event.target.checked)
                          }
                          className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-400"
                        />
                        <span>
                          {editingEnabled
                            ? siteConfig.connectors.enabledLabel
                            : siteConfig.connectors.disabledLabel}
                        </span>
                      </label>

                      <label className="block text-sm text-slate-700 md:col-span-2">
                        <span className="mb-2 block font-medium">
                          {siteConfig.connectors.fields.notes}
                        </span>
                        <textarea
                          value={editingNotes}
                          onChange={(event) => setEditingNotes(event.target.value)}
                          rows={3}
                          className={connectorInputClass}
                        />
                      </label>
                    </div>

                    {renderFolderPicker("edit", connector)}

                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void handleSave(connector)}
                        disabled={savingConnectorId === connector.id}
                        className={connectorPrimaryButtonClass}
                      >
                        {savingConnectorId === connector.id
                          ? siteConfig.connectors.savingButton
                          : siteConfig.connectors.saveButton}
                      </button>
                      <button
                        type="button"
                        onClick={resetEditingState}
                        className={connectorSecondaryButtonClass}
                      >
                        {siteConfig.connectors.cancelButton}
                      </button>
                    </div>
                  </div>
                ) : (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h5 className="text-sm font-semibold text-slate-900">
                        {connector.name}
                      </h5>
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.16em] text-slate-500">
                        {formatProvider(connector.provider)}
                      </span>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.16em] ${
                          connector.enabled
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-slate-100 text-slate-500"
                        }`}
                      >
                        {connector.enabled
                          ? siteConfig.connectors.enabledLabel
                          : siteConfig.connectors.disabledLabel}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {siteConfig.connectors.authModeLabel}: {connector.auth_mode}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      {siteConfig.connectors.lastSyncLabel}:{" "}
                      {formatTimestamp(connector.last_sync_at)}
                    </div>
                    {connector.container && (
                      <div className="mt-1 text-xs text-slate-500">
                        {siteConfig.connectors.containerLabel}: {connector.container}
                      </div>
                    )}
                    <div className="mt-1 text-xs text-slate-500">
                      {siteConfig.connectors.documentVisibilityLabel}:{" "}
                      {siteConfig.connectors.documentVisibilityOptions[connector.document_visibility]}
                    </div>
                    {connector.document_visibility === "restricted" &&
                      connector.access_usernames.length > 0 && (
                        <div className="mt-1 text-xs text-slate-500">
                          {siteConfig.connectors.accessUsersLabel}:{" "}
                          {connector.access_usernames.join(", ")}
                        </div>
                      )}
                    {connector.root_path && (
                      <div className="mt-1 text-xs text-slate-500">
                        {siteConfig.connectors.rootPathLabel}: {connector.root_path}
                      </div>
                    )}
                    {connector.provider_settings.folder_id && (
                      <div className="mt-1 break-all text-xs text-slate-500">
                        {siteConfig.connectors.folderIdLabel}:{" "}
                        {connector.provider_settings.folder_id}
                      </div>
                    )}
                    {connector.provider_settings.drive_id && (
                      <div className="mt-1 break-all text-xs text-slate-500">
                        {siteConfig.connectors.driveIdLabel}:{" "}
                        {connector.provider_settings.drive_id}
                      </div>
                    )}
                    {connector.provider_settings.max_files && (
                      <div className="mt-1 text-xs text-slate-500">
                        {siteConfig.connectors.maxFilesLabel}:{" "}
                        {connector.provider_settings.max_files}
                      </div>
                    )}
                    {connector.notes && (
                      <div className="mt-2 text-xs leading-6 text-slate-500">
                        {connector.notes}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void onPreviewSync(connector.id)}
                      disabled={
                        previewingConnectorId === connector.id ||
                        syncingConnectorId === connector.id ||
                        !connector.enabled
                      }
                      className={connectorSecondaryButtonClass}
                    >
                      {previewingConnectorId === connector.id
                        ? siteConfig.connectors.previewingSyncButton
                        : siteConfig.connectors.previewSyncButton}
                    </button>
                    <button
                      type="button"
                      onClick={() => void onSync(connector.id)}
                      disabled={
                        syncingConnectorId === connector.id ||
                        previewingConnectorId === connector.id ||
                        !connector.enabled
                      }
                      className={connectorSecondaryButtonClass}
                    >
                      {syncingConnectorId === connector.id
                        ? siteConfig.connectors.syncingButton
                        : siteConfig.connectors.syncButton}
                    </button>
                    <button
                      type="button"
                      onClick={() => startEditing(connector)}
                      className={connectorSecondaryButtonClass}
                    >
                      {siteConfig.connectors.editButton}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        void onUpdate(connector.id, { enabled: !connector.enabled })
                      }
                      disabled={savingConnectorId === connector.id}
                      className={connectorSecondaryButtonClass}
                    >
                      {connector.enabled
                        ? siteConfig.connectors.disableButton
                        : siteConfig.connectors.enableButton}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(siteConfig.connectors.deleteConfirm)) {
                          void onDelete(connector.id);
                        }
                      }}
                      disabled={deletingConnectorId === connector.id}
                      className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {deletingConnectorId === connector.id
                        ? siteConfig.connectors.deletingButton
                        : siteConfig.connectors.deleteButton}
                    </button>
                  </div>
                </div>
                )}

                <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5">
                    +{connector.include_patterns.length} include patterns
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5">
                    -{connector.exclude_patterns.length} exclude patterns
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5">
                    {connector.export_formats.join(", ")}
                  </span>
                </div>

                {lastSyncResult?.connector_id === connector.id && (
                  <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50/80 p-3">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold text-slate-900">
                        {siteConfig.connectors.syncSummaryTitle}
                      </p>
                      {lastSyncResult.dry_run && (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.16em] text-amber-700">
                          {siteConfig.connectors.previewBadge}
                        </span>
                      )}
                    </div>
                    <div className="mt-3 grid gap-2 sm:grid-cols-4">
                      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">
                          {siteConfig.connectors.syncSummaryScannedLabel}
                        </p>
                        <p className="mt-1 text-lg font-semibold text-slate-900">
                          {lastSyncResult.scanned_count}
                        </p>
                      </div>
                      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">
                          {siteConfig.connectors.syncSummaryImportedLabel}
                        </p>
                        <p className="mt-1 text-lg font-semibold text-slate-900">
                          {lastSyncResult.imported_count}
                        </p>
                      </div>
                      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">
                          {siteConfig.connectors.syncSummaryUpdatedLabel}
                        </p>
                        <p className="mt-1 text-lg font-semibold text-slate-900">
                          {lastSyncResult.updated_count}
                        </p>
                      </div>
                      <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">
                          {siteConfig.connectors.syncSummarySkippedLabel}
                        </p>
                        <p className="mt-1 text-lg font-semibold text-slate-900">
                          {lastSyncResult.skipped_count}
                        </p>
                      </div>
                    </div>

                    <div className="mt-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                        {siteConfig.connectors.syncResultsTitle}
                      </p>
                      {lastSyncResult.results.length > 0 ? (
                        <div className="mt-2 space-y-2">
                          {lastSyncResult.results.slice(0, 8).map((result) => (
                            <div
                              key={`${result.document_id}:${result.original_name}`}
                              className="flex flex-col gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600"
                            >
                              <div className="flex items-center justify-between gap-3">
                                <span className="truncate font-medium text-slate-900">
                                  {result.original_name}
                                </span>
                                <span className="shrink-0 rounded-full bg-slate-100 px-2 py-1 uppercase tracking-[0.14em] text-slate-500">
                                  {result.action}
                                </span>
                              </div>
                              {result.source_uri && (
                                <span className="truncate text-slate-500">
                                  {result.source_uri}
                                </span>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="mt-2 text-sm text-slate-500">
                          {siteConfig.connectors.syncResultsEmpty}
                        </p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
