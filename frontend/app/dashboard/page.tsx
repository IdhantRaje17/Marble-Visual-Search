"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Boxes, Loader2, Package, Search, ShoppingBag } from "lucide-react";
import api from "@/lib/api";

type TrendPoint = { date: string; count: number };
type Analytics = {
  date_range: { start_date: string; end_date: string };
  catalog: { total: number; active: number; inactive: number };
  searches: {
    total: number;
    trend: TrendPoint[];
    recent: { id: number; status: string; searched_at: string | null; tile_name: string | null }[];
  };
  orders: {
    total: number;
    status_counts: Record<string, number>;
    completed: number;
    units_sold: number;
    revenue: number;
    average_order_value: number | null;
    revenue_available: boolean;
    conversion_rate: number | null;
    conversion_available: boolean;
    trend: TrendPoint[];
    recent: { id: number; status: string; total_amount: number | null; placed_at: string | null; account_email: string }[];
    best_sellers: { tile_id: number; sku: string; name: string; units_sold: number }[];
  };
  inventory: {
    records: number;
    not_configured_products: number;
    quantity_total: number;
    out_of_stock: number;
    low_stock: number;
    in_stock: number;
  };
};

const localDate = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

function Metric({ label, value, note, icon: Icon }: {
  label: string;
  value: string | number;
  note?: string;
  icon: typeof Boxes;
}) {
  return (
    <section className="border-l-2 border-stone-300 bg-white px-4 py-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-stone-500">{label}</p>
        <Icon size={17} className="text-stone-400" aria-hidden="true" />
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-stone-900">{value}</p>
      {note && <p className="mt-1 text-xs text-stone-500">{note}</p>}
    </section>
  );
}

function TrendChart({ title, points }: { title: string; points: TrendPoint[] }) {
  const peak = Math.max(1, ...points.map((point) => point.count));
  return (
    <section className="border border-stone-200 bg-white p-5">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="font-semibold text-stone-800">{title}</h2>
        <span className="text-xs text-stone-400">Daily count</span>
      </div>
      {points.length === 0 ? (
        <p className="py-8 text-center text-sm text-stone-500">No activity in this date range.</p>
      ) : (
        <div className="flex h-36 items-end gap-1 border-b border-stone-200 px-1">
          {points.map((point) => (
            <div key={point.date} className="group relative flex h-full min-w-1 flex-1 items-end" title={`${point.date}: ${point.count}`}>
              <div className="w-full bg-cyan-700 transition-colors group-hover:bg-cyan-500" style={{ height: `${Math.max(4, (point.count / peak) * 100)}%` }} />
              <span className="pointer-events-none absolute -top-7 left-1/2 hidden -translate-x-1/2 whitespace-nowrap bg-stone-900 px-2 py-1 text-xs text-white group-hover:block">
                {point.date}: {point.count}
              </span>
            </div>
          ))}
        </div>
      )}
      {points.length > 0 && <div className="mt-2 flex justify-between text-[11px] text-stone-400"><span>{points[0].date}</span><span>{points[points.length - 1].date}</span></div>}
    </section>
  );
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "Date unavailable";
}

export default function DashboardPage() {
  const [rangeDays, setRangeDays] = useState(30);
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const end = new Date();
    const start = new Date(end);
    start.setDate(start.getDate() - rangeDays + 1);
    api.get<Analytics>("/api/admin/analytics", {
      params: { start_date: localDate(start), end_date: localDate(end) },
    }).then((response) => {
      if (!cancelled) setData(response.data);
    }).catch(() => {
      if (!cancelled) setError("Dashboard analytics could not be loaded.");
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [rangeDays]);

  if (loading && !data) {
    return <div className="flex min-h-64 items-center justify-center gap-3 text-stone-500" aria-live="polite"><Loader2 className="animate-spin" size={20} /> Loading business analytics...</div>;
  }
  if (!data) {
    return <div className="max-w-3xl"><h1 className="text-2xl font-semibold text-stone-900">Business dashboard</h1><p role="alert" className="mt-4 border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error || "Dashboard data is unavailable."}</p></div>;
  }

  return (
    <div className="mx-auto max-w-7xl space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-4 border-b border-stone-200 pb-5">
        <div><p className="text-xs font-semibold uppercase text-cyan-800">Operations overview</p><h1 className="mt-1 text-2xl font-semibold text-stone-900">Business dashboard</h1><p className="mt-1 text-sm text-stone-500">{data.date_range.start_date} through {data.date_range.end_date}</p></div>
        <label className="flex items-center gap-2 text-sm text-stone-600">Date range
          <select value={rangeDays} onChange={(event) => { setLoading(true); setError(""); setRangeDays(Number(event.target.value)); }} className="border border-stone-300 bg-white px-3 py-2 text-stone-800 focus:outline-none focus:ring-2 focus:ring-cyan-700">
            <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
          </select>
        </label>
      </header>

      {loading && <p className="text-xs text-stone-500" aria-live="polite">Updating date range...</p>}
      {error && <p role="alert" className="border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error} Showing the last successfully loaded data.</p>}
      <section aria-label="Catalog metrics" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Catalog products" value={data.catalog.total} note={`${data.catalog.active} active · ${data.catalog.inactive} inactive`} icon={Boxes} />
        <Metric label="Searches" value={data.searches.total} note="In selected date range" icon={Search} />
        <Metric label="Orders placed" value={data.orders.total} note={Object.entries(data.orders.status_counts).map(([status, count]) => `${count} ${status}`).join(" · ") || "No orders in range"} icon={ShoppingBag} />
        <Metric label="Inventory units" value={data.inventory.quantity_total.toLocaleString()} note={`${data.inventory.records} configured products`} icon={Package} />
      </section>

      <section aria-label="Sales metrics" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Completed orders" value={data.orders.completed} note="Paid or completed status only" icon={ShoppingBag} />
        <Metric label="Units sold" value={data.orders.units_sold.toLocaleString()} note="Completed orders only" icon={Boxes} />
        <Metric label="Revenue" value={data.orders.revenue_available ? data.orders.revenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "Unavailable"} note={data.orders.revenue_available ? "Stored order amounts · completed only" : "No completed orders in this range"} icon={Activity} />
        <Metric label="Average order value" value={data.orders.average_order_value === null ? "Unavailable" : data.orders.average_order_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} note="Completed orders with a stored total" icon={Activity} />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2"><TrendChart title="Search activity" points={data.searches.trend} /><TrendChart title="Orders placed" points={data.orders.trend} /></section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div className="border border-stone-200 bg-white p-5"><h2 className="font-semibold text-stone-800">Stock distribution</h2><div className="mt-4 space-y-3 text-sm">
          <div className="flex justify-between"><span className="text-emerald-800">In stock</span><strong>{data.inventory.in_stock}</strong></div>
          <div className="flex justify-between"><span className="text-amber-800">Low stock</span><strong>{data.inventory.low_stock}</strong></div>
          <div className="flex justify-between"><span className="text-red-800">Out of stock</span><strong>{data.inventory.out_of_stock}</strong></div>
          <div className="flex justify-between border-t border-stone-100 pt-3"><span className="text-stone-500">Not configured</span><strong>{data.inventory.not_configured_products}</strong></div>
        </div></div>
        <div className="border border-stone-200 bg-white p-5 xl:col-span-2"><h2 className="font-semibold text-stone-800">Best sellers</h2>
          {data.orders.best_sellers.length === 0 ? <p className="py-8 text-center text-sm text-stone-500">No completed-order sales recorded in this date range.</p> : <div className="mt-3 divide-y divide-stone-100">{data.orders.best_sellers.map((tile) => <div key={tile.tile_id} className="flex items-center justify-between gap-4 py-3 text-sm"><div><p className="font-medium text-stone-800">{tile.name}</p><p className="text-xs text-stone-500">{tile.sku}</p></div><span className="tabular-nums text-stone-700">{tile.units_sold} units</span></div>)}</div>}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="border border-stone-200 bg-white p-5"><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold text-stone-800">Recent orders</h2><span className="text-xs text-stone-500">{data.orders.recent.length} shown</span></div>
          {data.orders.recent.length === 0 ? <p className="py-7 text-center text-sm text-stone-500">No orders in this date range.</p> : <div className="divide-y divide-stone-100">{data.orders.recent.map((order) => <div key={order.id} className="flex flex-wrap justify-between gap-2 py-3 text-sm"><div><p className="font-medium text-stone-800">Order #{order.id} · {order.status}</p><p className="text-xs text-stone-500">{order.account_email}</p></div><div className="text-right"><p className="text-stone-700">{order.total_amount === null ? "Amount unavailable" : order.total_amount.toLocaleString()}</p><p className="text-xs text-stone-500">{formatDate(order.placed_at)}</p></div></div>)}</div>}
        </div>
        <div className="border border-stone-200 bg-white p-5"><div className="mb-3 flex items-center justify-between"><h2 className="font-semibold text-stone-800">Recent search activity</h2><Link href="/dashboard/history" className="text-sm text-cyan-800 hover:underline">Search history</Link></div>
          {data.searches.recent.length === 0 ? <p className="py-7 text-center text-sm text-stone-500">No searches in this date range.</p> : <div className="divide-y divide-stone-100">{data.searches.recent.map((search) => <div key={search.id} className="flex flex-wrap justify-between gap-2 py-3 text-sm"><div><p className="font-medium capitalize text-stone-800">{(search.status || "search").replaceAll("_", " ")}</p><p className="text-xs text-stone-500">{search.tile_name || "No matched product"}</p></div><p className="text-xs text-stone-500">{formatDate(search.searched_at)}</p></div>)}</div>}
        </div>
      </section>
    </div>
  );
}