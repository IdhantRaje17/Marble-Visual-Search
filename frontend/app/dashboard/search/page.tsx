"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import api from "@/lib/api";
import TileResultCard from "@/components/TileResultCard";
import {
  Upload, Loader2, X, ZoomIn, RefreshCcw, Check, Search,
} from "lucide-react";
import {
  loadSearchSession, saveSearchSession, clearSearchSession,
  PerImageStatus,
} from "@/lib/searchSession";

// ─── Types ────────────────────────────────────────────────
type SearchResult = {
  tile_id: number;
  sku: string;
  name: string;
  is_active?: boolean | null;
  confidence: number;
  vote_count?: number;
  location: { aisle: string | null; rack: string | null; bin: string | null; warehouse?: string; display?: string };
  stock: { quantity: number | null; unit: string; is_low: boolean; status?: string };
  image_url: string;
  details?: { material?: { name: string }; finish?: { name: string }; style?: { name: string }; width_cm?: number; height_cm?: number; price_per_sqm?: number };
};

type UploadedImage = {
  id: string;
  file: File;
  preview: string; // data URL
  croppedPreview?: string; // data URL of cropped version
  croppedBlob?: Blob; // cropped file data
};

// ─── Constants ────────────────────────────────────────────
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_FILE_BYTES = 10 * 1024 * 1024;
const LOADING_STAGES = [
  "Checking your images...",
  "Validating image content...",
  "Searching the catalog...",
  "Comparing visual matches...",
  "Ranking results...",
];

// ─── Crop Modal Component ────────────────────────────────
function CropModal({
  image,
  onConfirm,
  onCancel,
}: {
  image: UploadedImage;
  onConfirm: (croppedDataUrl: string, croppedBlob: Blob) => void;
  onCancel: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const [scale, setScale] = useState(1);
  const [rotation, setRotation] = useState(0);
  // Crop region as fraction of image (0–1)
  const [cropX, setCropX] = useState(0.1);
  const [cropY, setCropY] = useState(0.1);
  const [cropW, setCropW] = useState(0.8);
  const [cropH, setCropH] = useState(0.8);

  const PREVIEW_W = 340;
  const PREVIEW_H = 340;

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = PREVIEW_W;
    canvas.height = PREVIEW_H;
    ctx.clearRect(0, 0, PREVIEW_W, PREVIEW_H);

    const imgW = img.naturalWidth;
    const imgH = img.naturalHeight;
    const sx = cropX * imgW;
    const sy = cropY * imgH;
    const sw = cropW * imgW;
    const sh = cropH * imgH;

    ctx.save();
    ctx.translate(PREVIEW_W / 2, PREVIEW_H / 2);
    ctx.rotate((rotation * Math.PI) / 180);
    ctx.scale(scale, scale);
    ctx.drawImage(img, sx, sy, sw, sh, -PREVIEW_W / 2, -PREVIEW_H / 2, PREVIEW_W, PREVIEW_H);
    ctx.restore();

    // Crop guide overlay
    ctx.strokeStyle = "rgba(6,182,212,0.85)";
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 3]);
    ctx.strokeRect(10, 10, PREVIEW_W - 20, PREVIEW_H - 20);
  }, [cropX, cropY, cropW, cropH, scale, rotation]);

  useEffect(() => {
    const img = imgRef.current;
    if (img?.complete) draw();
    else img?.addEventListener("load", draw);
    return () => img?.removeEventListener("load", draw);
  }, [draw]);

  const handleConfirm = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.toBlob((blob) => {
      if (!blob) return;
      const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
      onConfirm(dataUrl, blob);
    }, "image/jpeg", 0.92);
  };

  const reset = () => {
    setScale(1);
    setRotation(0);
    setCropX(0.1);
    setCropY(0.1);
    setCropW(0.8);
    setCropH(0.8);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-lg font-bold text-stone-800 mb-4">Crop Image</h2>

        {/* Hidden source image for canvas drawing */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img ref={imgRef} src={image.preview} alt="" className="hidden" onLoad={draw} />

        <div className="flex justify-center mb-4 rounded-xl overflow-hidden border border-stone-200">
          <canvas ref={canvasRef} width={PREVIEW_W} height={PREVIEW_H}
                  className="block" style={{ maxWidth: "100%" }} />
        </div>

        <div className="space-y-2 mb-4">
          <SliderRow label="Zoom" value={scale} min={0.5} max={3} step={0.05}
                     onChange={(v) => { setScale(v); draw(); }} />
          <SliderRow label="Rotation" value={rotation} min={-180} max={180} step={1}
                     onChange={(v) => { setRotation(v); draw(); }} />
          <SliderRow label="Crop X" value={cropX} min={0} max={0.5} step={0.01}
                     onChange={(v) => { setCropX(v); draw(); }} />
          <SliderRow label="Crop Y" value={cropY} min={0} max={0.5} step={0.01}
                     onChange={(v) => { setCropY(v); draw(); }} />
          <SliderRow label="Crop Width" value={cropW} min={0.2} max={1} step={0.01}
                     onChange={(v) => { setCropW(v); draw(); }} />
          <SliderRow label="Crop Height" value={cropH} min={0.2} max={1} step={0.01}
                     onChange={(v) => { setCropH(v); draw(); }} />
        </div>

        <div className="flex gap-3 justify-end">
          <button onClick={reset}
            className="flex items-center gap-1.5 border border-stone-300 px-4 py-2 rounded-lg text-sm text-stone-600 hover:bg-stone-50 transition">
            <RefreshCcw size={14} /> Reset
          </button>
          <button onClick={onCancel}
            className="border border-stone-300 px-4 py-2 rounded-lg text-sm text-stone-600 hover:bg-stone-50 transition">
            Cancel
          </button>
          <button onClick={handleConfirm}
            className="flex items-center gap-1.5 bg-cyan-600 text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-cyan-500 transition">
            <Check size={14} /> Use This Crop
          </button>
        </div>
      </div>
    </div>
  );
}

function SliderRow({ label, value, min, max, step, onChange }: {
  label: string; value: number; min: number; max: number; step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="flex items-center gap-3 text-xs text-stone-600">
      <span className="w-20 shrink-0">{label}</span>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={(event) => onChange(parseFloat(event.target.value))}
        className="flex-1 accent-cyan-500" />
      <span className="w-10 text-right text-stone-500">{value.toFixed(2)}</span>
    </label>
  );
}

// ─── Per-Image Status Badge ───────────────────────────────
function ImageStatusBadge({ status }: { status: PerImageStatus["status"] }) {
  if (status === "valid") return (
    <span className="inline-flex items-center gap-1 text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full">
      <Check size={10} /> Valid tile image
    </span>
  );
  if (status === "rejected_not_tile") return (
    <span className="inline-flex items-center gap-1 text-xs font-medium bg-red-50 text-red-600 border border-red-200 px-2 py-0.5 rounded-full">
      <X size={10} /> Not a valid tile image
    </span>
  );
  return null;
}

// ─── Main Search Page ─────────────────────────────────────
export default function SearchPage() {
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingStage, setLoadingStage] = useState(0);
  const [searched, setSearched] = useState(false);
  const [responseMs, setResponseMs] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [perImageStatus, setPerImageStatus] = useState<PerImageStatus[]>([]);
  const [allRejected, setAllRejected] = useState(false);
  const [validationUnavailable, setValidationUnavailable] = useState(false);
  const [cropTarget, setCropTarget] = useState<UploadedImage | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // ── Restore session ───────────────────────────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("fresh") === "1") {
      clearSearchSession();
      window.history.replaceState({}, "", "/dashboard/search");
      return;
    }
    const saved = loadSearchSession();
    if (!saved) return;
    setResults((saved.results || []) as SearchResult[]);
    setSearched(Boolean(saved.searched));
    setResponseMs(saved.responseMs);
    setPerImageStatus([]);

    // Restore previews as display-only UploadedImage stubs (no File ref)
    const previews = (saved.previews ?? (saved.preview ? [saved.preview] : [])).slice(0, 1);
    if (previews.length > 0) {
      const stubs: UploadedImage[] = previews.map((p, i) => ({
        id: `restored-${i}`,
        file: new File([], ""),
        preview: p ?? "",
        croppedPreview: p ?? undefined,
      }));
      setImages(stubs);
    }
  }, []);

  // ── Cycling loading stage animation ──────────────────
  useEffect(() => {
    if (!loading) { setLoadingStage(0); return; }
    const t = setInterval(() => {
      setLoadingStage((s) => (s + 1) % LOADING_STAGES.length);
    }, 1200);
    return () => clearInterval(t);
  }, [loading]);

  // ── File handling ─────────────────────────────────────
  const addFiles = useCallback((files: File[]) => {
    if (files.length !== 1) {
      setError("Choose exactly one image for each search.");
      return;
    }
    const [file] = files;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Choose a JPEG, PNG, or WebP image.");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setError("Image must be 10 MB or smaller.");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const preview = typeof reader.result === "string" ? reader.result : "";
      setImages([{ id: `${Date.now()}-${Math.random()}`, file, preview }]);
      setCropTarget(null);
    };
    reader.onerror = () => setError("The selected image could not be read.");
    reader.readAsDataURL(file);
    setResults([]);
    setSearched(false);
    setError("");
    setPerImageStatus([]);
    setAllRejected(false);
    setValidationUnavailable(false);
  }, []);

  const removeImage = (id: string) => {
    setImages((prev) => prev.filter((img) => img.id !== id));
    setResults([]);
    setSearched(false);
    setError("");
    setPerImageStatus([]);
    setAllRejected(false);
    setValidationUnavailable(false);
  };

  // ── Drag-and-drop ─────────────────────────────────────
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const onDragLeave = () => setIsDragging(false);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
  };

  // ── Crop handlers ─────────────────────────────────────
  const openCrop = (img: UploadedImage) => {
    // Don't allow crop on restored stubs with no File
    if (!img.file.name) return;
    setCropTarget(img);
  };

  const applyCrop = (croppedDataUrl: string, croppedBlob: Blob) => {
    if (!cropTarget) return;
    setImages((prev) =>
      prev.map((img) =>
        img.id === cropTarget.id
          ? { ...img, croppedPreview: croppedDataUrl, croppedBlob }
          : img
      )
    );
    setCropTarget(null);
  };

  // ── Search ────────────────────────────────────────────
  const handleSearch = async () => {
    const image = images[0];
    if (!image) return;
    if (!image.croppedBlob) {
      setError("Crop and confirm this image before searching.");
      return;
    }

    setLoading(true);
    setError("");
    setAllRejected(false);
    setValidationUnavailable(false);
    setPerImageStatus([]);

    try {
      const form = new FormData();
      form.append("file", new File([image.croppedBlob], "cropped.jpg", { type: "image/jpeg" }));
      const res = await api.post("/api/search/image?top_k=3", form);
      const data = res.data;
      const rawResults = data.results || [];
      const matches = await Promise.all(rawResults.map(async (result: SearchResult) => {
        try {
          const detail = await api.get(`/api/tiles/${result.tile_id}`);
          return {
            ...result,
            details: detail.data,
            is_active: detail.data.is_active ?? result.is_active,
            stock: detail.data.inventory
              ? {
                  quantity: detail.data.inventory.quantity,
                  unit: detail.data.inventory.unit,
                  is_low: detail.data.low_stock,
                  status: detail.data.stock_status ?? result.stock?.status,
                }
              : result.stock,
          };
        } catch {
          return result;
        }
      }));
      const validationConfirmed = data.validation?.status === "VALID_TILE";
      const status: PerImageStatus | null = validationConfirmed ? {
        image_index: 0,
        status: "valid",
        gatekeeper_score: data.validation.score,
        result_count: matches.length,
        preview: image.croppedPreview,
      } : null;
      setResults(matches);
      setResponseMs(data.response_time_ms ?? null);
      setSearched(true);
      setValidationUnavailable(!validationConfirmed);
      setPerImageStatus(status ? [status] : []);
      saveSearchSession({
        preview: image.croppedPreview ?? image.preview,
        previews: [image.croppedPreview ?? image.preview],
        results: matches,
        searched: true,
        responseMs: data.response_time_ms ?? null,
        perImageStatus: status ? [status] : [],
        validImageCount: validationConfirmed ? 1 : 0,
        rejectedImageCount: 0,
        isMultiImage: false,
      });
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: unknown } }; message?: string };
      const detail = axiosError.response?.data?.detail;
      const structured = typeof detail === "object" && detail ? detail as { message?: string; status?: string } : null;
      if (structured?.status === "VALIDATION_UNAVAILABLE") {
        setValidationUnavailable(true);
        setError("");
      } else {
        setError(structured?.status === "NOT_TILE" ? "" : "Please try again.");
      }
      if (structured?.status === "NOT_TILE") {
        setAllRejected(true);
        setPerImageStatus([{ image_index: 0, status: "rejected_not_tile", gatekeeper_score: 0, result_count: 0, preview: image.croppedPreview }]);
      }
      setResults([]);
      setSearched(true);
    } finally {
      setLoading(false);
    }
  };

  // ── Render ────────────────────────────────────────────
  const canSearch = Boolean(images[0]?.croppedBlob) && !loading;

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 via-white to-slate-100 p-6 sm:p-10">
      {cropTarget && (
        <CropModal
          image={cropTarget}
          onConfirm={applyCrop}
          onCancel={() => setCropTarget(null)}
        />
      )}

      <div className="max-w-6xl mx-auto rounded-3xl bg-white shadow-xl border border-slate-200 p-6 sm:p-8">
        <h1 className="text-3xl sm:text-4xl font-bold text-slate-900 mb-2">
          Visual Tile Search
        </h1>
        <p className="text-slate-600 text-base sm:text-lg mb-6">
          Upload one tile photo, crop it, and search matching products.
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* ── Upload Panel ─────────────────────────── */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 shadow-inner ring-1 ring-slate-100 space-y-4">

            <div
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onDrop={onDrop}
                onClick={() => fileRef.current?.click()}
                className={`border-2 border-dashed rounded-2xl p-6 text-center cursor-pointer transition-all duration-300 ${
                  isDragging
                    ? "border-cyan-400 bg-cyan-50"
                    : "border-slate-300 hover:border-cyan-400 hover:bg-cyan-50"
                }`}
              >
                <Upload size={32} className="mx-auto mb-2 text-stone-400" />
                <p className="font-medium text-stone-600 text-sm">
                  {images.length === 0 ? "Choose or drop one tile photo" : "Replace photo"}
                </p>
                <p className="text-xs text-stone-400 mt-1">
                  JPEG, PNG, or WebP · Up to 10 MB
                </p>
            </div>

            <input
              ref={fileRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) addFiles([file]);
                e.target.value = "";
              }}
            />

            {/* Image thumbnails */}
            {images.length > 0 && (
              <div className="space-y-2">
                {images.map((img, idx) => {
                  const displaySrc = img.croppedPreview ?? img.preview;
                  const imgStatus = perImageStatus.find((s) => s.image_index === idx);
                  const hasFile = img.file.size > 0 || img.croppedBlob;

                  return (
                    <div key={img.id}
                      className="flex items-center gap-3 bg-white rounded-xl border border-stone-200 p-2 shadow-sm">
                      {/* Thumbnail */}
                      <div className="w-14 h-14 rounded-lg overflow-hidden bg-stone-100 flex-shrink-0 border border-stone-200">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={displaySrc} alt={`Image ${idx + 1}`}
                          className="w-full h-full object-cover" />
                      </div>
                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-stone-700 truncate">
                          Image {idx + 1}
                          {img.croppedPreview ? " (cropped)" : ""}
                        </p>
                        {imgStatus ? (
                          <ImageStatusBadge status={imgStatus.status} />
                        ) : (
                          <span className="text-xs text-stone-400">
                            {img.file.name ? img.file.name.slice(0, 24) : "Restored"}
                          </span>
                        )}
                      </div>
                      {/* Actions */}
                      <div className="flex items-center gap-1">
                        {hasFile && (
                          <button
                            onClick={() => openCrop(img)}
                            className="p-1.5 rounded-lg hover:bg-cyan-50 text-stone-400 hover:text-cyan-600 transition"
                            title="Crop this image"
                            aria-label={`Crop image ${idx + 1}`}
                          >
                            <ZoomIn size={14} />
                          </button>
                        )}
                        <button
                          onClick={() => removeImage(img.id)}
                          className="p-1.5 rounded-lg hover:bg-red-50 text-stone-400 hover:text-red-500 transition"
                          title="Remove"
                          aria-label={`Remove image ${idx + 1}`}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    </div>
                  );
                })}

                {images[0] && <p className="text-xs text-stone-500">{images[0].croppedBlob ? "Crop confirmed" : "Crop and confirm before searching"}</p>}
              </div>
            )}

            {/* Search button */}
            {images.length > 0 && (
              <button
                id="search-button"
                onClick={handleSearch}
                disabled={!canSearch}
                className="w-full bg-gradient-to-r from-cyan-600 to-blue-600 text-white py-3 rounded-xl
                           font-semibold tracking-wide hover:from-cyan-500 hover:to-blue-500 active:scale-[0.98]
                           transition duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center
                           justify-center gap-2"
                aria-label="Find matching tiles"
              >
                {loading ? (
                  <><Loader2 size={18} className="animate-spin" />{LOADING_STAGES[loadingStage]}</>
                ) : (
                  <><Search size={18} /> Find This Tile</>
                )}
              </button>
            )}

            {responseMs && (
              <p className="text-center text-xs text-stone-400">
                ⚡ Result in {responseMs}ms
              </p>
            )}
          </div>

          {/* ── Results Panel ─────────────────────────── */}
          <div>
            {/* Per-image status (multi-image) */}
            {perImageStatus.length > 0 && (
              <div className="mb-4 rounded-xl border border-slate-200 bg-slate-50 p-3 space-y-2">
                <p className="text-xs font-semibold text-stone-600 uppercase tracking-wide">
                  Image validation
                </p>
                {perImageStatus.map((s, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm">
                    {s.preview && (
                      <div className="w-8 h-8 rounded overflow-hidden flex-shrink-0 border border-stone-200">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={s.preview} alt="" className="w-full h-full object-cover" />
                      </div>
                    )}
                    <span className="text-stone-600 text-xs">Uploaded image</span>
                    <ImageStatusBadge status={s.status} />
                  </div>
                ))}
              </div>
            )}

            {/* Empty state */}
            {!searched && !loading && (
              <div className="text-center text-stone-400 mt-16">
                <p className="text-5xl mb-3">🔍</p>
                <p>Upload a photo to see matches</p>
              </div>
            )}

            {/* Loading state */}
            {loading && (
              <div className="text-center text-stone-500 mt-16">
                <Loader2 size={40} className="animate-spin mx-auto mb-3 text-cyan-500" />
                <p className="font-medium text-stone-700">{LOADING_STAGES[loadingStage]}</p>
                <p className="text-sm text-stone-400 mt-1">This may take a few seconds</p>
              </div>
            )}

            {/* All rejected state */}
            {validationUnavailable && (
              <div role="alert" className="text-center mt-16 p-6 rounded-2xl border border-amber-200 bg-amber-50">
                <p className="text-sm text-amber-900">
                  {results.length > 0
                    ? "Here are the closest matching tiles from our catalog. Review the results and select the tile that best matches your image."
                    : "Please try again."}
                </p>
              </div>
            )}

            {searched && allRejected && !validationUnavailable && (
              <div className="text-center mt-16 p-6 rounded-2xl border border-red-100 bg-red-50">
                <p className="text-4xl mb-3">🚫</p>
                <p className="font-semibold text-red-700 text-lg mb-2">
                  Not a valid tile image
                </p>
                <p className="text-sm text-red-600 mb-4">
                  Crop to show the tile or stone surface, then try again.
                </p>
                <ul className="text-sm text-stone-600 text-left list-disc list-inside space-y-1">
                  <li>Try a closer or better-lit photo</li>
                  <li>Ensure the tile surface is visible</li>
                  <li>Try a different angle</li>
                </ul>
              </div>
            )}

            {/* No-match state */}
            {searched && !allRejected && !error && results.length === 0 && !loading && (
              <div className="text-center mt-16 p-6 rounded-2xl border border-stone-200 bg-stone-50">
                <p className="text-5xl mb-3">❌</p>
                <p className="font-semibold text-stone-700 text-lg mb-2">
                  No reliable match found
                </p>
                <p className="text-sm text-stone-500 mb-4">
                  The catalog does not contain a visually similar tile with sufficient confidence.
                </p>
                <ul className="text-sm text-stone-500 text-left list-disc list-inside space-y-1">
                  <li>Try a closer crop of the tile surface</li>
                  <li>Improve lighting or shoot straight-on</li>
                  <li>Upload additional angles</li>
                </ul>
              </div>
            )}

            {/* Results */}
            {results.length > 0 && !loading && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-cyan-800 font-semibold tracking-wide">
                    {results.length} match{results.length !== 1 ? "es" : ""} found
                  </p>
                </div>
                <div className="rounded-xl bg-gradient-to-r from-cyan-50 to-blue-50 p-4 border border-cyan-100 text-sm font-medium text-cyan-700 shadow-inner">
                  {validationUnavailable
                    ? "Candidates are ranked by visual similarity. These matches are unverified."
                    : "Candidates are ranked by visual similarity to the validated tile image."}
                  Results labelled as{" "}
                  <span className="font-bold">Strong Visual Match</span>,{" "}
                  <span className="font-bold">Visual Match</span>, or{" "}
                  <span className="font-bold">Possible Match</span> based on similarity score.
                </div>
                {results.map((r, i) => (
                  <TileResultCard
                    key={r.tile_id}
                    result={r}
                    rank={i}
                    totalImages={1}
                  />
                ))}
              </div>
            )}

            {/* Error state */}
            {error && !allRejected && !validationUnavailable && (
              <p className="mt-4 rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                {error}
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}