// Screenshots are re-encoded in the browser: max 1600 px side, WebP, stepping quality down until ≤ 1 MB.
export const MAX_SCREENSHOT_BYTES = 1024 * 1024;
const MAX_SIDE = 1600;

const loadImage = (file) => new Promise((resolve, reject) => {
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
  img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("bad image")); };
  img.src = url;
});

const toBlob = (canvas, type, quality) => new Promise((resolve) => canvas.toBlob(resolve, type, quality));

export async function compressScreenshot(file) {
  if (!file?.type?.startsWith("image/")) throw new Error("not an image");
  const img = await loadImage(file);
  let scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    for (const quality of [0.82, 0.7, 0.55]) {
      const blob = await toBlob(canvas, "image/webp", quality) || await toBlob(canvas, "image/jpeg", quality);
      if (blob && blob.size <= MAX_SCREENSHOT_BYTES) return blob;
    }
    scale *= 0.75;
  }
  throw new Error("too large");
}
