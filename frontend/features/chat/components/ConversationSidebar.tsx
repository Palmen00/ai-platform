"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { siteConfig } from "../../../config/site";
import {
  AuthStatusResponse,
  ConversationSummary,
  deleteConversation,
  getAuthStatus,
  getConversations,
  updateConversationTitle,
} from "../../../lib/api";

const CONVERSATIONS_UPDATED_EVENT = "conversations:updated";
const AUTH_UPDATED_EVENT = "auth:updated";

function formatUpdatedAt(value: string) {
  return new Date(value).toLocaleDateString([], {
    month: "short",
    day: "numeric",
  });
}

function requiresLoginFromAuth(authStatus: AuthStatusResponse | null) {
  return !!authStatus?.auth_enabled && !authStatus?.authenticated;
}

export function ConversationSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [editingConversationId, setEditingConversationId] = useState("");
  const [titleDraft, setTitleDraft] = useState("");
  const [pendingConversationId, setPendingConversationId] = useState("");
  const [openMenuConversationId, setOpenMenuConversationId] = useState("");
  const containerRef = useRef<HTMLDivElement | null>(null);
  const loadRequestIdRef = useRef(0);

  const activeConversationId =
    pathname === "/chat" ? searchParams.get("conversation") ?? "" : "";

  async function loadConversations() {
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;
    setIsLoading(true);
    setError("");

    try {
      const nextAuthStatus = await getAuthStatus();
      if (loadRequestIdRef.current !== requestId) {
        return;
      }
      setAuthStatus(nextAuthStatus);

      if (nextAuthStatus.auth_enabled && !nextAuthStatus.authenticated) {
        setConversations([]);
        return;
      }

      let payload = await getConversations();
      if (loadRequestIdRef.current !== requestId) {
        return;
      }

      if (payload.conversations.length === 0 && !requiresLoginFromAuth(nextAuthStatus)) {
        await new Promise((resolve) => window.setTimeout(resolve, 400));
        payload = await getConversations();
      }
      if (loadRequestIdRef.current !== requestId) {
        return;
      }
      setConversations(payload.conversations);
    } catch {
      if (loadRequestIdRef.current !== requestId) {
        return;
      }
      setError(siteConfig.chat.errors.conversationLoadError);
    } finally {
      if (loadRequestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }

  function startRename(conversation: ConversationSummary) {
    setEditingConversationId(conversation.id);
    setTitleDraft(conversation.title);
    setOpenMenuConversationId("");
    setError("");
  }

  function cancelRename() {
    setEditingConversationId("");
    setTitleDraft("");
  }

  async function handleRename(
    event: FormEvent<HTMLFormElement>,
    conversationId: string
  ) {
    event.preventDefault();
    const nextTitle = titleDraft.trim();
    if (!nextTitle) {
      return;
    }

    setPendingConversationId(conversationId);
    setError("");

    try {
      await updateConversationTitle(conversationId, nextTitle);
      cancelRename();
      await loadConversations();
      window.dispatchEvent(new Event(CONVERSATIONS_UPDATED_EVENT));
    } catch {
      setError(siteConfig.chat.errors.conversationUpdateError);
    } finally {
      setPendingConversationId("");
    }
  }

  async function handleDelete(conversationId: string) {
    setPendingConversationId(conversationId);
    setError("");

    try {
      await deleteConversation(conversationId);
      setConversations((current) =>
        current.filter((conversation) => conversation.id !== conversationId)
      );
      if (conversationId === activeConversationId) {
        router.replace("/chat");
      }
      setOpenMenuConversationId("");
      await loadConversations();
      window.dispatchEvent(new Event(CONVERSATIONS_UPDATED_EVENT));
    } catch {
      setError(siteConfig.chat.errors.conversationDeleteError);
    } finally {
      if (editingConversationId === conversationId) {
        cancelRename();
      }
      setPendingConversationId("");
    }
  }

  useEffect(() => {
    void loadConversations();
  }, [pathname, searchParams]);

  useEffect(() => {
    function handleConversationUpdated() {
      void loadConversations();
    }

    function handleAuthUpdated() {
      void loadConversations();
    }

    window.addEventListener(
      CONVERSATIONS_UPDATED_EVENT,
      handleConversationUpdated
    );
    window.addEventListener(AUTH_UPDATED_EVENT, handleAuthUpdated);

    return () => {
      window.removeEventListener(
        CONVERSATIONS_UPDATED_EVENT,
        handleConversationUpdated
      );
      window.removeEventListener(AUTH_UPDATED_EVENT, handleAuthUpdated);
    };
  }, [pathname, searchParams]);

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpenMenuConversationId("");
      }
    }

    document.addEventListener("mousedown", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, []);

  const normalizedQuery = searchQuery.trim().toLowerCase();
  const filteredConversations = normalizedQuery
    ? conversations.filter((conversation) => {
        const searchable = [
          conversation.title,
          conversation.model ?? "",
          formatUpdatedAt(conversation.updated_at),
        ]
          .join(" ")
          .toLowerCase();
        return searchable.includes(normalizedQuery);
      })
    : conversations;

  const visibleConversations = showAll
    ? filteredConversations
    : filteredConversations.slice(0, siteConfig.chat.sidebarConversationLimit);
  const hasMoreConversations =
    filteredConversations.length > siteConfig.chat.sidebarConversationLimit;
  const requiresLogin = requiresLoginFromAuth(authStatus);
  const newChatHref = requiresLogin ? "/login?next=/chat" : "/chat";

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3 px-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold tracking-tight text-slate-900">
            {siteConfig.chat.sidebarSubtitle}
          </h3>
          <p className="mt-1 text-xs uppercase tracking-[0.18em] text-slate-400">
            {siteConfig.chat.sidebarTitle}
          </p>
        </div>
        <Link
          href={newChatHref}
          className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-[11px] font-semibold text-slate-900 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
        >
          {requiresLogin ? "Sign in" : siteConfig.chat.newConversationLabel}
        </Link>
      </div>

      <div className="px-1">
        <input
          value={searchQuery}
          onChange={(event) => {
            setSearchQuery(event.target.value);
            setShowAll(false);
            setOpenMenuConversationId("");
          }}
          placeholder={siteConfig.chat.searchConversationPlaceholder}
          className="w-full rounded-2xl border border-slate-200 bg-white px-3.5 py-3 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-slate-300"
        />
      </div>

      {error && (
        <div className="mb-3 rounded-2xl bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">
          {error}
        </div>
      )}

      <div ref={containerRef} className="space-y-1 pr-1">
        {requiresLogin && !isLoading && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-600">
            Sign in through Login to load saved conversations.
          </div>
        )}

        {isLoading && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-500">
            {siteConfig.chat.loadingConversationsLabel}
          </div>
        )}

        {!isLoading && !requiresLogin && conversations.length === 0 && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-500">
            {siteConfig.chat.emptyConversationLabel}
          </div>
        )}

        {!isLoading && !requiresLogin && conversations.length > 0 && filteredConversations.length === 0 && (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm text-slate-500">
            {siteConfig.chat.emptyFilteredConversationLabel}
          </div>
        )}

        {!requiresLogin &&
          visibleConversations.map((conversation) => {
          const href = `/chat?conversation=${conversation.id}`;
          const isActive = conversation.id === activeConversationId;
          const isEditing = editingConversationId === conversation.id;
          const isPending = pendingConversationId === conversation.id;

          return (
            <div
              key={conversation.id}
              className={`relative block rounded-2xl border px-3 py-2.5 transition ${
                isActive
                  ? "border-slate-200 bg-white text-slate-950 shadow-sm"
                  : "border-transparent bg-transparent text-slate-700 hover:border-slate-200 hover:bg-white hover:shadow-sm"
              }`}
            >
              {isEditing ? (
                <form
                  onSubmit={(event) => void handleRename(event, conversation.id)}
                  className="space-y-2"
                >
                  <input
                    value={titleDraft}
                    onChange={(event) => setTitleDraft(event.target.value)}
                    placeholder={siteConfig.chat.renameConversationPlaceholder}
                    className="w-full rounded-xl border border-slate-300 bg-white px-2.5 py-2 text-[13px] text-slate-950 outline-none transition focus:border-slate-500"
                    autoFocus
                  />
                  <div className="flex gap-2">
                    <button
                      type="submit"
                      disabled={!titleDraft.trim() || isPending}
                      className="rounded-xl bg-slate-950 px-2.5 py-1.5 text-[11px] font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                    >
                      {siteConfig.chat.renameConversationSaveLabel}
                    </button>
                    <button
                      type="button"
                      onClick={cancelRename}
                      disabled={isPending}
                      className="rounded-xl border border-slate-300 px-2.5 py-1.5 text-[11px] font-semibold text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {siteConfig.chat.renameConversationCancelLabel}
                    </button>
                  </div>
                </form>
              ) : (
                <>
                  <div className="flex items-start gap-2">
                    <Link href={href} className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-medium leading-5">
                        {conversation.title}
                      </div>
                      <div
                        className={`mt-1 text-[11px] ${
                          isActive ? "text-slate-500" : "text-slate-400"
                        }`}
                      >
                        {conversation.message_count} {siteConfig.chat.messagesLabel}
                        {" - "}
                        {formatUpdatedAt(conversation.updated_at)}
                      </div>
                    </Link>

                    <div className="relative shrink-0">
                      <button
                        type="button"
                        onClick={() =>
                          setOpenMenuConversationId((current) =>
                            current === conversation.id ? "" : conversation.id
                          )
                        }
                        disabled={isPending}
                        className={`flex h-8 w-8 items-center justify-center rounded-xl transition ${
                          isActive
                            ? "text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                            : "text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        } disabled:cursor-not-allowed disabled:opacity-60`}
                        aria-label="Conversation actions"
                      >
                        <svg
                          aria-hidden="true"
                          viewBox="0 0 20 20"
                          fill="currentColor"
                          className="h-4 w-4"
                        >
                          <path d="M10 4.75a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5Zm0 6.5a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5Zm0 6.5a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5Z" />
                        </svg>
                      </button>

                      {openMenuConversationId === conversation.id && (
                        <div
                          className="absolute right-0 top-9 z-20 min-w-32 rounded-2xl border border-slate-200 bg-white shadow-lg"
                        >
                          <button
                            type="button"
                            onClick={() => startRename(conversation)}
                            className="block w-full px-3 py-2.5 text-left text-[12px] font-medium text-slate-700 transition hover:bg-slate-50"
                          >
                            {siteConfig.chat.renameConversationLabel}
                          </button>
                          <button
                            type="button"
                            onClick={() => void handleDelete(conversation.id)}
                            className="block w-full px-3 py-2.5 text-left text-[12px] font-medium text-red-700 transition hover:bg-red-50"
                          >
                            {siteConfig.chat.deleteConversationLabel}
                          </button>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          );
          })}
      </div>

      {!requiresLogin && hasMoreConversations && (
        <button
          onClick={() => setShowAll((current) => !current)}
          className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
        >
          {showAll
            ? siteConfig.chat.showLessConversationsLabel
            : siteConfig.chat.showMoreConversationsLabel}
        </button>
      )}
    </section>
  );
}
