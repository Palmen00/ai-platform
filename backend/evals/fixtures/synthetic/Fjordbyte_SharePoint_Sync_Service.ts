import { refreshAccessToken } from "./auth/token-refresh";
import { fetchSharePointDriveItems, uploadIndexedChunk } from "./sharepoint/client";

type SyncResult = {
  filesSynced: number;
  chunksIndexed: number;
};

export async function syncSharePointKnowledgeLibrary(siteId: string): Promise<SyncResult> {
  const token = await refreshAccessToken("sharepoint-knowledge");
  const driveItems = await fetchSharePointDriveItems({ siteId, accessToken: token });

  let filesSynced = 0;
  let chunksIndexed = 0;

  for (const item of driveItems) {
    if (!item.name.endsWith(".docx") && !item.name.endsWith(".pdf") && !item.name.endsWith(".ts")) {
      continue;
    }

    filesSynced += 1;

    for (const chunk of item.chunks) {
      await uploadIndexedChunk({
        accessToken: token,
        source: "sharepoint",
        siteId,
        driveItemId: item.id,
        chunkContent: chunk.content,
      });
      chunksIndexed += 1;
    }
  }

  return { filesSynced, chunksIndexed };
}

export function describeSyncPurpose(): string {
  return "This service syncs SharePoint files into the local knowledge index and refreshes OAuth tokens when needed.";
}
