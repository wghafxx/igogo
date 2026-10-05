import React, { useRef, useState } from "react";
import { toast } from "sonner";
import { ImagePlus, X } from "lucide-react";
import { staffApi, errText } from "../../lib/staff-api";
import { EvidenceImage } from "./EvidenceImage";

const MAX = 6;
const MAX_BYTES = 5 * 1024 * 1024;

export default function EvidenceUploader({ value, onChange, upload, testId = "evidence-uploader" }) {
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const pick = async (files) => {
    const list = Array.from(files || []).slice(0, MAX - value.length);
    if (!list.length) return;
    setBusy(true);
    const added = [];
    for (const file of list) {
      if (!["image/png", "image/jpeg"].includes(file.type)) { toast.error(`${file.name}: нужен PNG или JPEG`); continue; }
      if (file.size > MAX_BYTES) { toast.error(`${file.name}: больше 5 МБ`); continue; }
      try { added.push((await upload(file)).id); }
      catch (e) { toast.error(errText(e, "Не удалось загрузить скриншот")); }
    }
    onChange([...value, ...added]);
    setBusy(false);
    if (input.current) input.current.value = "";
  };
  return (
    <div className="space-y-2" data-testid={testId}>
      <div className="grid grid-cols-3 gap-2">
        {value.map((id, i) => (
          <div key={id} className="relative">
            <EvidenceImage fileId={id} load={staffApi.evidence} className="aspect-video w-full" />
            <button type="button" onClick={() => onChange(value.filter((x) => x !== id))} className="absolute top-1 right-1 w-6 h-6 rounded-full bg-black/70 text-white flex items-center justify-center" data-testid={`${testId}-remove-${i}`}><X size={13} /></button>
          </div>
        ))}
        {value.length < MAX && (
          <button type="button" disabled={busy} onClick={() => input.current?.click()} className="aspect-video rounded-lg border border-dashed border-white/15 text-[#8e91a3] hover:text-white hover:border-white/30 flex flex-col items-center justify-center gap-1 text-[11px] transition-colors disabled:opacity-50" data-testid={`${testId}-add`}>
            <ImagePlus size={18} />{busy ? "Загрузка…" : "Добавить"}
          </button>
        )}
      </div>
      <input ref={input} type="file" accept="image/png,image/jpeg" multiple hidden onChange={(e) => pick(e.target.files)} data-testid={`${testId}-input`} />
      <div className="text-[11px] text-[#6b6f84]">{value.length} из {MAX} · PNG/JPEG до 5 МБ каждый</div>
    </div>
  );
}
