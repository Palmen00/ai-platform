"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { siteConfig } from "../config/site";
import { ConversationSidebar } from "../features/chat/components/ConversationSidebar";
import {
  AuthStatusResponse,
  getAuthStatus,
  getSystemStatus,
  loginUser,
  logoutAdmin,
  recoverIncompleteDocuments,
  SystemStatusResponse,
} from "../lib/api";

const SIDEBAR_STORAGE_KEY = "local-ai-shell-sidebar-hidden";
const AUTH_UPDATED_EVENT = "auth:updated";

function getNavIcon(href: string) {
  if (href === "/chat") {
    return (
      <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="h-5 w-5">
        <path
          d="M6.5 4.5h7a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-7l-2 2v-11a2 2 0 0 1 2-2Z"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  if (href === "/knowledge") {
    return (
      <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="h-5 w-5">
        <path
          d="M5.5 4.5h6l3 3v8a1 1 0 0 1-1 1h-8a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1Z"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M11.5 4.5v3h3"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" className="h-5 w-5">
      <path
        d="M10 3.5v13m6.5-6.5h-13"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function getUserInitials(username?: string | null) {
  const normalized = (username ?? "").trim();
  if (!normalized) {
    return "AI";
  }

  const parts = normalized.split(/\s+/).filter(Boolean);
  if (parts.length === 1) {
    return normalized.slice(0, 2).toUpperCase();
  }

  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
}

type AppShellProps = {
  children: ReactNode;
  contentClassName?: string;
  sidebarContent?: ReactNode;
  hideSidebarFooter?: boolean;
};

export function AppShell({
  children,
  contentClassName,
  sidebarContent,
}: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [isSidebarHidden, setIsSidebarHidden] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [profileUsername, setProfileUsername] = useState("Admin");
  const [profilePassword, setProfilePassword] = useState("");
  const [isProfileSigningIn, setIsProfileSigningIn] = useState(false);
  const [profileAuthError, setProfileAuthError] = useState("");
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(
    null
  );
  const [systemStatusError, setSystemStatusError] = useState("");
  const [recoveryNotice, setRecoveryNotice] = useState("");
  const [isRecoveryError, setIsRecoveryError] = useState(false);
  const [isRecovering, setIsRecovering] = useState(false);
  const previousOverallStatusRef = useRef<string | null>(null);
  const attemptedRecoveryCountRef = useRef<number | null>(null);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const savedValue = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
    const frameId = window.requestAnimationFrame(() => {
      setIsSidebarHidden(savedValue === "true");
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      SIDEBAR_STORAGE_KEY,
      isSidebarHidden ? "true" : "false"
    );
  }, [isSidebarHidden]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!profileMenuRef.current?.contains(event.target as Node)) {
        setIsProfileMenuOpen(false);
      }
    }

    if (!isProfileMenuOpen) {
      return;
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [isProfileMenuOpen]);

  useEffect(() => {
    let isMounted = true;

    async function loadAuthStatus() {
      try {
        const payload = await getAuthStatus();
        if (!isMounted) {
          return;
        }

        setAuthStatus(payload);
      } catch {
        if (!isMounted) {
          return;
        }

        setAuthStatus(null);
      }
    }

    function handleAuthUpdated() {
      void loadAuthStatus();
    }

    void loadAuthStatus();
    window.addEventListener(AUTH_UPDATED_EVENT, handleAuthUpdated);

    return () => {
      isMounted = false;
      window.removeEventListener(AUTH_UPDATED_EVENT, handleAuthUpdated);
    };
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function loadSystemStatus() {
      try {
        const payload = await getSystemStatus();
        if (!isMounted) {
          return;
        }

        setSystemStatus(payload);
        setSystemStatusError("");
      } catch {
        if (!isMounted) {
          return;
        }

        setSystemStatus(null);
        setSystemStatusError(siteConfig.shell.systemWarningFallback);
      }
    }

    void loadSystemStatus();
    const intervalId = window.setInterval(() => {
      void loadSystemStatus();
    }, 45000);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (systemStatus?.status !== "ok") {
      previousOverallStatusRef.current = systemStatus?.status ?? null;
      attemptedRecoveryCountRef.current = null;
      setRecoveryNotice("");
      setIsRecoveryError(false);
      return;
    }

    const previousOverallStatus = previousOverallStatusRef.current;
    const hasRecovered =
      previousOverallStatus !== null && previousOverallStatus !== "ok";
    previousOverallStatusRef.current = systemStatus.status;

    async function handleRecovery() {
      const retriableDocuments = systemStatus.recovery.retriable_documents;
      const shouldAttemptRecovery =
        systemStatus.recovery.auto_retry_recommended &&
        attemptedRecoveryCountRef.current !== retriableDocuments;

      if (shouldAttemptRecovery) {
        attemptedRecoveryCountRef.current = retriableDocuments;
        setIsRecovering(true);

        try {
          const payload = await recoverIncompleteDocuments();
          if (payload.retried_count > 0) {
            setRecoveryNotice(
              `${siteConfig.shell.recoveryTitle}. ${payload.retried_count} documents were retried.`
            );
          } else {
            setRecoveryNotice(siteConfig.knowledge.messages.recoverNoop);
          }
          setIsRecoveryError(false);

          const nextStatus = await getSystemStatus();
          setSystemStatus(nextStatus);
          setSystemStatusError("");
        } catch {
          setRecoveryNotice(siteConfig.shell.recoveryError);
          setIsRecoveryError(true);
        } finally {
          setIsRecovering(false);
        }
        return;
      }

      if (hasRecovered) {
        setRecoveryNotice(
          systemStatus.recovery.retriable_documents > 0
            ? siteConfig.shell.recoveryFallback
            : siteConfig.shell.recoveryNoop
        );
        setIsRecoveryError(false);
      }
    }

    void handleRecovery();
  }, [systemStatus]);

  const dependencyWarnings = systemStatus
    ? [
        systemStatus.ollama.status !== "ok"
          ? `Ollama: ${systemStatus.ollama.detail || "offline"}`
          : "",
        systemStatus.qdrant.status !== "ok"
          ? `Qdrant: ${systemStatus.qdrant.detail || "offline"}`
          : "",
      ].filter(Boolean)
    : [];
  const showSystemWarningBanner =
    pathname !== "/settings" &&
    (systemStatusError.length > 0 || dependencyWarnings.length > 0);
  const showRecoveryBanner =
    pathname !== "/settings" &&
    systemStatus?.status === "ok" &&
    recoveryNotice.length > 0;

  const authEnabled = !!authStatus?.auth_enabled;
  const isAuthenticated = !!authStatus?.authenticated;
  const isAdmin = authStatus?.role === "admin";

  async function handleProfileSignIn() {
    setProfileAuthError("");
    setIsProfileSigningIn(true);

    try {
      const nextStatus = await loginUser(profileUsername, profilePassword);
      setAuthStatus(nextStatus);
      setProfilePassword("");
      setIsProfileMenuOpen(false);
      window.dispatchEvent(new Event(AUTH_UPDATED_EVENT));
      router.refresh();
    } catch {
      setProfileAuthError("Could not sign in with those credentials.");
    } finally {
      setIsProfileSigningIn(false);
    }
  }

  async function handleSignOut() {
    await logoutAdmin();
    const nextStatus = authStatus
      ? {
          ...authStatus,
          authenticated: false,
          username: null,
          role: null,
          session_expires_at: null,
        }
      : null;
    setAuthStatus(nextStatus);
    setIsProfileMenuOpen(false);
    window.dispatchEvent(new Event(AUTH_UPDATED_EVENT));
    router.push(`/login?next=${encodeURIComponent(pathname || "/chat")}`);
  }

  return (
    <main className="min-h-screen bg-neutral-100 text-neutral-900">
      <div
        className={`grid min-h-screen grid-cols-1 ${
          isSidebarHidden ? "" : "lg:grid-cols-[280px_1fr]"
        }`}
      >
        <aside
          className={`border-b border-slate-200 bg-[#fbfbf9] text-slate-900 lg:border-b-0 lg:border-r ${
            isSidebarHidden ? "hidden" : ""
          }`}
        >
            <div className="flex h-full min-h-0 flex-col p-3.5 lg:sticky lg:top-0 lg:h-screen lg:p-4">
              <div className="flex items-center justify-between gap-4 px-1">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-sm font-semibold text-white shadow-sm">
                    {getUserInitials(siteConfig.name)}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-[1.3rem] font-semibold tracking-tight text-slate-950">
                      {siteConfig.name}
                    </p>
                    <p className="mt-0.5 text-[13px] text-slate-500">
                      {siteConfig.dashboard.eyebrow}
                    </p>
                  </div>
                </div>

              <button
                type="button"
                onClick={() => setIsSidebarHidden(true)}
                className="flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-slate-500 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800"
                aria-label={siteConfig.shell.closeSidebarLabel}
                title={siteConfig.shell.closeSidebarLabel}
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  fill="none"
                  className="h-4 w-4"
                >
                  <path
                    d="M12.5 4.5 7 10l5.5 5.5"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>

            <div className="sidebar-scroll-left mt-8 min-h-0 flex-1 overflow-y-auto pl-1">
              <div className="space-y-7 pb-6 pr-3">
                <section>
                <div className="mb-3 px-1.5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Workspace
                  </p>
                </div>
                <nav className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
                  {siteConfig.navigation.map((item) =>
                    item.disabled ? (
                      <button
                        key={item.label}
                        disabled
                        className="flex items-center gap-3 rounded-2xl px-3.5 py-3 text-left text-sm font-medium text-slate-400"
                      >
                        <span className="text-slate-300">{getNavIcon(item.href)}</span>
                        {item.label}
                      </button>
                    ) : (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={
                          item.href === pathname
                            ? "flex items-center gap-3 rounded-2xl bg-white px-3.5 py-3 text-sm font-medium text-slate-950 shadow-sm ring-1 ring-slate-200"
                            : "flex items-center gap-3 rounded-2xl px-3.5 py-3 text-sm font-medium text-slate-600 transition hover:bg-white hover:text-slate-950 hover:shadow-sm"
                        }
                      >
                        <span
                          className={
                            item.href === pathname ? "text-slate-950" : "text-slate-400"
                          }
                        >
                          {getNavIcon(item.href)}
                        </span>
                        {item.label}
                      </Link>
                    )
                  )}
                </nav>
              </section>

                <section>
                  <div className="mb-3 px-1.5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Chats
                  </p>
                  </div>
                  <div>
                    {sidebarContent ? sidebarContent : <ConversationSidebar />}
                  </div>
                </section>
              </div>
            </div>

            <div
              ref={profileMenuRef}
              className="relative shrink-0 border-t border-slate-200/80 pt-4"
            >
                {isProfileMenuOpen && (
                  <div className="absolute bottom-[calc(100%+0.75rem)] left-0 right-0 rounded-[1.8rem] bg-white p-4 shadow-[0_20px_60px_rgba(15,23,42,0.16)] ring-1 ring-slate-200">
                    {!authEnabled ? (
                      <div className="space-y-3">
                        <div className="flex items-center gap-3">
                          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-950 text-sm font-semibold text-white">
                            AI
                          </div>
                          <div>
                            <p className="text-sm font-medium text-slate-950">
                              Local environment
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              No sign-in required
                            </p>
                          </div>
                        </div>
                        <p className="text-xs leading-5 text-slate-600">
                          This app is running in open local mode. Anyone with
                          access to this environment can use the workspace until
                          authentication is enabled.
                        </p>
                        <div className="flex flex-wrap gap-2">
                          <Link
                            href="/settings?tab=security"
                            className="inline-flex rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-700 transition hover:border-slate-300 hover:bg-white hover:text-slate-900"
                          >
                            Open security
                          </Link>
                          <Link
                            href="/settings?tab=users"
                            className="inline-flex rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                          >
                            Open users
                          </Link>
                        </div>
                      </div>
                    ) : isAuthenticated ? (
                      <div className="space-y-4">
                        <div className="flex items-center gap-3">
                          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-amber-500 text-sm font-semibold text-white">
                            {getUserInitials(authStatus?.username)}
                          </div>
                          <div>
                            <p className="text-base font-semibold text-slate-950">
                              {authStatus?.username}
                            </p>
                            <p className="mt-1 text-sm text-slate-500">
                              {isAdmin ? "Admin account" : "Viewer account"}
                            </p>
                          </div>
                        </div>
                        <p className="text-xs leading-5 text-slate-600">
                          {isAdmin
                            ? "This session can manage settings, users, connectors, and protected document actions."
                            : "This session can use chat and knowledge within the permissions assigned to this account."}
                        </p>
                        <div className="space-y-2">
                          {isAdmin && (
                            <Link
                              href="/settings"
                              className="flex items-center rounded-xl px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 hover:text-slate-950"
                            >
                              Settings
                            </Link>
                          )}
                          <button
                            type="button"
                            onClick={() => void handleSignOut()}
                            className="flex w-full items-center rounded-xl px-3 py-2 text-left text-sm font-medium text-slate-700 transition hover:bg-slate-50 hover:text-slate-950"
                          >
                            Sign out
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex items-center gap-3">
                          <div className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-950 text-sm font-semibold text-white">
                            AI
                          </div>
                          <div>
                            <p className="text-sm font-medium text-slate-950">
                              Sign in
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              Local admin or viewer account
                            </p>
                          </div>
                        </div>
                        <p className="text-xs leading-5 text-slate-600">
                          Sign in to load saved chats, apply document access
                          rules, and unlock admin controls if your account has
                          that role.
                        </p>
                        {profileAuthError && (
                          <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
                            {profileAuthError}
                          </div>
                        )}
                        <div className="space-y-2">
                          <input
                            type="text"
                            value={profileUsername}
                            onChange={(event) =>
                              setProfileUsername(event.target.value)
                            }
                            placeholder="Username"
                            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-slate-400"
                          />
                          <input
                            type="password"
                            value={profilePassword}
                            onChange={(event) =>
                              setProfilePassword(event.target.value)
                            }
                            placeholder="Password"
                            className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-800 outline-none focus:border-slate-400"
                          />
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            onClick={() => void handleProfileSignIn()}
                            disabled={isProfileSigningIn}
                            className="inline-flex rounded-xl bg-slate-950 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                          >
                            {isProfileSigningIn ? "Signing in..." : "Sign in"}
                          </button>
                          <Link
                            href={`/login?next=${encodeURIComponent(pathname || "/chat")}`}
                            className="inline-flex rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
                          >
                            Full login
                          </Link>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <button
                  type="button"
                  onClick={() => setIsProfileMenuOpen((current) => !current)}
                  className="flex w-full items-center gap-3 rounded-2xl px-2 py-2 transition hover:bg-white/70"
                >
                  <div className="relative shrink-0">
                    <div className="flex h-11 w-11 items-center justify-center rounded-full bg-amber-500 text-sm font-semibold text-white">
                      {getUserInitials(authStatus?.username ?? siteConfig.name)}
                    </div>
                    <span className="absolute bottom-0 right-0 h-3.5 w-3.5 rounded-full border-2 border-[#fbfbf9] bg-emerald-500" />
                  </div>
                  <div className="min-w-0 flex-1 text-left">
                    <p className="truncate text-sm font-medium text-slate-950">
                      {isAuthenticated
                        ? authStatus?.username
                        : authEnabled
                          ? "Sign in"
                          : "Local access"}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-slate-500">
                      {isAuthenticated
                        ? isAdmin
                          ? "Admin"
                          : "Viewer"
                        : authEnabled
                          ? "Not signed in"
                          : "No sign-in required"}
                    </p>
                  </div>
                </button>
            </div>
          </div>
        </aside>

        <section
          className={`min-w-0 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.95),_rgba(243,246,251,1)_58%)] ${
            contentClassName ?? "p-6 md:p-8 xl:p-10"
          }`}
        >
          {isSidebarHidden && (
            <div className="mb-4">
              <button
                type="button"
                onClick={() => setIsSidebarHidden(false)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white/90 text-slate-700 shadow-sm transition hover:bg-white"
                aria-label={siteConfig.shell.openSidebarLabel}
                title={siteConfig.shell.openSidebarLabel}
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  fill="none"
                  className="h-4 w-4"
                >
                  <path
                    d="M7.5 4.5 13 10l-5.5 5.5"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          )}

          {showSystemWarningBanner && (
            <div className="mb-4 rounded-[1.5rem] border border-amber-200 bg-amber-50/90 px-4 py-3 text-sm text-amber-900 shadow-sm">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="font-semibold">
                    {siteConfig.shell.systemWarningTitle}
                  </div>
                  <p className="mt-1 leading-6 text-amber-800">
                    {systemStatusError || dependencyWarnings.join(" ")}
                  </p>
                </div>

                <Link
                  href="/settings"
                  className="inline-flex rounded-xl border border-amber-300 bg-white/80 px-3 py-2 text-sm font-medium text-amber-900 transition hover:bg-white"
                >
                  {siteConfig.shell.systemWarningOpenSettingsLabel}
                </Link>
              </div>
            </div>
          )}

          {showRecoveryBanner && (
            <div
              className={`mb-4 rounded-[1.5rem] px-4 py-3 text-sm shadow-sm ${
                isRecoveryError
                  ? "border border-amber-200 bg-amber-50/90 text-amber-900"
                  : "border border-emerald-200 bg-emerald-50/90 text-emerald-900"
              }`}
            >
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="font-semibold">
                    {siteConfig.shell.recoveryTitle}
                  </div>
                  <p
                    className={`mt-1 leading-6 ${
                      isRecoveryError ? "text-amber-800" : "text-emerald-800"
                    }`}
                  >
                    {isRecovering ? "Automatic recovery is running..." : recoveryNotice}
                  </p>
                </div>

                <Link
                  href="/knowledge"
                  className={`inline-flex rounded-xl px-3 py-2 text-sm font-medium transition ${
                    isRecoveryError
                      ? "border border-amber-300 bg-white/80 text-amber-900 hover:bg-white"
                      : "border border-emerald-300 bg-white/80 text-emerald-900 hover:bg-white"
                  }`}
                >
                  {siteConfig.shell.recoveryOpenKnowledgeLabel}
                </Link>
              </div>
            </div>
          )}

          {children}
        </section>
      </div>
    </main>
  );
}
