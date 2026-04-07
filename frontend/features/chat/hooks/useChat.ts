"use client";

import { useEffect, useRef, useState } from "react";
import { siteConfig } from "../../../config/site";
import {
  ChatHistoryItem,
  getConversation,
  sendChatMessage,
} from "../../../lib/api";
import { createClientId } from "../../../lib/client-id";
import { ChatMessage } from "../types";

const CONVERSATIONS_UPDATED_EVENT = "conversations:updated";

function createAssistantMessage(content: string): ChatMessage {
  return {
    id: createClientId(),
    role: "assistant",
    content,
  };
}

function mapHistoryToMessages(history: ChatHistoryItem[]): ChatMessage[] {
  if (history.length === 0) {
    return [createAssistantMessage(siteConfig.chat.initialAssistantMessage)];
  }

  return history.map((item) => ({
    id: createClientId(),
    role: item.role,
    content: item.content,
    model: item.model,
    sources: item.sources ?? [],
    retrieval: item.retrieval ?? null,
  }));
}

export function useChat(
  selectedModel: string,
  requestedConversationId: string,
  selectedDocumentIds: string[]
) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeConversationId, setActiveConversationId] = useState("");
  const [conversationDocumentIds, setConversationDocumentIds] = useState<string[]>(
    []
  );
  const [isLoading, setIsLoading] = useState(false);
  const [conversationError, setConversationError] = useState("");
  const [chatError, setChatError] = useState("");
  const loadRequestIdRef = useRef(0);

  useEffect(() => {
    const requestId = loadRequestIdRef.current + 1;
    loadRequestIdRef.current = requestId;

    async function loadConversation() {
      setConversationError("");

      if (!requestedConversationId) {
        setActiveConversationId("");
        setConversationDocumentIds([]);
        setMessages([
          createAssistantMessage(siteConfig.chat.initialAssistantMessage),
        ]);
        return;
      }

      try {
        let conversation = await getConversation(requestedConversationId);
        if (loadRequestIdRef.current !== requestId) {
          return;
        }

        if (!conversation.messages.length) {
          await new Promise((resolve) => window.setTimeout(resolve, 400));
          conversation = await getConversation(requestedConversationId);
          if (loadRequestIdRef.current !== requestId) {
            return;
          }
        }

        setActiveConversationId(conversation.id);
        setConversationDocumentIds(conversation.document_ids ?? []);
        setMessages(mapHistoryToMessages(conversation.messages));
        setChatError("");
      } catch {
        if (loadRequestIdRef.current !== requestId) {
          return;
        }
        setConversationError(siteConfig.chat.errors.conversationLoadError);
        setMessages((current) =>
          current.length > 0
            ? current
            : [createAssistantMessage(siteConfig.chat.initialAssistantMessage)]
        );
      }
    }

    void loadConversation();
  }, [requestedConversationId]);

  async function sendMessage(text: string) {
    if (!text.trim() || isLoading) return;

    setChatError("");
    const userMessage: ChatMessage = {
      id: createClientId(),
      role: "user",
      content: text,
    };

    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setIsLoading(true);

    try {
      const history: ChatHistoryItem[] = messages.map((message) => ({
        role: message.role,
        content: message.content,
        model: message.model,
        sources: message.sources ?? [],
        retrieval: message.retrieval ?? null,
      }));

      const response = await sendChatMessage(
        text,
        selectedModel,
        history,
        activeConversationId || undefined,
        selectedDocumentIds
      );

      const assistantMessage: ChatMessage = {
        id: createClientId(),
        role: "assistant",
        content: response.reply,
        model: response.model,
        sources: response.sources ?? [],
        retrieval: response.retrieval ?? null,
      };

      setMessages([...nextMessages, assistantMessage]);

      if (response.conversation_id) {
        setActiveConversationId(response.conversation_id);
      }

      window.dispatchEvent(new Event(CONVERSATIONS_UPDATED_EVENT));
      return response.conversation_id;
    } catch (error) {
      const nextError =
        error instanceof Error && error.message
          ? error.message
          : siteConfig.chat.errors.backendUnavailable;
      setChatError(nextError);
      setMessages((prev) => [
        ...prev,
        {
          id: createClientId(),
          role: "assistant",
          content: nextError,
        },
      ]);
      return undefined;
    } finally {
      setIsLoading(false);
    }
  }

  function clearChat() {
    setConversationError("");
    setActiveConversationId("");
    setConversationDocumentIds([]);
    setMessages([
      createAssistantMessage(siteConfig.chat.clearedAssistantMessage),
    ]);
  }

  return {
    messages,
    activeConversationId,
    conversationDocumentIds,
    isLoading,
    conversationError,
    chatError,
    sendMessage,
    clearChat,
  };
}
