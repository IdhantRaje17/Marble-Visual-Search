"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, Boxes, Loader2, Package, Plus } from "lucide-react";
import api, { API_BASE_URL } from "@/lib/api";
import { type Analytics, formatInr, rangeParams } from "@/lib/analytics";

type CatalogTile = { id: number; sku: string; name: string; is_active: boolean };
type Production = {
  id: number; tile_id: number | null; tile_sku: string; tile_name: string;
  quantity: number; factory_name: string; batch_number: string | null;
  produced_at: string; notes: string | null; inventory_receipt?: boolean;
};
type Movement = {
  id: number; tile_id: number | null; tile_sku: string; tile_name: string;
  movement_type: string; quantity: number; direction: number; unit: string;
  balance_after: number | null; reference_type: string | null; reference_id: number | null;
  reason: string | null; occurred_at: string | null;
};
type FactoryInsights = {
  production_vs_sales: { produced_quantity: number; sold_quantity: number };
  dead_stock: { tile_count: number; age_days: number };
  conversion: {
    searches: number; linked_searches: number; quotations: number;
    closed_quotations: number; closed_orders: number; closed_searches: number;
    search_to_quotation_rate: number; quotation_to_order_rate: number;
    search_to_sale_rate: number;
  };
  stock_aging: {
    categories: {
      key: string; label: string; range: string;
      items: {
        tile_id: number; name: string; sku: string; quantity: number;
        unit: string; stock_date: string; stock_age_days: number;
        image_url: string | null;
      }[];
    }[];
    unaged_tile_count: number;
    note: string;
  };
  top_materials: { material: string; volume_sqm: number; revenue: number }[];
  top_corporate_buyers: {
    company_name: string; completed_orders: number;
    revenue: number | null; revenue_available: boolean;
  }[];
  unattributed_corporate_orders: number;
  material_note: string;
};

export default function FactoryAnalyticsPage() {
  const [rangeDays, setRangeDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [insights, setInsights] = useState<FactoryInsights | null>(null);
  const [tiles, setTiles] = useState<CatalogTile[]>([]);
  const [productions, setProductions] = useState<Production[]>([]);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [activeProductionPoint, setActiveProductionPoint] = useState<{
    date: string;
    produced: number;
    sold: number;
  } | null>(null);
  const [error, setError] = useState("");
  const [insightsError, setInsightsError] = useState("");
  const [productionFeedback, setProductionFeedback] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    tile_id: "", quantity: "", factory_name: "", batch_number: "",
    produced_at: new Date().toISOString().slice(0, 10), notes: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    setActiveProductionPoint(null);
    try {
      const params = rangeParams(rangeDays);
      const [analytics, productionRows, movementRows, tileRows] = await Promise.all([
        api.get<Analytics>("/api/admin/analytics", { params }),
        api.get<Production[]>("/api/admin/production", { params }),
        api.get<Movement[]>("/api/inventory/movements", { params }),
        api.get<CatalogTile[]>("/api/tiles/?is_active=true&limit=500"),
      ]);
      setData(analytics.data);
      setProductions(productionRows.data);
      setMovements(movementRows.data);
      setTiles(Array.isArray(tileRows.data) ? tileRows.data.filter((tile) => tile.is_active) : []);
      setError("");
    } catch {
      setError("Factory analytics could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [rangeDays]);

  const loadFactoryInsights = useCallback(async () => {
    setInsights(null);
    setInsightsError("");
    try {
      const response = await api.get<FactoryInsights>(
        "/api/admin/factory-insights",
        { params: rangeParams(rangeDays) },
      );
      setInsights(response.data);
      setInsightsError("");
    } catch {
      setInsightsError("Additional factory analytics could not be loaded.");
    }
  }, [rangeDays]);

  useEffect(() => {
    void load();
    void loadFactoryInsights();
  }, [load, loadFactoryInsights]);

  const saveProduction = async () => {
    if (!form.tile_id || !form.quantity || !form.factory_name.trim()) {
      setError("Tile, produced quantity, and factory name are required.");
      return;
    }
    setSaving(true);
    setError("");
    setProductionFeedback("");
    try {
      const response = await api.post("/api/admin/production", {
        tile_id: Number(form.tile_id),
        quantity: Number(form.quantity),
        factory_name: form.factory_name.trim(),
        batch_number: form.batch_number.trim() || null,
        produced_at: form.produced_at,
        notes: form.notes.trim() || null,
      });
      setForm((current) => ({ ...current, quantity: "", batch_number: "", notes: "" }));
      const savedTile = tiles.find((tile) => tile.id === Number(form.tile_id));
      setProductionFeedback(
        `${savedTile?.sku ?? "Tile"} production saved: ${response.data.quantity} units recorded.`
      );
      await Promise.all([load(), loadFactoryInsights()]);
    } catch (saveError) {
      const detail = (saveError as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail || "Production entry could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  if (error && !data) return <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">{error}</p>;
  if (!data) return <div className="flex min-h-64 items-center justify-center gap-2 text-stone-500"><Loader2 className="animate-spin" /> Loading factory analytics...</div>;

  const productionPeak = Math.max(1, ...data.orders.production_vs_sales.trend.map((point) => Math.max(point.produced, point.sold)));
  const productionTrendHasData = data.orders.production_vs_sales.trend.some(
    (point) => point.produced > 0 || point.sold > 0,
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase text-cyan-800">Real database values</p>
          <h1 className="mt-1 text-2xl font-semibold text-stone-900">Factory Analytics</h1>
          <p className="mt-1 text-sm text-stone-500">{data.date_range.start_date} through {data.date_range.end_date}</p>
        </div>
        <label className="text-sm text-stone-600">Date range
          <select value={rangeDays} onChange={(event) => setRangeDays(Number(event.target.value))} className="ml-2 border border-stone-300 bg-white px-3 py-2">
            <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
          </select>
        </label>
      </header>
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {productionFeedback && <p role="status" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">{productionFeedback}</p>}
      {loading && <p className="text-xs text-stone-500">Updating date range...</p>}

      <section className="grid gap-4 sm:grid-cols-3">
        <Metric label="Produced in range" value={data.orders.production_vs_sales.produced_quantity.toLocaleString()} note="Production entries with inventory receipt" icon={Boxes} />
        <Metric label="Completed units sold" value={data.orders.units_sold.toLocaleString()} note={data.orders.completed === 0 ? "Zero completed sales" : undefined} icon={Package} />
        <Metric label="Completed-order revenue" value={formatInr(data.orders.revenue, data.orders.revenue_available)} note={data.orders.revenue_reason} icon={Activity} />
      </section>

      {insightsError && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{insightsError}</p>}
      {insights && (
        <>
          <section className="grid gap-4 sm:grid-cols-3">
            <Metric
              label="Production vs sales"
              value={`${insights.production_vs_sales.produced_quantity.toLocaleString()} / ${insights.production_vs_sales.sold_quantity.toLocaleString()}`}
              note="Produced / completed units in selected period"
              icon={Activity}
            />
            <Metric
              label={`Aged dead stock (>${insights.dead_stock.age_days} days)`}
              value={`${insights.dead_stock.tile_count.toLocaleString()} tiles`}
              note="On-hand tile SKUs with last recorded receipt over 180 days ago"
              icon={Boxes}
            />
            <Metric
              label="Search-to-sale conversion"
              value={`${insights.conversion.search_to_sale_rate.toFixed(2)}%`}
              note={`${insights.conversion.closed_searches.toLocaleString()} of ${insights.conversion.searches.toLocaleString()} searches led to a closed B2B order`}
              icon={Package}
            />
          </section>

          <section className="border border-stone-200 bg-white p-5">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="font-semibold text-stone-900">Warehouse stock aging report</h2>
                <p className="mt-1 text-xs text-stone-500">{insights.stock_aging.note}</p>
              </div>
              <p className="text-xs text-stone-500">
                {insights.stock_aging.unaged_tile_count} stocked tile(s) have no recorded receipt date
              </p>
            </div>
            <div className="mt-4 space-y-3">
              {insights.stock_aging.categories.map((category) => (
                <details key={category.key} className="border border-stone-200">
                  <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-stone-50">
                    <span className="font-medium text-stone-800">{category.label} <span className="font-normal text-stone-500">({category.range})</span></span>
                    <span className="text-sm text-stone-600">{category.items.length} stocked tile(s)</span>
                  </summary>
                  {category.items.length > 0 ? (
                    <div className="grid gap-3 border-t border-stone-100 p-4 sm:grid-cols-2 lg:grid-cols-3">
                      {category.items.map((item) => (
                        <article key={item.tile_id} className="flex gap-3 rounded-lg border border-stone-200 p-3">
                          <div
                            role="img"
                            aria-label={`${item.name} tile`}
                            className={`flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded bg-stone-100 text-2xl text-stone-300 ${item.image_url ? "bg-cover bg-center" : ""}`}
                            style={item.image_url ? {
                              backgroundImage: `url("${API_BASE_URL}${item.image_url}")`,
                            } : undefined}
                          >
                            {!item.image_url && "◆"}
                          </div>
                          <div className="min-w-0 text-sm">
                            <p className="truncate font-medium text-stone-800">{item.name}</p>
                            <p className="text-xs text-stone-500">SKU {item.sku}</p>
                            <p className="mt-1 text-stone-700">{item.quantity.toLocaleString()} {item.unit}</p>
                            <p className="text-xs text-stone-500">Stock date: {new Date(`${item.stock_date}T00:00:00`).toLocaleDateString()}</p>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : <p className="border-t border-stone-100 px-4 py-5 text-sm text-stone-500">No stocked tiles in this age band.</p>}
                </details>
              ))}
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <div className="border border-stone-200 bg-white p-5">
              <h2 className="font-semibold text-stone-900">Top-selling materials</h2>
              <p className="mt-1 text-xs text-stone-500">{insights.material_note}</p>
              {insights.top_materials.length > 0 ? (
                <ul className="mt-4 divide-y divide-stone-100">
                  {insights.top_materials.map((material) => (
                    <li key={material.material} className="py-3">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="font-medium text-stone-800">{material.material}</span>
                        <span className="text-stone-600">{material.volume_sqm.toLocaleString(undefined, { maximumFractionDigits: 2 })} m² · {formatInr(material.revenue)}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <p className="mt-4 text-sm text-stone-500">No unambiguous linked material sales in this date range.</p>}
            </div>

            <div className="border border-stone-200 bg-white p-5">
              <h2 className="font-semibold text-stone-900">Top corporate buyers</h2>
              <p className="mt-1 text-xs text-stone-500">Ranked by completed orders; buyer and order revenue come from explicit quotation links and stored order totals.</p>
              {insights.top_corporate_buyers.length > 0 ? (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead><tr className="text-xs uppercase text-stone-500"><th className="py-2">Company</th><th>Completed orders</th><th>Revenue</th></tr></thead>
                    <tbody>
                      {insights.top_corporate_buyers.map((buyer) => (
                        <tr key={buyer.company_name} className="border-t border-stone-100">
                          <td className="py-3 font-medium text-stone-800">{buyer.company_name}</td>
                          <td>{buyer.completed_orders.toLocaleString()}</td>
                          <td>{formatInr(buyer.revenue, buyer.revenue_available)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="mt-4 text-sm text-stone-500">No completed orders with an explicitly linked company quotation in this date range.</p>}
              {insights.unattributed_corporate_orders > 0 && (
                <p className="mt-2 text-xs text-stone-500">
                  {insights.unattributed_corporate_orders} order(s) have ambiguous or missing company attribution and are not ranked.
                </p>
              )}
            </div>
          </section>
        </>
      )}

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Production vs actual sales</h2>
          <p className="mt-1 text-xs text-stone-500">{data.orders.production_vs_sales.reason}</p>
          {productionTrendHasData ? (
            <div className="mt-4" role="img" aria-label="Production and completed sales chart">
              {(() => {
                const trend = data.orders.production_vs_sales.trend;
                const point = activeProductionPoint ?? [...trend].reverse().find(
                  (item) => item.produced > 0 || item.sold > 0
                ) ?? trend[0];
                return (
                  <div className="mb-2 flex flex-wrap items-center gap-3 text-xs">
                    <span className="font-medium text-stone-700">{point?.date}</span>
                    <span className="text-cyan-800">Produced {point?.produced ?? 0}</span>
                    <span className="text-emerald-700">Sold {point?.sold ?? 0}</span>
                  </div>
                );
              })()}
              <svg viewBox="0 0 600 160" className="h-40 w-full" preserveAspectRatio="none">
                {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
                  const y = 12 + (1 - ratio) * 120;
                  return (
                    <g key={ratio}>
                      <line x1="42" x2="592" y1={y} y2={y} stroke="#e7e5e4" strokeWidth="1" />
                      <text x="36" y={y + 4} textAnchor="end" className="fill-stone-400 text-[10px]">
                        {Math.round(productionPeak * ratio)}
                      </text>
                    </g>
                  );
                })}
                {data.orders.production_vs_sales.trend.map((point, index) => {
                  const trend = data.orders.production_vs_sales.trend;
                  const chartWidth = 550;
                  const groupWidth = chartWidth / Math.max(trend.length, 1);
                  const barWidth = Math.max(2, Math.min(12, groupWidth * 0.32));
                  const x = 42 + index * groupWidth + (groupWidth - barWidth * 2 - 2) / 2;
                  const producedHeight = point.produced / productionPeak * 120;
                  const soldHeight = point.sold / productionPeak * 120;
                  return (
                    <g
                      key={point.date}
                      className="cursor-pointer"
                      tabIndex={0}
                      onMouseEnter={() => setActiveProductionPoint(point)}
                      onMouseLeave={() => setActiveProductionPoint(null)}
                      onFocus={() => setActiveProductionPoint(point)}
                      onBlur={() => setActiveProductionPoint(null)}
                    >
                      <title>{`${point.date}: ${point.produced} produced, ${point.sold} sold`}</title>
                      <rect
                        x={42 + index * groupWidth}
                        y="12"
                        width={groupWidth}
                        height="120"
                        fill="transparent"
                      />
                      {point.produced > 0 && (
                        <rect
                          x={x}
                          y={132 - producedHeight}
                          width={barWidth}
                          height={producedHeight}
                          rx="1"
                          fill="#0e7490"
                        />
                      )}
                      {point.sold > 0 && (
                        <rect
                          x={x + barWidth + 2}
                          y={132 - soldHeight}
                          width={barWidth}
                          height={soldHeight}
                          rx="1"
                          fill="#059669"
                        />
                      )}
                    </g>
                  );
                })}
                {data.orders.production_vs_sales.trend.length > 0 && (
                  <>
                    <text x="42" y="154" className="fill-stone-400 text-[10px]">
                      {data.orders.production_vs_sales.trend[0].date}
                    </text>
                    <text x="592" y="154" textAnchor="end" className="fill-stone-400 text-[10px]">
                      {data.orders.production_vs_sales.trend[data.orders.production_vs_sales.trend.length - 1].date}
                    </text>
                  </>
                )}
              </svg>
            </div>
          ) : (
            <div className="mt-4 flex h-40 items-center justify-center rounded border border-dashed border-stone-200 text-sm text-stone-500">
              No production or completed sales in this date range.
            </div>
          )}
          <div className="mt-2 flex gap-4 text-xs text-stone-500"><span className="text-cyan-800">Produced</span><span className="text-emerald-700">Sold</span></div>
        </div>
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Search → quotation → order conversion</h2>
          <p className="mt-1 text-xs text-stone-500">{data.orders.search_to_quotation_to_order.reason}</p>
          {data.orders.search_to_quotation_to_order.available ? (
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <Conversion label="Searches" value={data.orders.search_to_quotation_to_order.searches} />
              <Conversion label="Linked quotes" value={data.orders.search_to_quotation_to_order.linked_quotes} rate={`${data.orders.search_to_quotation_to_order.search_to_quote_rate}%`} />
              <Conversion label="Linked orders" value={data.orders.search_to_quotation_to_order.linked_orders} rate={`${data.orders.search_to_quotation_to_order.quote_to_order_rate}%`} />
            </div>
          ) : <p className="py-8 text-sm text-stone-500">No real linked conversion data exists yet.</p>}
        </div>
      </section>

      <section className="border border-stone-200 bg-white p-5">
        <h2 className="font-semibold text-stone-900">Record production</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <label className="text-xs text-stone-600">SKU *<select value={form.tile_id} onChange={(event) => setForm((current) => ({ ...current, tile_id: event.target.value }))} className="mt-1 w-full border border-stone-300 px-3 py-2 text-sm"><option value="">Select active tile</option>{tiles.map((tile) => <option key={tile.id} value={tile.id}>{tile.sku} · {tile.name}</option>)}</select></label>
          <label className="text-xs text-stone-600">Produced quantity *<input type="number" min="1" value={form.quantity} onChange={(event) => setForm((current) => ({ ...current, quantity: event.target.value }))} className="mt-1 w-full border border-stone-300 px-3 py-2 text-sm" /></label>
          <label className="text-xs text-stone-600">Factory / batch *<input value={form.factory_name} onChange={(event) => setForm((current) => ({ ...current, factory_name: event.target.value }))} placeholder="Factory or batch location" className="mt-1 w-full border border-stone-300 px-3 py-2 text-sm" /></label>
          <label className="text-xs text-stone-600">Batch number<input value={form.batch_number} onChange={(event) => setForm((current) => ({ ...current, batch_number: event.target.value }))} className="mt-1 w-full border border-stone-300 px-3 py-2 text-sm" /></label>
          <label className="text-xs text-stone-600">Production date<input type="date" value={form.produced_at} onChange={(event) => setForm((current) => ({ ...current, produced_at: event.target.value }))} className="mt-1 w-full border border-stone-300 px-3 py-2 text-sm" /></label>
          <label className="text-xs text-stone-600">Notes<input value={form.notes} onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))} className="mt-1 w-full border border-stone-300 px-3 py-2 text-sm" /></label>
        </div>
        <button type="button" onClick={() => void saveProduction()} disabled={saving} className="mt-4 inline-flex items-center gap-2 rounded-lg bg-stone-900 px-4 py-2 text-sm text-white disabled:opacity-60"><Plus size={16} />{saving ? "Saving..." : "Save production entry"}</button>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Recent production entries</h2>
          {productions.length === 0 ? <p className="py-8 text-center text-sm text-stone-500">No production entries recorded.</p> : <ul className="mt-3 divide-y divide-stone-100">{productions.map((entry) => <li key={entry.id} className="py-3 text-sm"><p className="font-medium text-stone-800">{entry.tile_name} · {entry.quantity} units</p><p className="text-xs text-stone-500">{entry.tile_sku} · {entry.factory_name} · {entry.produced_at}{entry.batch_number ? ` · batch ${entry.batch_number}` : ""}</p></li>)}</ul>}
        </div>
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Recent inventory movements</h2>
          {movements.length === 0 ? <p className="py-8 text-center text-sm text-stone-500">No inventory movements recorded.</p> : <ul className="mt-3 divide-y divide-stone-100">{movements.slice(0, 8).map((movement) => <li key={movement.id} className="py-3 text-sm"><p className="font-medium text-stone-800">{movement.movement_type.replaceAll("_", " ")} · {movement.direction > 0 ? "+" : "-"}{movement.quantity} {movement.unit}</p><p className="text-xs text-stone-500">{movement.tile_sku} · balance {movement.balance_after ?? "unavailable"} · {movement.occurred_at ? new Date(movement.occurred_at).toLocaleString() : "date unavailable"}</p></li>)}</ul>}
        </div>
      </section>

      <section className="border border-stone-200 bg-white p-5">
        <h2 className="font-semibold text-stone-900">Stock aging and turnover</h2>
        {data.inventory.stock_aging_and_turnover.available ? (
          <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr className="text-xs uppercase text-stone-500"><th className="py-2">Tile</th><th>Stock</th><th>Age</th><th>Turnover</th></tr></thead><tbody>{data.inventory.stock_aging_and_turnover.items.map((item) => <tr key={item.tile_id} className="border-t border-stone-100"><td className="py-3"><strong>{item.name}</strong><span className="block text-xs text-stone-500">{item.sku}</span></td><td>{item.current_stock}</td><td>{item.stock_age_days == null ? "No receipt recorded" : `${item.stock_age_days} days`}</td><td>{item.turnover.toFixed(2)}x</td></tr>)}</tbody></table></div>
        ) : <p className="mt-2 text-sm text-stone-500">{data.inventory.stock_aging_and_turnover.reason}</p>}
      </section>
    </div>
  );
}

function Metric({ label, value, note, icon: Icon }: { label: string; value: string; note?: string; icon: typeof Boxes }) {
  return <section className="flex items-center justify-between border border-stone-200 bg-white p-5"><div><p className="text-sm text-stone-500">{label}</p><p className="mt-2 text-2xl font-semibold text-stone-900">{value}</p>{note && <p className="mt-1 text-xs text-stone-500">{note}</p>}</div><Icon className="text-stone-400" /></section>;
}

function Conversion({ label, value, rate }: { label: string; value: number; rate?: string }) {
  return <div className="rounded border border-stone-200 p-3"><p className="text-2xl font-semibold text-stone-900">{value}</p><p className="text-xs text-stone-500">{label}</p>{rate && <p className="mt-1 text-xs font-medium text-cyan-800">{rate}</p>}</div>;
}
