"use client";

import { useEffect, useMemo, useState } from "react";
import { FileText, Loader2, Plus, Trash2 } from "lucide-react";
import api from "@/lib/api";
import { downloadQuotationPdf, type QuotationPdf } from "@/lib/quotationPdf";

type CatalogTile = {
  id: number;
  sku: string;
  name: string;
  is_active: boolean;
  width_cm?: number | null;
  height_cm?: number | null;
  price_per_sqm?: number | null;
  material?: { name: string } | null;
  size_format?: { name: string } | null;
};

type QuoteLine = {
  key: string;
  tile: CatalogTile;
  quantity: string;
  area_sqm: string;
  rate_per_sqm: string;
};

type SavedQuotation = QuotationPdf & {
  id: number;
  status: string;
  created_by_email: string;
};

const gstDefault = 18;

const suggestedArea = (tile: CatalogTile) => {
  if (tile.width_cm && tile.height_cm) {
    return ((tile.width_cm / 100) * (tile.height_cm / 100)).toFixed(4);
  }
  return "";
};

const sizeLabel = (tile: CatalogTile) => {
  if (tile.size_format?.name) return tile.size_format.name;
  if (tile.width_cm && tile.height_cm) return `${tile.width_cm} x ${tile.height_cm} cm`;
  return "Not specified";
};

const money = (value: number) =>
  `₹${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function QuotationsPage() {
  const [quotations, setQuotations] = useState<SavedQuotation[]>([]);
  const [tiles, setTiles] = useState<CatalogTile[]>([]);
  const [tileQuery, setTileQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [client, setClient] = useState({
    client_name: "",
    company_name: "",
    project_name: "",
    email: "",
    phone: "",
    address: "",
    gst_rate: String(gstDefault),
  });
  const [lines, setLines] = useState<QuoteLine[]>([]);

  const loadQuotations = () =>
    api.get<SavedQuotation[]>("/api/quotations").then(({ data }) => setQuotations(data));

  useEffect(() => {
    Promise.all([
      loadQuotations(),
      api.get<CatalogTile[]>("/api/tiles/", { params: { is_active: true, limit: 200 } }),
    ]).then(([, tileResponse]) => {
      setTiles(tileResponse.data.filter((tile) => tile.is_active));
    }).catch(() => {
      setError("Quotations could not be loaded.");
    }).finally(() => setLoading(false));
  }, []);

  const filteredTiles = useMemo(() => {
    const query = tileQuery.trim().toLowerCase();
    const selected = new Set(lines.map((line) => line.tile.id));
    return tiles.filter((tile) => {
      if (selected.has(tile.id)) return false;
      if (!query) return true;
      return tile.name.toLowerCase().includes(query) || tile.sku.toLowerCase().includes(query);
    }).slice(0, 8);
  }, [tileQuery, tiles, lines]);

  const parsedLines = lines.map((line) => {
    const quantity = Number(line.quantity);
    const area = Number(line.area_sqm);
    const rate = Number(line.rate_per_sqm);
    const valid =
      Number.isInteger(quantity) && quantity >= 1 &&
      Number.isFinite(area) && area > 0 &&
      Number.isFinite(rate) && rate >= 0 && line.rate_per_sqm.trim() !== "";
    return {
      ...line,
      quantity,
      area,
      rate,
      valid,
      lineTotal: valid ? Math.round(quantity * area * rate * 100) / 100 : 0,
    };
  });

  const gstRate = Number(client.gst_rate);
  const gstValid = Number.isFinite(gstRate) && gstRate >= 0 && gstRate <= 100;
  const subtotal = parsedLines.reduce((sum, line) => sum + line.lineTotal, 0);
  const gstAmount = gstValid ? Math.round(subtotal * gstRate) / 100 : 0;
  const grandTotal = Math.round((subtotal + gstAmount) * 100) / 100;

  const addTile = (tile: CatalogTile) => {
    setLines((current) => [
      ...current,
      {
        key: `${tile.id}-${Date.now()}`,
        tile,
        quantity: "1",
        area_sqm: suggestedArea(tile),
        rate_per_sqm: tile.price_per_sqm == null ? "" : String(tile.price_per_sqm),
      },
    ]);
    setTileQuery("");
  };

  const saveQuotation = async () => {
    setError("");
    setNotice("");
    if (!client.client_name.trim()) {
      setError("Client name is required.");
      return;
    }
    if (!gstValid) {
      setError("GST must be a number between 0 and 100.");
      return;
    }
    if (parsedLines.length === 0) {
      setError("Add at least one catalog tile.");
      return;
    }
    const invalid = parsedLines.find((line) => !line.valid);
    if (invalid) {
      setError(
        invalid.tile.price_per_sqm == null && invalid.rate_per_sqm.trim() === ""
          ? `${invalid.tile.sku} has no catalog price. Enter a quotation-specific rate before saving.`
          : `Quantity, area (m²), and rate are required for ${invalid.tile.sku}. Missing dimensions were not invented.`
      );
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.post<SavedQuotation>("/api/quotations", {
        client_name: client.client_name.trim(),
        company_name: client.company_name.trim() || null,
        project_name: client.project_name.trim() || null,
        email: client.email.trim() || null,
        phone: client.phone.trim() || null,
        address: client.address.trim() || null,
        gst_rate: gstRate,
        items: parsedLines.map((line) => ({
          tile_id: line.tile.id,
          quantity: line.quantity,
          area_sqm: line.area,
          rate_per_sqm: line.rate,
        })),
      });
      setNotice(`Saved ${data.quotation_number}. This quotation did not place an order or change stock.`);
      setLines([]);
      await loadQuotations();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Quotation could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="flex min-h-64 items-center justify-center gap-2 text-stone-500"><Loader2 className="animate-spin" /> Loading quotations...</div>;
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase text-cyan-800">B2B sales document</p>
        <h1 className="mt-1 flex items-center gap-2 text-2xl font-semibold text-stone-900"><FileText className="text-cyan-700" /> Quotations</h1>
        <p className="mt-1 text-sm text-stone-500">Create a priced offer from existing catalog tiles. Quotations never place orders or deduct inventory.</p>
      </header>

      {error && <p role="alert" className="border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {notice && <p className="border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}

      <section className="border border-stone-200 bg-white p-5">
        <h2 className="font-semibold text-stone-900">Client and project</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field label="Client name" required value={client.client_name} onChange={(value) => setClient((current) => ({ ...current, client_name: value }))} />
          <Field label="Company" value={client.company_name} onChange={(value) => setClient((current) => ({ ...current, company_name: value }))} />
          <Field label="Project" value={client.project_name} onChange={(value) => setClient((current) => ({ ...current, project_name: value }))} />
          <Field label="Email" value={client.email} onChange={(value) => setClient((current) => ({ ...current, email: value }))} />
          <Field label="Phone" value={client.phone} onChange={(value) => setClient((current) => ({ ...current, phone: value }))} />
          <Field label="GST %" value={client.gst_rate} onChange={(value) => setClient((current) => ({ ...current, gst_rate: value }))} />
          <label className="sm:col-span-2 text-xs text-stone-600">Address
            <textarea value={client.address} onChange={(event) => setClient((current) => ({ ...current, address: event.target.value }))} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm" rows={2} />
          </label>
        </div>
      </section>

      <section className="border border-stone-200 bg-white p-5">
        <h2 className="font-semibold text-stone-900">Catalog tiles</h2>
        <input
          value={tileQuery}
          onChange={(event) => setTileQuery(event.target.value)}
          placeholder="Search active catalog tiles by name or SKU"
          className="mt-3 w-full rounded border border-stone-300 px-3 py-2 text-sm"
        />
        {filteredTiles.length > 0 && (
          <ul className="mt-2 divide-y divide-stone-100 border border-stone-200">
            {filteredTiles.map((tile) => (
              <li key={tile.id} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2 text-sm">
                <div>
                  <p className="font-medium text-stone-800">{tile.name}</p>
                  <p className="text-xs text-stone-500">
                    {tile.sku} · {tile.material?.name || "Material not specified"} · {sizeLabel(tile)} · {tile.price_per_sqm == null ? "Catalog rate not specified" : `${money(tile.price_per_sqm)} / m²`}
                  </p>
                </div>
                <button type="button" onClick={() => addTile(tile)} className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50">
                  <Plus size={14} /> Add
                </button>
              </li>
            ))}
          </ul>
        )}

        {lines.length === 0 ? (
          <p className="mt-4 py-6 text-center text-sm text-stone-500">No tiles added. Only existing catalog products can be quoted.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-stone-50 text-xs uppercase text-stone-500">
                <tr>
                  <th className="px-3 py-2">Tile</th>
                  <th className="px-3 py-2">Qty</th>
                  <th className="px-3 py-2">Area m²</th>
                  <th className="px-3 py-2">Rate / m²</th>
                  <th className="px-3 py-2">Line total</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {parsedLines.map((line) => (
                  <tr key={line.key} className="border-t border-stone-100">
                    <td className="px-3 py-2">
                      <p className="font-medium text-stone-800">{line.tile.name}</p>
                      <p className="text-xs text-stone-500">{line.tile.sku} · {line.tile.material?.name || "Material not specified"} · {sizeLabel(line.tile)}</p>
                      {line.tile.price_per_sqm == null && <p className="text-xs text-amber-800">Catalog price missing — enter a quote rate</p>}
                      {!suggestedArea(line.tile) && <p className="text-xs text-amber-800">Dimensions missing — enter area in m²</p>}
                    </td>
                    <td className="px-3 py-2"><input value={line.quantity} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, quantity: event.target.value } : item))} className="w-20 rounded border border-stone-300 px-2 py-1" /></td>
                    <td className="px-3 py-2"><input value={line.area_sqm} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, area_sqm: event.target.value } : item))} className="w-24 rounded border border-stone-300 px-2 py-1" /></td>
                    <td className="px-3 py-2">
                      <input value={line.rate_per_sqm} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, rate_per_sqm: event.target.value } : item))} className="w-28 rounded border border-stone-300 px-2 py-1" />
                      {line.tile.price_per_sqm != null && Number(line.rate_per_sqm) !== line.tile.price_per_sqm && (
                        <p className="text-[11px] text-stone-500">Catalog {money(line.tile.price_per_sqm)}</p>
                      )}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{line.valid ? money(line.lineTotal) : "—"}</td>
                    <td className="px-3 py-2">
                      <button type="button" onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))} className="text-red-700 hover:text-red-900" aria-label={`Remove ${line.tile.sku}`}>
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="mt-4 ml-auto max-w-xs space-y-1 text-sm">
          <div className="flex justify-between"><span>Subtotal</span><strong>{money(subtotal)}</strong></div>
          <div className="flex justify-between"><span>GST {gstValid ? `${gstRate}%` : ""}</span><strong>{gstValid ? money(gstAmount) : "—"}</strong></div>
          <div className="flex justify-between border-t border-stone-200 pt-2 text-base"><span>Grand total</span><strong>{gstValid ? money(grandTotal) : "—"}</strong></div>
        </div>
        <button type="button" onClick={() => void saveQuotation()} disabled={saving} className="mt-4 rounded-lg bg-stone-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">
          {saving ? "Saving..." : "Save quotation"}
        </button>
      </section>

      <section className="border border-stone-200 bg-white p-5">
        <h2 className="font-semibold text-stone-900">Saved quotations</h2>
        {quotations.length === 0 ? (
          <p className="py-8 text-center text-sm text-stone-500">No quotations have been saved yet.</p>
        ) : (
          <ul className="mt-4 space-y-3">
            {quotations.map((quotation) => (
              <li key={quotation.id} className="border border-stone-100 p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-semibold text-stone-900">{quotation.quotation_number} · {quotation.client_name}</p>
                    <p className="text-xs text-stone-500">
                      {quotation.company_name || "No company"} · {quotation.project_name || "No project"} · {quotation.status} · {new Date(quotation.created_at).toLocaleString()} · valid until {new Date(quotation.valid_until).toLocaleDateString()}
                    </p>
                    <p className="text-xs text-stone-500">Prepared by {quotation.created_by_name}</p>
                  </div>
                  <div className="text-right">
                    <p className="font-semibold">{money(quotation.grand_total)}</p>
                    <button type="button" onClick={() => downloadQuotationPdf(quotation)} className="mt-2 rounded border border-stone-300 px-3 py-1.5 text-xs font-medium hover:bg-stone-50">
                      Download PDF
                    </button>
                  </div>
                </div>
                <ul className="mt-3 divide-y divide-stone-100 text-sm">
                  {quotation.items.map((item) => (
                    <li key={item.tile_sku + item.line_total} className="flex justify-between gap-3 py-2">
                      <span>{item.tile_name} ({item.tile_sku}) · {item.quantity} × {item.area_sqm} m² × {money(item.rate_per_sqm)}</span>
                      <span>{money(item.line_total)}</span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Field({ label, value, onChange, required }: { label: string; value: string; onChange: (value: string) => void; required?: boolean }) {
  return (
    <label className="text-xs text-stone-600">{label}{required ? " *" : ""}
      <input required={required} value={value} onChange={(event) => onChange(event.target.value)} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm" />
    </label>
  );
}
