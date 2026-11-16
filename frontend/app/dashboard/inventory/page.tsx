"use client";
import { Fragment, useEffect, useState } from "react";
import api from "@/lib/api";
import { getRole } from "@/lib/auth";
import { Check, Loader2, Pencil, X } from "lucide-react";

interface InventoryItem {
  id: number;
  tile_id: number;
  quantity: number;
  unit: string;
  low_stock_threshold: number;
}

interface Tile {
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
  images: { id: number; image_url: string; is_primary: boolean }[];
}

interface Category { id: number; name: string; }
interface Categories {
  materials: Category[];
  styles: Category[];
  finishes: Category[];
  sizes: Category[];
  applications: Category[];
  colors: Category[];
  origins: Category[];
}

interface RowEditForm {
  name: string;
  description: string;
  texture: string;
  material_id: string;
  style_id: string;
  finish_id: string;
  size_format_id: string;
  application_id: string;
  color_family_id: string;
  origin_id: string;
  width_cm: string;
  height_cm: string;
  thickness_cm: string;
  price_per_sqm: string;
  quantity: string;
  unit: string;
  low_stock_threshold: string;
}

const rowEditForm = (tile: Tile, item: InventoryItem): RowEditForm => ({
  name: tile.name,
  description: tile.description ?? "",
  texture: tile.texture ?? "",
  material_id: tile.material?.id?.toString() ?? "",
  style_id: tile.style?.id?.toString() ?? "",
  finish_id: tile.finish?.id?.toString() ?? "",
  size_format_id: tile.size_format?.id?.toString() ?? "",
  application_id: tile.application?.id?.toString() ?? "",
  color_family_id: tile.color_family?.id?.toString() ?? "",
  origin_id: tile.origin?.id?.toString() ?? "",
  width_cm: tile.width_cm?.toString() ?? "",
  height_cm: tile.height_cm?.toString() ?? "",
  thickness_cm: tile.thickness_cm?.toString() ?? "",
  price_per_sqm: tile.price_per_sqm?.toString() ?? "",
  quantity: item.quantity.toString(),
  unit: item.unit,
  low_stock_threshold: item.low_stock_threshold.toString(),
});

export default function InventoryPage() {
  const [inventory, setInventory] = useState<InventoryItem[]>([]);
  const [tiles, setTiles]         = useState<Record<number, Tile>>({});
  const [loading, setLoading]     = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editForm, setEditForm] = useState<RowEditForm | null>(null);
  const [categories, setCategories] = useState<Categories | null>(null);
  const [saving, setSaving] = useState(false);
  const [canEdit, setCanEdit] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [showLowOnly, setShowLowOnly] = useState(false);
  const [filters, setFilters] = useState({
    query: "", material: "", color: "", finish: "", texture: "", style: "", application: "",
  });

  const fetchAll = async () => {
    setLoading(true);
    try {
      const [invRes, tilesRes] = await Promise.all([
        api.get("/api/inventory/"),
        api.get("/api/tiles/?limit=500"),
      ]);
      setInventory(invRes.data);

      // Build tile lookup map
      const tileMap: Record<number, Tile> = {};
      tilesRes.data.forEach((t: Tile) => { tileMap[t.id] = t; });
      setTiles(tileMap);
    } catch {}
    setLoading(false);
  };

  useEffect(() => { fetchAll(); }, []);

  useEffect(() => {
    const role = getRole();
    setCanEdit(role === "admin" || role === "super_admin");
  }, []);

  const startEditing = async (tile: Tile | undefined, item: InventoryItem) => {
    if (!canEdit || !tile) return;
    setFeedback(null);
    try {
      const response = await api.get<Categories>("/api/categories/all");
      setCategories(response.data);
      setEditForm(rowEditForm(tile, item));
      setEditingId(item.tile_id);
    } catch {
      setFeedback({ type: "error", message: "Tile edit options could not be loaded." });
    }
  };

  const saveRow = async (tileId: number) => {
    if (!editForm || !canEdit) return;
    const dimensions = [editForm.width_cm, editForm.height_cm, editForm.thickness_cm];
    if (!editForm.name.trim() || !editForm.material_id) {
      setFeedback({ type: "error", message: "Tile name and material are required." });
      return;
    }
    if (dimensions.some((value) => value.trim() !== "" && (!Number.isFinite(Number(value)) || Number(value) <= 0))) {
      setFeedback({ type: "error", message: "Dimensions must be positive numbers or left empty." });
      return;
    }
    if (editForm.quantity.trim() === "" || editForm.low_stock_threshold.trim() === "" || !editForm.unit.trim()) {
      setFeedback({ type: "error", message: "Quantity, stock unit, and threshold are required." });
      return;
    }
    const price = editForm.price_per_sqm.trim() === "" ? null : Number(editForm.price_per_sqm);
    const quantity = Number(editForm.quantity);
    const threshold = Number(editForm.low_stock_threshold);
    if (price !== null && (!Number.isFinite(price) || price < 0)) {
      setFeedback({ type: "error", message: "Price must be zero or greater, or left empty." });
      return;
    }
    if (!Number.isInteger(quantity) || quantity < 0 || !Number.isInteger(threshold) || threshold < 0) {
      setFeedback({ type: "error", message: "Stock and threshold must be whole numbers of zero or greater." });
      return;
    }

    const nullableNumber = (value: string) => value.trim() === "" ? null : Number(value);
    const nullableId = (value: string) => value === "" ? null : Number(value);
    setSaving(true);
    setFeedback(null);
    try {
      await api.put(`/api/inventory/${tileId}/details`, {
        name: editForm.name.trim(),
        description: editForm.description.trim() || null,
        texture: editForm.texture.trim() || null,
        material_id: Number(editForm.material_id),
        style_id: nullableId(editForm.style_id),
        finish_id: nullableId(editForm.finish_id),
        size_format_id: nullableId(editForm.size_format_id),
        application_id: nullableId(editForm.application_id),
        color_family_id: nullableId(editForm.color_family_id),
        origin_id: nullableId(editForm.origin_id),
        width_cm: nullableNumber(editForm.width_cm),
        height_cm: nullableNumber(editForm.height_cm),
        thickness_cm: nullableNumber(editForm.thickness_cm),
        price_per_sqm: price,
        quantity,
        unit: editForm.unit,
        low_stock_threshold: threshold,
      });
      setEditingId(null);
      setEditForm(null);
      setFeedback({ type: "success", message: "Tile details and stock saved." });
      await fetchAll();
    } catch (saveError) {
      const response = (saveError as { response?: { data?: { detail?: unknown } } }).response;
      const detail = response?.data?.detail;
      setFeedback({
        type: "error",
        message: typeof detail === "string" ? detail : "Tile details and stock could not be saved.",
      });
    } finally {
      setSaving(false);
    }
  };

  const filtered = inventory.filter((item) => {
    if (showLowOnly && item.quantity > item.low_stock_threshold) return false;
    const tile = tiles[item.tile_id];
    const includes = (value: string | undefined, filter: string) =>
      !filter || Boolean(value?.toLowerCase().includes(filter.trim().toLowerCase()));
    return includes(`${tile?.sku ?? ""} ${tile?.name ?? ""}`, filters.query)
      && includes(tile?.material?.name, filters.material)
      && includes(tile?.color_family?.name, filters.color)
      && includes(tile?.finish?.name, filters.finish)
      && includes(tile?.texture ?? undefined, filters.texture)
      && includes(tile?.style?.name, filters.style)
      && includes(tile?.application?.name, filters.application);
  });

  const lowCount = inventory.filter(
    (i) => i.quantity <= i.low_stock_threshold
  ).length;
  const colorOptions = Array.from(
    new Set(
      Object.values(tiles)
        .map((tile) => tile.color_family?.name)
        .filter((name): name is string => Boolean(name))
    )
  ).sort((a, b) => a.localeCompare(b));

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-800">Inventory</h1>
          {lowCount > 0 && (
            <p className="text-sm text-red-500 mt-1">
              ⚠️ {lowCount} tiles are low on stock
            </p>
          )}
        </div>
        <button
          onClick={() => setShowLowOnly(!showLowOnly)}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition
            ${showLowOnly
              ? "bg-red-500 text-white"
              : "border border-stone-300 text-stone-600 hover:bg-stone-50"
            }`}
        >
          {showLowOnly ? "Show All" : `⚠️ Low Stock (${lowCount})`}
        </button>
      </div>
      {feedback && (
        <p
          role={feedback.type === "error" ? "alert" : "status"}
          className={`mb-4 rounded-lg p-3 text-sm ${feedback.type === "error" ? "bg-red-50 text-red-700" : "bg-emerald-50 text-emerald-700"}`}
        >
          {feedback.message}
        </p>
      )}
      <section aria-label="Inventory filters" className="mb-4 grid gap-3 rounded-xl border border-stone-200 bg-white p-4 sm:grid-cols-2 lg:grid-cols-4">
        {([
          ["query", "SKU / tile name"],
          ["material", "Material"],
          ["color", "Color"],
          ["finish", "Finish"],
          ["texture", "Texture"],
          ["style", "Style"],
          ["application", "Application area"],
        ] as const).map(([key, label]) => (
          <label key={key} className="text-xs font-medium text-stone-600">
            {label}
            {key === "color" ? (
              <select
                value={filters.color}
                onChange={(event) => setFilters((current) => ({ ...current, color: event.target.value }))}
                className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm font-normal text-stone-800"
              >
                <option value="">All colors</option>
                {colorOptions.map((color) => (
                  <option key={color} value={color}>{color}</option>
                ))}
              </select>
            ) : (
              <input
                value={filters[key]}
                onChange={(event) => setFilters((current) => ({ ...current, [key]: event.target.value }))}
                placeholder={`Filter ${label.toLowerCase()}`}
                className="mt-1 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm font-normal text-stone-800"
              />
            )}
          </label>
        ))}
      </section>

      {/* Table */}
      <div className="bg-white rounded-xl border border-stone-200
                      shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-stone-50 border-b border-stone-200">
            <tr>
              <th className="text-left px-4 py-3 text-stone-600 font-medium">
                Tile
              </th>
              <th className="text-left px-4 py-3 text-stone-600 font-medium">
                SKU
              </th>
              <th className="text-left px-4 py-3 text-stone-600 font-medium">
                Stock
              </th>
              <th className="text-left px-4 py-3 text-stone-600 font-medium">
                Threshold
              </th>
              <th className="text-left px-4 py-3 text-stone-600 font-medium">
                Status
              </th>
              {canEdit && <th className="text-left px-4 py-3 text-stone-600 font-medium">Edit</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {loading ? (
              <tr>
                <td colSpan={canEdit ? 6 : 5}
                    className="text-center py-12 text-stone-400">
                  Loading...
                </td>
              </tr>
            ) : filtered.map((item) => {
              const tile    = tiles[item.tile_id];
              const isLow   = item.quantity <= item.low_stock_threshold;
              const editing = editingId === item.tile_id;

              return (
                <Fragment key={item.id}>
                <tr
                    className={`transition ${
                      isLow ? "bg-red-50" : "hover:bg-stone-50"
                    }`}>
                  {/* Tile Info */}
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg overflow-hidden
                                      bg-stone-100 border border-stone-200
                                      flex-shrink-0">
                        {tile?.images?.[0] ? (
                          <img
                            src={`http://localhost:8000${tile.images[0].image_url}`}
                            className="w-full h-full object-cover"
                            alt={tile.name}
                          />
                        ) : (
                          <div className="w-full h-full flex items-center
                                          justify-center text-lg">🪨</div>
                        )}
                      </div>
                      <span className="font-medium text-stone-800">
                        {tile?.name || `Tile #${item.tile_id}`}
                      </span>
                    </div>
                  </td>

                  <td className="px-4 py-3 font-mono text-stone-500 text-xs">
                    {tile?.sku || "—"}
                  </td>

                  {/* Editable Quantity */}
                  <td className="px-4 py-3">
                    <span className={`font-semibold ${
                      isLow ? "text-red-600" : "text-stone-800"
                    }`}>
                      {item.quantity} {item.unit}
                    </span>
                  </td>

                  <td className="px-4 py-3 text-stone-400 text-xs">
                    Min {item.low_stock_threshold}
                  </td>

                  {/* Status Badge */}
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs
                                      font-medium ${
                      item.quantity === 0
                        ? "bg-red-100 text-red-700"
                        : isLow
                        ? "bg-yellow-100 text-yellow-700"
                        : "bg-green-100 text-green-700"
                    }`}>
                      {item.quantity === 0
                        ? "Out of Stock"
                        : isLow ? "Low Stock" : "In Stock"}
                    </span>
                  </td>

                  {/* Edit / Save Button */}
                  {canEdit && (
                    <td className="px-4 py-3">
                      {!editing && (
                        <button
                          type="button"
                          onClick={() => startEditing(tile, item)}
                          className="text-stone-500 hover:text-stone-800 transition"
                          title="Edit tile and stock"
                          aria-label={`Edit ${tile?.name ?? `tile ${item.tile_id}`} details and stock`}
                        >
                          <Pencil size={16} />
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              {editing && tile && categories && (
                <tr key={`${item.id}-editor`} className="bg-stone-50">
                  <td colSpan={canEdit ? 6 : 5} className="px-4 py-4">
                    <form
                      onSubmit={(event) => {
                        event.preventDefault();
                        void saveRow(item.tile_id);
                      }}
                      className="grid gap-4 md:grid-cols-2 xl:grid-cols-3"
                    >
                      <label className="space-y-1 text-xs text-stone-600">
                        Tile name *
                        <input required value={editForm?.name ?? ""} onChange={(event) => setEditForm((current) => current && ({ ...current, name: event.target.value }))} className="w-full rounded border border-stone-300 px-2 py-1.5 text-sm" />
                      </label>
                      {([
                        ["Material *", "material_id", categories.materials, tile.material, true],
                        ["Style", "style_id", categories.styles, tile.style, false],
                        ["Finish", "finish_id", categories.finishes, tile.finish, false],
                        ["Size", "size_format_id", categories.sizes, tile.size_format, false],
                        ["Application", "application_id", categories.applications, tile.application, false],
                        ["Color", "color_family_id", categories.colors, tile.color_family, false],
                        ["Origin", "origin_id", categories.origins, tile.origin, false],
                      ] as const).map(([label, key, options, current, required]) => {
                        const selected = editForm?.[key] ?? "";
                        const availableOptions = current && !options.some((option) => option.id === current.id)
                          ? [current, ...options]
                          : options;
                        return (
                          <label key={key} className="space-y-1 text-xs text-stone-600">
                            {label}
                            <select required={required} value={selected} onChange={(event) => setEditForm((form) => form && ({ ...form, [key]: event.target.value }))} className="w-full rounded border border-stone-300 bg-white px-2 py-1.5 text-sm">
                              <option value="">{required ? "Select material" : "Not specified"}</option>
                              {availableOptions.map((option) => <option key={option.id} value={option.id}>{option.name}</option>)}
                            </select>
                          </label>
                        );
                      })}
                      <label className="space-y-1 text-xs text-stone-600">
                        Texture
                        <input value={editForm?.texture ?? ""} onChange={(event) => setEditForm((current) => current && ({ ...current, texture: event.target.value }))} placeholder="Not specified" className="w-full rounded border border-stone-300 px-2 py-1.5 text-sm" />
                      </label>
                      <label className="space-y-1 text-xs text-stone-600 md:col-span-2 xl:col-span-3">
                        Description
                        <textarea rows={2} value={editForm?.description ?? ""} onChange={(event) => setEditForm((current) => current && ({ ...current, description: event.target.value }))} className="w-full rounded border border-stone-300 px-2 py-1.5 text-sm" />
                      </label>
                      {([
                        ["Width (cm)", "width_cm", "0.000001"],
                        ["Height (cm)", "height_cm", "0.000001"],
                        ["Thickness (cm)", "thickness_cm", "0.000001"],
                        ["Price/sqm", "price_per_sqm", "0"],
                        ["Quantity", "quantity", "0"],
                        ["Low-stock threshold", "low_stock_threshold", "0"],
                      ] as const).map(([label, key, min]) => (
                        <label key={key} className="space-y-1 text-xs text-stone-600">
                          {label}
                          <input type="number" min={min} step={key === "quantity" || key === "low_stock_threshold" ? "1" : "any"} required={key === "quantity" || key === "low_stock_threshold"} value={editForm?.[key] ?? ""} onChange={(event) => setEditForm((current) => current && ({ ...current, [key]: event.target.value }))} className="w-full rounded border border-stone-300 px-2 py-1.5 text-sm" />
                        </label>
                      ))}
                      <label className="space-y-1 text-xs text-stone-600">
                        Stock unit
                        <input required value={editForm?.unit ?? ""} onChange={(event) => setEditForm((current) => current && ({ ...current, unit: event.target.value }))} className="w-full rounded border border-stone-300 px-2 py-1.5 text-sm" />
                      </label>
                      <div className="flex items-end justify-end gap-2 md:col-span-2 xl:col-span-3">
                        <button type="button" disabled={saving} onClick={() => { setEditingId(null); setEditForm(null); setFeedback(null); }} className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-2 text-sm text-stone-700 disabled:opacity-50"><X size={14} />Cancel</button>
                        <button type="submit" disabled={saving} className="inline-flex items-center gap-1 rounded bg-stone-800 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">{saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}Save tile and stock</button>
                      </div>
                    </form>
                  </td>
                </tr>
              )}
              </Fragment>
              );
            })}
          </tbody>
        </table>

        <div className="px-4 py-3 border-t border-stone-100
                        text-xs text-stone-400">
          {filtered.length} items shown
        </div>
      </div>
    </div>
  );
}