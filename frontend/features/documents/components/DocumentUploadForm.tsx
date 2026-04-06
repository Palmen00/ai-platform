"use client";

import { useState } from "react";
import { siteConfig } from "../../../config/site";

type DocumentUploadFormProps = {
  isUploading: boolean;
  onUpload: (files: File[]) => Promise<boolean>;
};

export function DocumentUploadForm({
  isUploading,
  onUpload,
}: DocumentUploadFormProps) {
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const wasUploaded = await onUpload(selectedFiles);

    if (wasUploaded) {
      setSelectedFiles([]);
      form.reset();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-[2rem] border border-slate-200/80 bg-white/88 p-6 shadow-[0_28px_70px_rgba(15,23,42,0.10)] backdrop-blur md:p-8"
    >
      <div className="mb-4">
        <h3 className="text-xl font-semibold tracking-tight text-slate-950">
          {siteConfig.knowledge.uploadTitle}
        </h3>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
          {siteConfig.knowledge.uploadSubtitle}
        </p>
      </div>

      <div className="flex flex-col gap-4 md:flex-row md:items-center">
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.xlsx,.pptx,.txt,.text,.md,.markdown,.mdx,.json,.jsonl,.ndjson,.csv,.tsv,.log,.rst,.py,.js,.jsx,.ts,.tsx,.java,.cs,.go,.rs,.php,.rb,.c,.cc,.cpp,.cxx,.h,.hpp,.swift,.kt,.kts,.scala,.sh,.bash,.zsh,.ps1,.psm1,.psd1,.sql,.html,.htm,.css,.scss,.less,.vue,.svelte,.yml,.yaml,.toml,.ini,.cfg,.conf,.env,.properties,.xml,.jpg,.jpeg,.png,.bmp,.tif,.tiff,.webp"
          onChange={(event) =>
            setSelectedFiles(Array.from(event.target.files ?? []))
          }
          className="block w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700"
        />

        <button
          type="submit"
          disabled={isUploading}
          className="rounded-2xl bg-slate-950 px-5 py-3 text-sm font-medium text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isUploading
            ? siteConfig.knowledge.uploadingButton
            : siteConfig.knowledge.uploadButton}
          </button>
      </div>

      {selectedFiles.length > 0 && (
        <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
          <div className="font-medium text-slate-800">
            {siteConfig.knowledge.selectedFilesLabel}: {selectedFiles.length}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            {selectedFiles.slice(0, 6).map((file) => (
              <span
                key={`${file.name}-${file.size}`}
                className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-600 ring-1 ring-slate-200"
              >
                {file.name}
              </span>
            ))}
            {selectedFiles.length > 6 && (
              <span className="rounded-full bg-white px-2.5 py-1 text-xs text-slate-500 ring-1 ring-slate-200">
                +{selectedFiles.length - 6} more
              </span>
            )}
          </div>
        </div>
      )}
    </form>
  );
}
