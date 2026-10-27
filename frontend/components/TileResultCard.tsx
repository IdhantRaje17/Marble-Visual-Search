"use client";

interface TileResult {
  tile_id: number;
  sku: string;
  name: string;
  is_active?: boolean | null;
  confidence: number;
  vote_count?: number; // how many uploaded images matched this tile
  location: {
    warehouse?: string;
    aisle: string | null;
    rack: string | null;
    bin: string | null;
    display?: string;
  };
  stock: { quantity: number | null; unit: string; is_low: boolean; status?: string };
  image_url: string;
  details?: {
    material?: { name: string };
    finish?: { name: string };
    style?: { name: string };
    color_family?: { name: string };
    application?: { name: string };
    texture?: string | null;
    width_cm?: number | null;
    height_cm?: number | null;
    thickness_cm?: number | null;
    price_per_sqm?: number;
  };
}

/** Convert cosine similarity score to an honest match quality label. */
function getMatchLabel(confidence: number): {
  label: string;
  colorClass: string;
} {
  if (confidence >= 85) {
    return { label: "Strong Visual Match", colorClass: "text-emerald-700 bg-emerald-50 border-emerald-200" };
  }
  if (confidence >= 70) {
    return { label: "Visual Match", colorClass: "text-amber-700 bg-amber-50 border-amber-200" };
  }
  return { label: "Possible Match", colorClass: "text-orange-700 bg-orange-50 border-orange-200" };
}

export default function TileResultCard({
  result,
  rank,
  totalImages,
}: {
  result: TileResult;
  rank: number;
  totalImages?: number;
}) {
  const { label, colorClass } = getMatchLabel(result.confidence);
  const imageUrl = result.image_url
    ? `http://localhost:8000${result.image_url}`
    : null;

  // Show multi-image evidence indicator when relevant
  const showVoteInfo =
    totalImages && totalImages > 1 && result.vote_count !== undefined;

  return (
    <div
      className={`bg-white/95 backdrop-blur-sm rounded-2xl border p-5 shadow-md transition-all duration-300 transform hover:-translate-y-1 hover:shadow-2xl ${
        rank === 0
          ? "border-emerald-500 ring-2 ring-emerald-400/50"
          : "border-stone-200"
      }`}
    >
      {/* Header Row */}
      <div className="flex gap-4 items-start">

        {/* Tile Image */}
        <div className="w-24 h-24 rounded-lg overflow-hidden
                        bg-stone-100 flex-shrink-0 border border-stone-200 shadow-inner transition-all duration-300 hover:scale-105 hover:shadow-xl">
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={result.name}
              className="w-full h-full object-cover transition-all duration-300 ease-out hover:scale-110"
              onError={(e) => {
                (e.target as HTMLImageElement).src =
                  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'" +
                  " width='96' height='96'%3E%3Crect width='96' height='96'" +
                  " fill='%23e7e5e4'/%3E%3Ctext x='50%25' y='50%25'" +
                  " dominant-baseline='middle' text-anchor='middle'" +
                  " font-size='24'%3E%F0%9F%AA%A8%3C/text%3E%3C/svg%3E";
              }}
            />
          ) : (
            <div className="w-full h-full flex items-center
                            justify-center text-3xl text-stone-400">
              🪨
            </div>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between mb-1">
            <div>
              {rank === 0 && (
                <span className="text-xs font-bold bg-gradient-to-r from-emerald-500 to-cyan-500 text-white
                                 px-2 py-0.5 rounded-full mb-1 inline-block shadow">
                  Best Match
                </span>
              )}
              <p className="font-bold text-stone-800 leading-tight tracking-tight text-lg">
                {result.name}
              </p>
              <p className="text-stone-400 text-xs">{result.sku}</p>
              {result.is_active === false && (
                <span className="mt-1 inline-block border border-stone-300 bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
                  Inactive catalog item
                </span>
              )}
            </div>
            {/* Honest match quality label — NOT raw similarity as probability */}
            <span
              className={`text-xs font-semibold px-2.5 py-1 rounded-full border flex-shrink-0 ml-2 ${colorClass}`}
              title="Visual similarity score, not a probability"
            >
              {label} · {result.confidence.toFixed(1)}% similarity
            </span>
          </div>

          {/* Multi-image evidence badge */}
          {showVoteInfo && (
            <p className="text-xs text-stone-500 mt-1">
              {result.vote_count === totalImages
                ? `Matched across all ${totalImages} images`
                : `Matched in ${result.vote_count} of ${totalImages} images`}
            </p>
          )}

          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-3 text-xs text-stone-500">
            <span>Material: {result.details?.material?.name || "Not specified"}</span>
            <span>Color: {result.details?.color_family?.name || "Not specified"}</span>
            <span>Finish: {result.details?.finish?.name || "Not specified"}</span>
            <span>Texture: {result.details?.texture?.trim() || "Not specified"}</span>
            <span>Style: {result.details?.style?.name || "Not specified"}</span>
            <span>Application: {result.details?.application?.name || "Not specified"}</span>
            <span>Dimensions: {result.details?.width_cm ?? "Not specified"} x {result.details?.height_cm ?? "Not specified"} x {result.details?.thickness_cm ?? "Not specified"} cm</span>
            {result.details?.price_per_sqm != null && <span>₹{result.details.price_per_sqm}/sqm</span>}
          </div>

          {/* Location */}
          <div className="bg-stone-50 rounded-lg px-3 py-2 mt-2 text-sm">
            <p className="text-stone-500 text-xs mb-0.5">
              📍 Warehouse Location
            </p>
            {result.location?.aisle ? (
              <p className="font-medium text-stone-700 text-xs">
                {result.location.display ||
                  `${result.location.warehouse || "Warehouse"} | Aisle ${result.location.aisle} -> Rack ${result.location.rack} -> Bin ${result.location.bin}`}
              </p>
            ) : (
              <p className="text-stone-500 italic text-xs">
                {result.location?.display || `${result.location?.warehouse || "Warehouse"} | Location pending assignment`}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Stock Row */}
      <div className="flex items-center justify-between text-sm mt-3
                      pt-3 border-t border-stone-100">
        <span className="text-stone-500">📦 Inventory</span>
        <span
          className={`font-semibold ${
            result.stock.is_low ? "text-red-500" : "text-green-600"
          }`}
        >
          {result.stock.status === "INVENTORY_NOT_CONFIGURED"
            ? "Inventory not configured"
            : result.stock.quantity == null
              ? "Information unavailable"
              : `${result.stock.quantity} ${result.stock.unit}${result.stock.status ? ` · ${result.stock.status.replaceAll("_", " ").toLowerCase()}` : ""}`}
        </span>
      </div>

      <div className="flex items-center justify-end mt-4">
        <a
          href={`/dashboard/tiles/${result.tile_id}?from=search`}
          className="text-sm font-semibold text-cyan-700 hover:text-cyan-900 transition"
        >
          View Details →
        </a>
      </div>
    </div>
  );
}
