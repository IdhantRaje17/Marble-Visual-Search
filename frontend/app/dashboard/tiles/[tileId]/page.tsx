"use client";

import { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import axios from "axios";
import { ArrowLeft, Loader2, Package, ShoppingCart, Check, Minus, Plus, Pencil, Save, X } from "lucide-react";
import api, { API_BASE_URL } from "@/lib/api";
import { getRole } from "@/lib/auth";

type Category = { id: number; name: string; is_active?: boolean; hex_code?: string | null };
type Tile = {
  id: number;
  sku: string;
  name: string;
  description?: string | null;
  texture?: string | null;
  width_cm?: number | null;
  height_cm?: number | null;
  thickness_cm?: number | null;
  price_per_sqm?: number | null;
  material?: Category;
  style?: Category;
  finish?: Category;
  size_format?: Category;
  application?: Category;
  color_family?: Category;
  origin?: Category;
  inventory?: { quantity: number; unit: string; low_stock_threshold: number } | null;
  stock_quantity?: number | null;
  stock_status?: string;
  low_stock?: boolean;
  images?: { id: number; image_url: string; is_primary: boolean }[];
};

type TileCategories = {
  materials: Category[];
  styles: Category[];
  finishes: Category[];
  applications: Category[];
  colors: Category[];
  origins: Category[];
};

type TileEditForm = {
  description: string;
  texture: string;
  material_id: string;
  style_id: string;
  finish_id: string;
  application_id: string;
  color_family_id: string;
  origin_id: string;
  width_cm: string;
  height_cm: string;
  thickness_cm: string;
  price_per_sqm: string;
};

type CategoryField =
  | "material_id"
  | "style_id"
  | "finish_id"
  | "application_id"
  | "color_family_id"
  | "origin_id";

const createEditForm = (tile: Tile): TileEditForm => ({
  description: tile.description ?? "",
  texture: tile.texture ?? "",
  material_id: tile.material?.id?.toString() ?? "",
  style_id: tile.style?.id?.toString() ?? "",
  finish_id: tile.finish?.id?.toString() ?? "",
  application_id: tile.application?.id?.toString() ?? "",
  color_family_id: tile.color_family?.id?.toString() ?? "",
  origin_id: tile.origin?.id?.toString() ?? "",
  width_cm: tile.width_cm?.toString() ?? "",
  height_cm: tile.height_cm?.toString() ?? "",
  thickness_cm: tile.thickness_cm?.toString() ?? "",
  price_per_sqm: tile.price_per_sqm?.toString() ?? "",
});

const editOptions = (options: Category[], current?: Category) =>
  current && !options.some((option) => option.id === current.id)
    ? [current, ...options]
    : options;

const statusStyles: Record<string, string> = {
  IN_STOCK: "bg-emerald-100 text-emerald-800",
  LOW_STOCK: "bg-amber-100 text-amber-800",
  OUT_OF_STOCK: "bg-red-100 text-red-800",
  INVENTORY_NOT_CONFIGURED: "bg-stone-100 text-stone-700",
};

function TileDetailsNav({ error }: { error?: boolean }) {
  const searchParams = useSearchParams();
  const fromSearch = searchParams.get("from") === "search";

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      {fromSearch ? (
        <Link
          href="/dashboard/search"
          className="inline-flex items-center gap-2 text-sm text-stone-600 hover:text-stone-900"
        >
          <ArrowLeft size={16} /> Back to Search Results
        </Link>
      ) : (
        <Link
          href="/dashboard/tiles"
          className="inline-flex items-center gap-2 text-sm text-stone-600 hover:text-stone-900"
        >
          <ArrowLeft size={16} /> Back to catalog
        </Link>
      )}
      {!error && (
        <Link
          href="/dashboard/search?fresh=1"
          className="inline-flex items-center justify-center rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 w-full sm:w-auto"
        >
          Search New Tile
        </Link>
      )}
    </div>
  );
}

function AddToCartControls({ tile }: { tile: Tile }) {
  const stockQty = tile.inventory?.quantity ?? tile.stock_quantity ?? null;
  const outOfStock = stockQty === 0;
  const [quantity, setQuantity] = useState(1);
  const [addState, setAddState] = useState<"idle" | "loading" | "added" | "error">("idle");

  const handleAddToCart = async () => {
    setAddState("loading");
    try {
      await api.post("/api/cart/add", { tile_id: tile.id, quantity });
      setAddState("added");
      setTimeout(() => setAddState("idle"), 1500);
    } catch {
      setAddState("error");
      setTimeout(() => setAddState("idle"), 2000);
    }
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setQuantity((q) => Math.max(1, q - 1))}
          className="w-8 h-8 rounded-lg border border-stone-200 flex items-center justify-center text-stone-600 hover:bg-stone-100"
          aria-label="Decrease quantity"
        >
          <Minus size={14} />
        </button>
        <span className="text-sm font-semibold text-stone-700 w-8 text-center">{quantity}</span>
        <button
          type="button"
          onClick={() => setQuantity((q) => q + 1)}
          className="w-8 h-8 rounded-lg border border-stone-200 flex items-center justify-center text-stone-600 hover:bg-stone-100"
          aria-label="Increase quantity"
        >
          <Plus size={14} />
        </button>
      </div>
      <button
        onClick={handleAddToCart}
        disabled={addState === "loading" || outOfStock}
        className={`inline-flex items-center justify-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-xl border transition-all duration-200 w-full sm:w-auto disabled:cursor-not-allowed ${
          addState === "added"
            ? "bg-emerald-50 border-emerald-300 text-emerald-700"
            : addState === "error"
            ? "bg-red-50 border-red-300 text-red-600"
            : outOfStock
            ? "bg-stone-50 border-stone-200 text-stone-400"
            : "bg-stone-800 border-stone-800 text-white hover:bg-stone-700"
        }`}
      >
        {addState === "loading" && <Loader2 size={14} className="animate-spin" />}
        {addState === "added" && <Check size={14} />}
        {addState === "idle" && <ShoppingCart size={14} />}
        {addState === "loading"
          ? "Adding…"
          : addState === "added"
          ? "Added!"
          : addState === "error"
          ? "Failed — retry"
          : outOfStock
          ? "Out of stock"
          : "Add to Cart"}
      </button>
    </div>
  );
}

function TileDetailsContent({ params }: { params: Promise<{ tileId: string }> }) {
  const [tile, setTile] = useState<Tile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [canEdit, setCanEdit] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [loadingEditOptions, setLoadingEditOptions] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [categories, setCategories] = useState<TileCategories | null>(null);
  const [editForm, setEditForm] = useState<TileEditForm | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    params.then(({ tileId }) => api.get(`/api/tiles/${tileId}`)
      .then((response) => setTile(response.data))
      .catch(() => setError("Product details could not be loaded."))
      .finally(() => setLoading(false)));
  }, [params]);

  useEffect(() => {
    const role = getRole();
    setCanEdit(role === "admin" || role === "super_admin");
  }, []);

  const startEditing = async () => {
    if (!canEdit || !tile) return;
    setLoadingEditOptions(true);
    setFeedback(null);
    try {
      const response = await api.get<TileCategories>("/api/categories/all");
      setCategories(response.data);
      setEditForm(createEditForm(tile));
      setIsEditing(true);
    } catch {
      setFeedback({ type: "error", message: "Edit options could not be loaded. Please try again." });
    } finally {
      setLoadingEditOptions(false);
    }
  };

  const updateEditField = (field: keyof TileEditForm, value: string) => {
    setEditForm((current) => current ? { ...current, [field]: value } : current);
  };

  const handleSaveEdit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canEdit || !tile || !editForm) return;
    setFeedback(null);

    const width = editForm.width_cm.trim() === "" ? null : Number(editForm.width_cm);
    const height = editForm.height_cm.trim() === "" ? null : Number(editForm.height_cm);
    const thickness = editForm.thickness_cm.trim() === "" ? null : Number(editForm.thickness_cm);
    const price = editForm.price_per_sqm.trim() === "" ? null : Number(editForm.price_per_sqm);
    const dimensions = [width, height, thickness];

    if (!editForm.material_id) {
      setFeedback({ type: "error", message: "Material is required." });
      return;
    }
    if (dimensions.some((value) => value !== null && (!Number.isFinite(value) || value <= 0))) {
      setFeedback({ type: "error", message: "Dimensions must be positive numbers or left empty." });
      return;
    }
    if (price !== null && (!Number.isFinite(price) || price < 0)) {
      setFeedback({ type: "error", message: "Price must be zero or greater, or left empty." });
      return;
    }

    const optionalId = (value: string) => value ? Number(value) : null;
    setSavingEdit(true);
    try {
      const response = await api.put<Tile>(`/api/tiles/${tile.id}`, {
        description: editForm.description.trim() || null,
        texture: editForm.texture.trim() || null,
        material_id: Number(editForm.material_id),
        style_id: optionalId(editForm.style_id),
        finish_id: optionalId(editForm.finish_id),
        application_id: optionalId(editForm.application_id),
        color_family_id: optionalId(editForm.color_family_id),
        origin_id: optionalId(editForm.origin_id),
        width_cm: width,
        height_cm: height,
        thickness_cm: thickness,
        price_per_sqm: price,
      });
      setTile(response.data);
      setEditForm(null);
      setIsEditing(false);
      setFeedback({ type: "success", message: "Tile details saved." });
    } catch (saveError) {
      const detail = axios.isAxiosError<{ detail?: unknown }>(saveError)
        ? saveError.response?.data?.detail
        : null;
      const validationMessages = Array.isArray(detail)
        ? detail.flatMap((entry: unknown) =>
            typeof entry === "object"
              && entry !== null
              && "msg" in entry
              && typeof entry.msg === "string"
              ? [entry.msg]
              : []
          )
        : [];
      setFeedback({
        type: "error",
        message: typeof detail === "string"
          ? detail
          : validationMessages.join(" ") || "Tile details could not be saved. Please try again.",
      });
    } finally {
      setSavingEdit(false);
    }
  };

  const renderCategoryField = (
    label: string,
    field: CategoryField,
    options: Category[],
    current?: Category,
    required = false,
  ) => editForm && (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium text-stone-700">{label}{required ? " *" : ""}</span>
      <select
        value={editForm[field]}
        onChange={(event) => updateEditField(field, event.target.value)}
        required={required}
        className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-stone-800"
      >
        <option value="">{required ? "Select material" : "Not specified"}</option>
        {editOptions(options, current).map((option) => (
          <option key={option.id} value={option.id}>{option.name}</option>
        ))}
      </select>
    </label>
  );

  if (loading) return <div className="flex min-h-[50vh] items-center justify-center text-stone-500"><Loader2 className="animate-spin mr-2" /> Loading product...</div>;
  if (error || !tile) return <div className="space-y-4"><TileDetailsNav error /><p className="rounded-lg bg-red-50 p-4 text-red-700">{error || "Product not found."}</p></div>;

  const status = tile.stock_status || (tile.inventory ? (tile.inventory.quantity === 0 ? "OUT_OF_STOCK" : tile.low_stock ? "LOW_STOCK" : "IN_STOCK") : "INVENTORY_NOT_CONFIGURED");
  const images = tile.images || [];

  return (
    <div className="max-w-5xl space-y-6">
      <TileDetailsNav />
      <div className="grid gap-8 lg:grid-cols-[1.05fr_1fr]">
        <section className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
          <div className="aspect-square overflow-hidden rounded-lg bg-stone-100">
            {images[0] ? <img src={`${API_BASE_URL}${images[0].image_url}`} alt={tile.name} className="h-full w-full object-contain" /> : <div className="flex h-full items-center justify-center text-6xl text-stone-300">◆</div>}
          </div>
          {images.length > 1 && <div className="mt-3 grid grid-cols-5 gap-2">{images.slice(0, 5).map((image) => <img key={image.id} src={`${API_BASE_URL}${image.image_url}`} alt="" className="aspect-square rounded border border-stone-200 object-cover" />)}</div>}
        </section>
        <section className="space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-sm text-stone-500">{tile.sku}</p>
              <h1 className="mt-1 text-3xl font-bold text-stone-900">{tile.name}</h1>
              <p className="mt-3 text-stone-600">{tile.description?.trim() || "Not specified"}</p>
            </div>
            {canEdit && (
              <button
                type="button"
                onClick={startEditing}
                disabled={loadingEditOptions || isEditing}
                className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {loadingEditOptions ? <Loader2 size={15} className="animate-spin" /> : <Pencil size={15} />}
                {loadingEditOptions ? "Loading..." : "Edit"}
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              ["Material", tile.material?.name],
              ["Style", tile.style?.name],
              ["Finish", tile.finish?.name],
              ["Size", tile.size_format?.name],
              ["Application", tile.application?.name],
              ["Color", tile.color_family?.name],
              ["Origin", tile.origin?.name],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-stone-50 p-3">
                <p className="text-xs text-stone-500">{label}</p>
                <p className="mt-1 font-medium text-stone-800">{value || "Not specified"}</p>
              </div>
            ))}
            <div className="rounded-lg bg-stone-50 p-3">
              <p className="text-xs text-stone-500">Texture</p>
              <p className="mt-1 font-medium text-stone-800">{tile.texture?.trim() || "Not specified"}</p>
            </div>
          </div>
          <div className="space-y-1 text-sm text-stone-700">
            <p>Dimensions: {tile.width_cm ?? "Not specified"} x {tile.height_cm ?? "Not specified"} x {tile.thickness_cm ?? "Not specified"} cm</p>
            <p>Price: {tile.price_per_sqm == null ? "Not specified" : `₹${tile.price_per_sqm}/sqm`}</p>
          </div>
          <div className="flex items-center gap-3 border-t border-stone-200 pt-5"><Package size={20} className="text-stone-500" /><span className={`rounded-full px-3 py-1 text-sm font-semibold ${statusStyles[status] || statusStyles.INVENTORY_NOT_CONFIGURED}`}>{status.replaceAll("_", " ")}</span><span className="text-sm text-stone-600">{tile.inventory ? `${tile.inventory.quantity} ${tile.inventory.unit}` : "Inventory information unavailable"}</span></div>
          {getRole() === "user" && <AddToCartControls tile={tile} />}
        </section>
      </div>
      {feedback && !isEditing && (
        <p
          role={feedback.type === "error" ? "alert" : "status"}
          className={`rounded-lg p-3 text-sm ${feedback.type === "error" ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700"}`}
        >
          {feedback.message}
        </p>
      )}
      {isEditing && editForm && categories && (
        <form onSubmit={handleSaveEdit} className="space-y-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-semibold text-stone-900">Edit tile details</h2>
          {feedback?.type === "error" && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{feedback.message}</p>}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {renderCategoryField("Material", "material_id", categories.materials, tile.material, true)}
            {renderCategoryField("Style", "style_id", categories.styles, tile.style)}
            {renderCategoryField("Finish", "finish_id", categories.finishes, tile.finish)}
            {renderCategoryField("Application", "application_id", categories.applications, tile.application)}
            {renderCategoryField("Color", "color_family_id", categories.colors, tile.color_family)}
            {renderCategoryField("Origin", "origin_id", categories.origins, tile.origin)}
          </div>
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium text-stone-700">Description</span>
            <textarea
              value={editForm.description}
              onChange={(event) => updateEditField("description", event.target.value)}
              rows={3}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-stone-800"
            />
          </label>
          <label className="block space-y-1.5 text-sm">
            <span className="font-medium text-stone-700">Texture</span>
            <input
              value={editForm.texture}
              onChange={(event) => updateEditField("texture", event.target.value)}
              placeholder="Not specified"
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-stone-800"
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {([
              ["Width (cm)", "width_cm"],
              ["Height (cm)", "height_cm"],
              ["Thickness (cm)", "thickness_cm"],
              ["Price per sqm (₹)", "price_per_sqm"],
            ] as const).map(([label, field]) => (
              <label key={field} className="block space-y-1.5 text-sm">
                <span className="font-medium text-stone-700">{label}</span>
                <input
                  type="number"
                  step="any"
                  min={field === "price_per_sqm" ? "0" : "0.000001"}
                  value={editForm[field]}
                  onChange={(event) => updateEditField(field, event.target.value)}
                  className="w-full rounded-lg border border-stone-300 px-3 py-2 text-stone-800"
                />
              </label>
            ))}
          </div>
          <div className="flex flex-wrap justify-end gap-3">
            <button
              type="button"
              onClick={() => {
                setIsEditing(false);
                setEditForm(null);
                setFeedback(null);
              }}
              disabled={savingEdit}
              className="inline-flex items-center gap-2 rounded-lg border border-stone-300 px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50 disabled:opacity-50"
            >
              <X size={15} /> Cancel
            </button>
            <button
              type="submit"
              disabled={savingEdit}
              className="inline-flex items-center gap-2 rounded-lg bg-stone-800 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {savingEdit ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
              {savingEdit ? "Saving..." : "Save changes"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function TileDetailsPage({ params }: { params: Promise<{ tileId: string }> }) {
  return (
    <Suspense fallback={<div className="flex min-h-[50vh] items-center justify-center text-stone-500"><Loader2 className="animate-spin mr-2" /> Loading product...</div>}>
      <TileDetailsContent params={params} />
    </Suspense>
  );
}
