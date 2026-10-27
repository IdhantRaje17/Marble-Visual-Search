"use client";

import { useEffect, useState } from "react";
import { Activity, Boxes, Loader2, Package } from "lucide-react";
import api from "@/lib/api";
import { type Analytics, formatInr, rangeParams } from "@/lib/analytics";

export default function FactoryAnalyticsPage() {
  const [rangeDays, setRangeDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api.get<Analytics>("/api/admin/analytics", { params: rangeParams(rangeDays) })
      .then(({ data: response }) => {
        if (!cancelled) {
          setData(response);
          setError("");
        }
      })
      .catch(() => {
        if (!cancelled) setError("Factory analytics could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [rangeDays]);

  if (error && !data) return <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">{error}</p>;
  if (!data) return <div className="flex min-h-64 items-center justify-center gap-2 text-stone-500"><Loader2 className="animate-spin" /> Loading factory analytics...</div>;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase text-cyan-800">Real database values</p>
          <h1 className="mt-1 text-2xl font-semibold text-stone-900">Factory Analytics</h1>
          <p className="mt-1 text-sm text-stone-500">{data.date_range.start_date} through {data.date_range.end_date}</p>
          <p className="mt-2 max-w-3xl text-xs text-stone-500">{data.definitions.sales}</p>
        </div>
        <label className="text-sm text-stone-600">Date range
          <select value={rangeDays} onChange={(event) => setRangeDays(Number(event.target.value))} className="ml-2 border border-stone-300 bg-white px-3 py-2">
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
          </select>
        </label>
      </header>
      {loading && <p className="text-xs text-stone-500">Updating date range...</p>}
      <section className="grid gap-4 sm:grid-cols-3">
        <Metric label="Completed units sold" value={data.orders.units_sold.toLocaleString()} note={data.orders.completed === 0 ? "Zero completed sales" : undefined} icon={Boxes} />
        <Metric label="Completed-order revenue" value={formatInr(data.orders.revenue, data.orders.revenue_available)} note={data.orders.revenue_reason} icon={Activity} />
        <Metric label="Current inventory units" value={data.inventory.quantity_total.toLocaleString()} note="Not filtered by date" icon={Package} />
      </section>
      <section className="grid gap-4 lg:grid-cols-2">
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Trending by visual searches</h2>
          <p className="mt-1 text-xs text-stone-500">{data.definitions.visual_search_popularity}</p>
          {data.orders.top_searched_tiles.length === 0 ? <p className="py-6 text-sm text-stone-500">No matched tile searches recorded in this date range.</p> : <ul className="mt-3 divide-y divide-stone-100">{data.orders.top_searched_tiles.map((tile) => <li key={tile.tile_id} className="flex justify-between gap-3 py-3 text-sm"><span><strong className="block text-stone-800">{tile.name}</strong><span className="text-xs text-stone-500">{tile.sku}</span></span><span className="text-stone-700">{tile.searches} searches</span></li>)}</ul>}
        </div>
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Top-selling tiles</h2>
          <p className="mt-1 text-xs text-stone-500">Completed-order quantity and revenue</p>
          {data.orders.best_sellers.length === 0 ? <p className="py-6 text-sm text-stone-500">Zero completed-order sales in this date range.</p> : <ul className="mt-3 divide-y divide-stone-100">{data.orders.best_sellers.map((tile, index) => <li key={`${tile.tile_id ?? tile.sku}-${index}`} className="flex justify-between gap-3 py-3 text-sm"><span><strong className="block text-stone-800">{tile.name}</strong><span className="text-xs text-stone-500">{tile.sku}</span></span><span className="text-right text-stone-700">{tile.units_sold} units<p className="text-xs">{tile.revenue_available ? formatInr(tile.revenue) : "Revenue unavailable"}</p></span></li>)}</ul>}
        </div>
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Top buyers</h2>
          {data.orders.top_buyers.length === 0 ? <p className="py-6 text-sm text-stone-500">No completed orders recorded.</p> : <ul className="mt-3 divide-y divide-stone-100">{data.orders.top_buyers.map((buyer) => <li key={buyer.account_id} className="flex justify-between gap-3 py-3 text-sm"><span><strong className="block text-stone-800">{buyer.name}</strong><span className="text-xs text-stone-500">{buyer.email} · {buyer.completed_orders} orders</span></span><span className="text-stone-700">{buyer.revenue_available ? formatInr(buyer.revenue) : "Revenue unavailable"}</span></li>)}</ul>}
        </div>
        <div className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-900">Stock distribution</h2>
          <p className="mt-1 text-xs text-stone-500">{data.definitions.inventory}</p>
          <div className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between"><span className="text-emerald-800">In stock</span><strong>{data.inventory.in_stock}</strong></div>
            <div className="flex justify-between"><span className="text-amber-800">Low stock</span><strong>{data.inventory.low_stock}</strong></div>
            <div className="flex justify-between"><span className="text-red-800">Out of stock</span><strong>{data.inventory.out_of_stock}</strong></div>
            <div className="flex justify-between border-t border-stone-100 pt-3"><span className="text-stone-500">Not configured</span><strong>{data.inventory.not_configured_products}</strong></div>
          </div>
        </div>
      </section>
      <section className="border border-amber-200 bg-amber-50 p-5">
        <h2 className="font-semibold text-amber-950">Low-stock alerts</h2>
        {data.inventory.low_stock_items.length === 0 ? <p className="mt-2 text-sm text-amber-900">No configured products are at or below their stock thresholds.</p> : <ul className="mt-3 grid gap-2 sm:grid-cols-2">{data.inventory.low_stock_items.map((tile) => <li key={tile.tile_id} className="bg-white/70 p-3 text-sm"><p className="font-medium text-stone-800">{tile.name}</p><p className="text-xs text-stone-600">{tile.sku} · {tile.quantity} on hand / {tile.threshold} threshold</p></li>)}</ul>}
      </section>
      <section className="grid gap-4 lg:grid-cols-3">
        <Unavailable label="Production vs sales" reason={data.orders.production_vs_sales.reason} />
        <Unavailable label="Search → quotation → order conversion" reason={data.orders.search_to_quotation_to_order.reason} />
        <Unavailable label="Stock aging / turnover" reason={data.inventory.stock_aging_and_turnover.reason} />
      </section>
    </div>
  );
}

function Metric({ label, value, note, icon: Icon }: { label: string; value: string; note?: string; icon: typeof Boxes }) {
  return (
    <section className="flex items-center justify-between border border-stone-200 bg-white p-5">
      <div>
        <p className="text-sm text-stone-500">{label}</p>
        <p className="mt-2 text-2xl font-semibold text-stone-900">{value}</p>
        {note && <p className="mt-1 text-xs text-stone-500">{note}</p>}
      </div>
      <Icon className="text-stone-400" />
    </section>
  );
}

function Unavailable({ label, reason }: { label: string; reason: string }) {
  return <section className="border border-dashed border-stone-300 bg-stone-50 p-4"><h2 className="font-medium text-stone-800">{label}</h2><p className="mt-2 text-sm text-stone-600">Unavailable</p><p className="mt-1 text-xs text-stone-500">{reason}</p></section>;
}
