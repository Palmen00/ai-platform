"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useEffect, useRef, useState } from "react";
import { siteConfig } from "../config/site";
import { ConversationSidebar } from "../features/chat/components/ConversationSidebar";
import {
  getSystemStatus,
  recoverIncompleteDocuments,
  SystemStatusResponse,
} from "../lib/api";

const SIDEBAR_STORAGE_KEY = "local-ai-shell-sidebar-hidden";

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
  hideSidebarFooter = false,
}: AppShellProps) {
  const pathname = usePathname();
  const [isSidebarHidden, setIsSidebarHidden] = useState(false);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(
    null
  );
  const [systemStatusError, setSystemStatusError] = useState("");
  const [recoveryNotice, setRecoveryNotice] = useState("");
  const [isRecoveryError, setIsRecoveryError] = useState(false);
  const [isRecovering, setIsRecovering] = useState(false);
  const previousOverallStatusRef = useRef<string | null>(null);
  const attemptedRecoveryCountRef = useRef<number | null>(null);

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

  return (
    <main className="min-h-screen bg-neutral-100 text-neutral-900">
      <div
        className={`grid min-h-screen grid-cols-1 ${
          isSidebarHidden ? "" : "lg:grid-cols-[280px_1fr]"
        }`}
      >
        <aside
          className={`border-b border-white/10 bg-slate-950 text-slate-100 lg:border-b-0 lg:border-r ${
            isSidebarHidden ? "hidden" : ""
          }`}
        >
          <div className="flex h-full flex-col gap-6 p-5 lg:sticky lg:top-0 lg:h-screen lg:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                  {siteConfig.shell.eyebrow}
                </p>
                <h1 className="mt-3 text-2xl font-semibold tracking-tight">
                  {siteConfig.name}
                </h1>
                <p className="mt-2 text-sm text-slate-400">
                  {siteConfig.dashboard.eyebrow}
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsSidebarHidden(true)}
                className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-300 transition hover:bg-white/10 hover:text-white"
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

            <nav className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible">
              {siteConfig.navigation.map((item) =>
                item.disabled ? (
                  <button
                    key={item.label}
                    disabled
                    className="rounded-xl px-3 py-2.5 text-left text-sm font-medium text-slate-500"
                  >
                    {item.label}
                  </button>
                ) : (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={
                      item.href === pathname
                        ? "block rounded-xl bg-white px-3 py-2.5 text-sm font-medium text-slate-950 shadow-sm"
                        : "block rounded-xl px-3 py-2.5 text-sm font-medium text-slate-300 transition hover:bg-white/10 hover:text-white"
                    }
                  >
                    {item.label}
                  </Link>
                )
              )}
            </nav>

            {sidebarContent ? (
              <div className="min-h-0 flex-1">{sidebarContent}</div>
            ) : (
              <div className="min-h-0 flex-1">
                <ConversationSidebar />
              </div>
            )}

            {!hideSidebarFooter && (
              <div className="hidden rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-slate-300 lg:block">
                <div className="font-medium text-white">
                  {siteConfig.shell.deploymentTitle}
                </div>
                <p className="mt-2 leading-6 text-slate-400">
                  {siteConfig.shell.deploymentDescription}
                </p>
              </div>
            )}
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
