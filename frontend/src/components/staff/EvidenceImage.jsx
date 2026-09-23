import React, { useEffect, useState } from "react";

// Private screenshot: fetched with the auth header, shown from a blob URL.
export const EvidenceImage = ({ fileId, load, className = "", onOpen, testId }) => {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    let objectUrl = null;
    load(fileId).then((blob) => {
      if (!alive) return;
      objectUrl = URL.createObjectURL(blob);
      setUrl(objectUrl);
    }).catch(() => alive && setFailed(true));
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [fileId, load]);
  if (failed) return <div className={`flex items-center justify-center bg-white/[0.04] text-[11px] text-[#8e91a3] ${className}`}>нет доступа</div>;
  if (!url) return <div className={`animate-pulse bg-white/[0.06] ${className}`} />;
  return (
    <button type="button" onClick={() => onOpen?.(url)} className={`overflow-hidden rounded-lg bg-black/40 ${className}`} data-testid={testId}>
      <img src={url} alt="скриншот" className="w-full h-full object-cover" />
    </button>
  );
};

export const EvidenceGallery = ({ ids = [], load, testId = "evidence-gallery" }) => {
  const [open, setOpen] = useState(null);
  return (
    <div data-testid={testId}>
      <div className="grid grid-cols-3 gap-2">
        {ids.map((id, i) => <EvidenceImage key={id} fileId={id} load={load} onOpen={setOpen} className="aspect-video w-full" testId={`${testId}-item-${i}`} />)}
      </div>
      {open && (
        <div className="fixed inset-0 z-[100] bg-black/85 flex items-center justify-center p-4" onClick={() => setOpen(null)} data-testid={`${testId}-lightbox`}>
          <img src={open} alt="скриншот" className="max-w-full max-h-full rounded-lg" />
        </div>
      )}
    </div>
  );
};
