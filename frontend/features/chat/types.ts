import { ChatSource, RetrievalDebug } from "../../lib/api";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string;
  sources?: ChatSource[];
  retrieval?: RetrievalDebug | null;
};
