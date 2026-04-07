"use client";

import { Suspense, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AppShell } from "../../components/AppShell";
import { siteConfig } from "../../config/site";
import {
  AuthStatusResponse,
  DocumentItem,
  DocumentPreview,
  getAuthStatus,
  getDocumentPreview,
  getDocuments,
  getModels,
  ModelItem,
} from "../../lib/api";
import { ChatMessage } from "../../features/chat/components/ChatMessage";
import { useChat } from "../../features/chat/hooks/useChat";
import { DocumentPreviewPanel } from "../../features/documents/components/DocumentPreviewPanel";

function ChatPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [model, setModel] = useState("");
  const [input, setInput] = useState("");
  const [authStatus, setAuthStatus] = useState<AuthStatusResponse | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [models, setModels] = useState<ModelItem[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [modelsError, setModelsError] = useState("");
  const [documentsError, setDocumentsError] = useState("");
  const [isLoadingModels, setIsLoadingModels] = useState(true);
  const [isLoadingDocuments, setIsLoadingDocuments] = useState(true);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [isChatCompressed, setIsChatCompressed] = useState(false);
  const [isScopeOpen, setIsScopeOpen] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<DocumentPreview | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [previewHighlightExcerpt, setPreviewHighlightExcerpt] = useState("");
  const requestedConversationId = searchParams.get("conversation") ?? "";
  const requestedDocumentIds = (searchParams.get("documents") ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const scrollFrameRef = useRef<number | null>(null);
  const scopeRef = useRef<HTMLDivElement | null>(null);
  const previewRequestKeyRef = useRef("");

  const {
    messages,
    activeConversationId,
    conversationDocumentIds,
    isLoading,
    conversationError,
    chatError,
    sendMessage,
    clearChat,
  } = useChat(model, requestedConversationId, selectedDocumentIds);

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
    if (isAuthLoading) {
      return;
    }

    if (authStatus?.auth_enabled && !authStatus?.authenticated) {
      setIsLoadingDocuments(false);
      setIsLoadingModels(false);
      setDocuments([]);
      setModels([]);
      setDocumentsError("");
      setModelsError("");
      return;
    }

    async function loadDependencies() {
      setIsLoadingModels(true);
      setModelsError("");
      setIsLoadingDocuments(true);
      setDocumentsError("");

      try {
        const [modelsResponse, documentsResponse] = await Promise.all([
          getModels(),
          getDocuments(),
        ]);
        const chatModels = modelsResponse.models.filter(
          (candidate) => candidate.capability !== "embedding"
        );
        const processedDocuments = documentsResponse.documents.filter(
          (document) => document.processing_status === "processed"
        );
        setModels(chatModels);
        setDocuments(processedDocuments);
        if (chatModels.length > 0) {
          setModel((current) => current || chatModels[0].id);
        }
      } catch {
        setModels([]);
        setModelsError(siteConfig.chat.modelLoadError);
        setDocuments([]);
        setDocumentsError(siteConfig.chat.scopeEmptyLabel);
      } finally {
        setIsLoadingModels(false);
        setIsLoadingDocuments(false);
      }
    }

    void loadDependencies();
  }, [authStatus?.auth_enabled, authStatus?.authenticated, isAuthLoading]);

  useEffect(() => {
    setSelectedDocumentIds((current) =>
      current.filter((documentId) =>
        documents.some((document) => document.id === documentId)
      )
    );
  }, [documents]);

  useEffect(() => {
    if (requestedDocumentIds.length === 0) {
      return;
    }

    setSelectedDocumentIds(
      requestedDocumentIds.filter((documentId) =>
        documents.some((document) => document.id === documentId)
      )
    );
  }, [documents, requestedDocumentIds]);

  useEffect(() => {
    if (requestedDocumentIds.length > 0 || !activeConversationId) {
      return;
    }

    setSelectedDocumentIds(
      conversationDocumentIds.filter((documentId) =>
        documents.some((document) => document.id === documentId)
      )
    );
  }, [
    activeConversationId,
    conversationDocumentIds,
    documents,
    requestedDocumentIds.length,
  ]);

  useEffect(() => {
    if (!isScopeOpen) {
      return;
    }

    function handleClickOutside(event: MouseEvent) {
      if (!scopeRef.current?.contains(event.target as Node)) {
        setIsScopeOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isScopeOpen]);

  function scrollToBottom(behavior: ScrollBehavior = "smooth") {
    const container = scrollContainerRef.current;
    if (!container) {
      return;
    }

    container.scrollTo({
      top: container.scrollHeight,
      behavior,
    });
    setShowScrollToBottom(false);
  }

  function updateScrollToBottomVisibility() {
    const container = scrollContainerRef.current;
    if (!container) {
      return;
    }

    setIsChatCompressed((current) => {
      if (current) {
        return container.scrollTop > 24;
      }

      return container.scrollTop > 72;
    });
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    setShowScrollToBottom(distanceFromBottom > 160);
  }

  function handleMessagesScroll() {
    updateScrollToBottomVisibility();
  }

  useLayoutEffect(() => {
    if (scrollFrameRef.current) {
      cancelAnimationFrame(scrollFrameRef.current);
    }

    scrollFrameRef.current = requestAnimationFrame(() => {
      scrollFrameRef.current = requestAnimationFrame(() => {
        scrollToBottom("auto");
        updateScrollToBottomVisibility();
        scrollFrameRef.current = null;
      });
    });
  }, [requestedConversationId, messages, isLoading]);

  useEffect(() => {
    return () => {
      if (scrollFrameRef.current) {
        cancelAnimationFrame(scrollFrameRef.current);
      }
    };
  }, []);

  async function handleSendMessage() {
    const messageText = input.trim();

    if (!model || !messageText || isLoading) {
      return;
    }

    setInput("");
    const nextConversationId = await sendMessage(messageText);

    if (!nextConversationId) {
      setInput(messageText);
      return;
    }

    if (nextConversationId !== requestedConversationId) {
      router.replace(`/chat?conversation=${nextConversationId}`);
    }
  }

  const isComposerCompact = isChatCompressed;
  const selectedDocuments = documents.filter((document) =>
    selectedDocumentIds.includes(document.id)
  );
  const scopeLabel =
    selectedDocumentIds.length === 0
      ? siteConfig.chat.scopeAllLabel
      : `${selectedDocumentIds.length} ${siteConfig.chat.scopeSelectedSuffix}`;

  function toggleDocumentSelection(documentId: string) {
    setSelectedDocumentIds((current) =>
      current.includes(documentId)
        ? current.filter((item) => item !== documentId)
        : [...current, documentId]
    );
  }

  async function openSourcePreview(
    documentId: string,
    chunkIndex: number,
    excerpt: string
  ) {
    const requestKey = `${documentId}:${chunkIndex}`;
    if (
      previewRequestKeyRef.current === requestKey &&
      (isPreviewLoading ||
        (preview?.document.id === documentId &&
          preview.focused_chunk_index === chunkIndex))
    ) {
      return;
    }

    previewRequestKeyRef.current = requestKey;
    setPreviewError("");
    setIsPreviewLoading(true);
    setPreviewHighlightExcerpt(excerpt);

    try {
      const nextPreview = await getDocumentPreview(documentId, chunkIndex);
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

  function closeSourcePreview() {
    previewRequestKeyRef.current = "";
    setPreview(null);
    setPreviewError("");
    setIsPreviewLoading(false);
    setPreviewHighlightExcerpt("");
  }

  if (isAuthLoading) {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8" hideSidebarFooter>
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-10 text-sm text-slate-600 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8">
          Loading chat...
        </section>
      </AppShell>
    );
  }

  if (authStatus?.auth_enabled && !authStatus.authenticated) {
    return (
      <AppShell contentClassName="p-4 md:p-6 xl:p-8" hideSidebarFooter>
        <section className="rounded-[2rem] border border-slate-200/80 bg-white/88 px-6 py-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:px-8 md:py-8">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
            {siteConfig.chat.title}
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950">
            Sign in to open chat
          </h2>
          <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">
            This workspace now protects saved conversations and document-scoped chat behind a signed-in account.
          </p>
          <button
            type="button"
            onClick={() => router.push("/login?next=/chat")}
            className="mt-5 inline-flex rounded-2xl bg-slate-950 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Open Login
          </button>
        </section>
      </AppShell>
    );
  }

  return (
    <AppShell contentClassName="p-3 md:p-4 lg:p-5" hideSidebarFooter>
      <div className="h-[calc(100vh-1.5rem)] overflow-hidden">
        <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-[2rem] border border-slate-200/80 bg-white/88 shadow-[0_32px_80px_rgba(15,23,42,0.12)] backdrop-blur">
          <header
            className={`shrink-0 border-b border-slate-200/80 px-5 transition-all duration-200 md:px-8 ${
              isChatCompressed ? "py-2" : "py-3"
            }`}
          >
            <div
              className={`flex flex-col transition-all duration-200 lg:flex-row lg:justify-between ${
                isChatCompressed
                  ? "gap-1.5 lg:items-center"
                  : "gap-3 lg:items-center"
              }`}
            >
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                  {siteConfig.chat.title}
                </p>
                <h2
                  className={`font-semibold tracking-tight text-slate-950 transition-all duration-200 ${
                    isChatCompressed
                      ? "mt-0.5 text-base md:text-lg"
                      : "mt-1 text-xl md:text-2xl"
                  }`}
                >
                  {siteConfig.chat.title}
                </h2>
                <p
                  className={`max-w-2xl text-sm leading-6 text-slate-500 transition-all duration-200 ${
                    isChatCompressed
                      ? "mt-0.5 line-clamp-1 text-[11px] leading-5"
                      : "mt-2 text-[13px] leading-5"
                  }`}
                >
                  {siteConfig.chat.subtitle}
                </p>
                {!isChatCompressed && (
                  <p className="mt-1.5 max-w-2xl text-[13px] leading-5 text-slate-500">
                    {siteConfig.chat.retrievalHint}
                  </p>
                )}
                {!isChatCompressed && selectedDocuments.length > 0 && (
                  <p className="mt-1.5 max-w-2xl text-[13px] leading-5 text-slate-500">
                    {siteConfig.chat.scopeLabel}:{" "}
                    {selectedDocuments
                      .slice(0, 2)
                      .map((document) => document.original_name)
                      .join(", ")}
                    {selectedDocuments.length > 2
                      ? ` +${selectedDocuments.length - 2}`
                      : ""}
                  </p>
                )}
              </div>

              <div
                className={`flex flex-col sm:flex-row sm:items-center ${
                  isChatCompressed ? "gap-1.5" : "gap-2"
                }`}
              >
                <div className="relative" ref={scopeRef}>
                  <button
                    type="button"
                    onClick={() => setIsScopeOpen((current) => !current)}
                    disabled={isLoadingDocuments || documents.length === 0}
                    className={`flex items-center gap-2 border border-slate-200 bg-slate-50 text-sm text-slate-700 outline-none transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-400 ${
                      isChatCompressed
                        ? "rounded-xl px-3 py-2"
                        : "rounded-xl px-3.5 py-2.5"
                    }`}
                    title={siteConfig.chat.scopeButtonLabel}
                  >
                    <span>{scopeLabel}</span>
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 20 20"
                      fill="none"
                      className="h-4 w-4"
                    >
                      <path
                        d="m5.5 7.5 4.5 4.5 4.5-4.5"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>

                  {isScopeOpen && (
                    <div className="absolute right-0 z-20 mt-2 w-[22rem] rounded-[1.25rem] border border-slate-200 bg-white p-3 shadow-[0_20px_50px_rgba(15,23,42,0.14)]">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-slate-900">
                            {siteConfig.chat.scopeLabel}
                          </p>
                          <p className="mt-1 text-xs text-slate-500">
                            {siteConfig.chat.scopeHelper}
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={() => setSelectedDocumentIds([])}
                          className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                        >
                          {siteConfig.chat.scopeResetLabel}
                        </button>
                      </div>

                      <div className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1">
                        {documents.length === 0 ? (
                          <div className="rounded-xl bg-slate-50 px-3 py-3 text-sm text-slate-500">
                            {documentsError || siteConfig.chat.scopeEmptyLabel}
                          </div>
                        ) : (
                          documents.map((document) => {
                            const isSelected = selectedDocumentIds.includes(
                              document.id
                            );

                            return (
                              <label
                                key={document.id}
                                className="flex cursor-pointer items-start gap-3 rounded-xl border border-slate-200 px-3 py-3 transition hover:bg-slate-50"
                              >
                                <input
                                  type="checkbox"
                                  checked={isSelected}
                                  onChange={() =>
                                    toggleDocumentSelection(document.id)
                                  }
                                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-slate-950 focus:ring-slate-400"
                                />
                                <span className="min-w-0">
                                  <span className="block truncate text-sm font-medium text-slate-900">
                                    {document.original_name}
                                  </span>
                                  <span className="mt-1 block text-xs text-slate-500">
                                    {document.chunk_count} chunks
                                  </span>
                                </span>
                              </label>
                            );
                          })
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={isLoadingModels || models.length === 0}
                  className={`border border-slate-200 bg-slate-50 text-sm text-slate-700 outline-none transition focus:border-slate-400 ${
                    isChatCompressed
                      ? "rounded-xl px-3 py-2"
                      : "rounded-xl px-3.5 py-2.5"
                  }`}
                >
                  {isLoadingModels && (
                    <option value="">{siteConfig.chat.modelLoadingLabel}</option>
                  )}

                  {!isLoadingModels && models.length === 0 && (
                    <option value="">{siteConfig.chat.noChatModelsLabel}</option>
                  )}

                  {models.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  onClick={() => {
                    clearChat();
                    router.replace("/chat");
                  }}
                  disabled={isLoading}
                  className={`border border-slate-200 text-sm font-medium text-slate-600 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60 ${
                    isChatCompressed
                      ? "rounded-xl px-3 py-2"
                      : "rounded-xl px-3.5 py-2.5"
                  }`}
                >
                  {siteConfig.chat.clearLabel}
                </button>
              </div>
            </div>

            {modelsError && (
              <div className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
                {modelsError}
              </div>
            )}

            {conversationError && (
              <div className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200">
                {conversationError}
              </div>
            )}

            {chatError && (
              <div className="mt-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-amber-200">
                {chatError}
              </div>
            )}
          </header>

          <div className="relative min-h-0 flex-1 overflow-hidden">
            <div
              ref={scrollContainerRef}
              onScroll={handleMessagesScroll}
              className="h-full overflow-y-auto px-4 py-6 md:px-8 md:py-8"
            >
              <div className="mx-auto flex w-full max-w-4xl flex-col gap-6 pb-24">
                {messages.map((m) => (
                  <ChatMessage
                    key={m.id}
                    msg={m}
                    onOpenSource={(documentId, chunkIndex, excerpt) =>
                      void openSourcePreview(documentId, chunkIndex, excerpt)
                    }
                  />
                ))}

                {isLoading && (
                  <p className="text-sm text-slate-500">
                    {siteConfig.chat.loadingLabel}
                  </p>
                )}
              </div>
            </div>

            {showScrollToBottom && (
              <button
                onClick={() => scrollToBottom()}
                className="absolute bottom-5 right-5 z-10 flex h-11 w-11 items-center justify-center rounded-full border border-slate-200 bg-white/95 text-slate-700 shadow-[0_12px_30px_rgba(15,23,42,0.14)] transition hover:bg-slate-50"
                aria-label="Scroll to bottom"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 20 20"
                  fill="none"
                  className="h-5 w-5"
                >
                  <path
                    d="M10 4.5v10m0 0-4-4m4 4 4-4"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            )}
          </div>

          <div
            className={`shrink-0 border-t border-slate-200/80 bg-white/90 px-4 transition-all duration-200 md:px-8 ${
              isComposerCompact ? "py-1.5" : "py-2.5"
            }`}
          >
            <div className="mx-auto w-full max-w-4xl">
              <div
                className={`border border-slate-200 bg-slate-50 shadow-[0_10px_35px_rgba(15,23,42,0.06)] transition-all duration-200 ${
                  isComposerCompact
                    ? "rounded-[1rem] p-1.5"
                    : "rounded-[1.25rem] p-2"
                }`}
              >
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      input.trim() &&
                      model &&
                      !isLoading
                    ) {
                      event.preventDefault();
                      void handleSendMessage();
                    }
                  }}
                  placeholder={siteConfig.chat.inputPlaceholder}
                  rows={isComposerCompact ? 1 : 2}
                  className={`w-full resize-none bg-transparent px-2 text-[15px] text-slate-900 outline-none placeholder:text-slate-400 transition-all duration-200 ${
                    isComposerCompact
                      ? "min-h-10 py-1 leading-5"
                      : "min-h-16 py-1.5 leading-6"
                  }`}
                />

                <div
                  className={`flex flex-col border-t border-slate-200 px-2 sm:flex-row sm:items-center sm:justify-between ${
                    isComposerCompact ? "gap-1 pt-1" : "gap-2 pt-2"
                  }`}
                >
                  {!isComposerCompact && (
                    <p className="text-[11px] text-slate-500 transition-all duration-200">
                      {siteConfig.chat.composerHint}
                    </p>
                  )}

                  <button
                    type="button"
                    onClick={() => {
                      void handleSendMessage();
                    }}
                    disabled={!input.trim() || !model || isLoading || isLoadingModels}
                    className={`bg-slate-950 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300 ${
                      isComposerCompact
                        ? "rounded-lg px-3 py-1.5"
                        : "rounded-xl px-4 py-2"
                    }`}
                  >
                    {siteConfig.chat.sendLabel}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
      <DocumentPreviewPanel
        preview={preview}
        isLoading={isPreviewLoading}
        error={previewError}
        highlightExcerpt={previewHighlightExcerpt}
        onClose={closeSourcePreview}
        onUseInChat={(documentId) => {
          setSelectedDocumentIds([documentId]);
          closeSourcePreview();
        }}
      />
    </AppShell>
  );
}

export default function ChatPage() {
  return (
    <Suspense
      fallback={
        <AppShell contentClassName="p-4 md:p-6 xl:p-8">
          <section className="rounded-[1.25rem] border border-slate-200/80 bg-white/92 px-5 py-6 text-sm text-slate-600 shadow-[0_16px_40px_rgba(15,23,42,0.06)]">
            Loading chat...
          </section>
        </AppShell>
      }
    >
      <ChatPageContent />
    </Suspense>
  );
}
