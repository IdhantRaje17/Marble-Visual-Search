"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Truck } from "lucide-react";
import api from "@/lib/api";
import { type Analytics, formatInr, rangeParams } from "@/lib/analytics";

type TrackedOrder = {
  id: number;
  status: string;
  total_amount: number | null;
  placed_at: string | null;
  buyer_name: string;
  buyer_email: string;
  shipment_details: { tracking_number: string | null; carrier: string | null } | null;
  dispatched_at: string | null;
  delivered_at: string | null;
  expected_delivery_at: string | null;
  delay_seconds: number | null;
  known_statuses?: string[];
  timeline: { status: string; timestamp: string | null }[];
  items: { tile_id: number | null; tile_name: string; tile_sku: string; quantity: number; unit_price: number | null; current_stock: number | null }[];
};

const DEFAULT_STATUSES = ["placed", "paid", "dispatched", "completed", "delivered", "cancelled"];

export default function OrderTrackingPage() {
  const [orders, setOrders] = useState<TrackedOrder[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [status, setStatus] = useState("");
  const [rangeDays, setRangeDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editingOrderId, setEditingOrderId] = useState<number | null>(null);
  const [trackingForm, setTrackingForm] = useState({
    status: "", tracking_number: "", carrier: "", dispatched_at: "", delivered_at: "", expected_delivery_at: "",
  });

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.all([
      api.get<TrackedOrder[]>("/api/admin/orders", { params: status ? { status } : {} }),
      api.get<Analytics>("/api/admin/analytics", { params: rangeParams(rangeDays) }),
    ]).then(([orderResponse, analyticsResponse]) => {
      if (!active) return;
      setOrders(orderResponse.data);
      setAnalytics(analyticsResponse.data);
      setError("");
    }).catch(() => {
      if (active) setError("Order tracking data could not be loaded.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [status, rangeDays]);

  const statusOptions = useMemo(() => {
    const fromOrders = orders.flatMap((order) => [
      order.status,
      ...(order.known_statuses ?? []),
      ...order.timeline.map((event) => event.status),
    ]);
    return Array.from(new Set([...DEFAULT_STATUSES, ...fromOrders].filter(Boolean))).sort();
  }, [orders]);

  const editTracking = (order: TrackedOrder) => {
    const dateInput = (value: string | null) => value ? new Date(value).toISOString().slice(0, 16) : "";
    setTrackingForm({
      status: order.status,
      tracking_number: order.shipment_details?.tracking_number ?? "",
      carrier: order.shipment_details?.carrier ?? "",
      dispatched_at: dateInput(order.dispatched_at),
      delivered_at: dateInput(order.delivered_at),
      expected_delivery_at: dateInput(order.expected_delivery_at),
    });
    setEditingOrderId(order.id);
  };

  const saveTracking = async (orderId: number) => {
    const payload = {
      status: trackingForm.status,
      tracking_number: trackingForm.tracking_number || null,
      carrier: trackingForm.carrier || null,
      dispatched_at: trackingForm.dispatched_at ? new Date(trackingForm.dispatched_at).toISOString() : null,
      delivered_at: trackingForm.delivered_at ? new Date(trackingForm.delivered_at).toISOString() : null,
      expected_delivery_at: trackingForm.expected_delivery_at ? new Date(trackingForm.expected_delivery_at).toISOString() : null,
    };
    try {
      await api.patch(`/api/admin/orders/${orderId}/tracking`, payload);
      const { data } = await api.get<TrackedOrder[]>("/api/admin/orders", { params: status ? { status } : {} });
      setOrders(data);
      setEditingOrderId(null);
      setError("");
    } catch {
      setError("Order tracking details could not be saved.");
    }
  };

  const revenueTrendPeak = Math.max(1, ...(analytics?.orders.revenue_trend.map((point) => point.amount ?? 0) ?? [1]));
  const orderTrendPeak = Math.max(1, ...(analytics?.orders.trend.map((entry) => entry.count) ?? [1]));

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <Truck className="text-cyan-700" />
          <div>
            <h1 className="text-2xl font-semibold text-stone-900">Order Tracking &amp; Analytics</h1>
            <p className="mt-1 text-sm text-stone-500">Status history and shipment dates from the database</p>
            {analytics && <p className="mt-1 max-w-2xl text-xs text-stone-500">{analytics.definitions.sales}</p>}
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <label className="text-sm text-stone-600">Sales date range
            <select value={rangeDays} onChange={(event) => setRangeDays(Number(event.target.value))} className="ml-2 border border-stone-300 bg-white px-3 py-2">
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </select>
          </label>
          <label className="text-sm text-stone-600">Status
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="ml-2 border border-stone-300 bg-white px-3 py-2">
              <option value="">All statuses</option>
              {statusOptions.map((value) => <option key={value} value={value}>{value}</option>)}
            </select>
          </label>
        </div>
      </header>
      {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {analytics && (
        <section className="grid gap-3 sm:grid-cols-4">
          <Metric label="Completed orders" value={analytics.orders.completed.toLocaleString()} />
          <Metric label="Units sold" value={analytics.orders.units_sold.toLocaleString()} />
          <Metric label="Completed-order revenue" value={formatInr(analytics.orders.revenue, analytics.orders.revenue_available)} />
          <Metric label="Average order value" value={analytics.orders.completed === 0 ? "Not applicable" : formatInr(analytics.orders.average_order_value, analytics.orders.aov_available)} />
        </section>
      )}
      {analytics && (
        <section className="border border-stone-200 bg-white p-5">
          <h2 className="font-semibold text-stone-800">Daily orders placed · {analytics.date_range.start_date} to {analytics.date_range.end_date}</h2>
          <div className="mt-4 flex h-28 items-end gap-1">
            {analytics.orders.trend.map((point) => (
              <div key={point.date} title={`${point.date}: ${point.count}`} className="flex-1 bg-cyan-700" style={{ height: `${Math.max(4, point.count / orderTrendPeak * 100)}%` }} />
            ))}
          </div>
        </section>
      )}
      {analytics && (
        <section className="grid gap-4 lg:grid-cols-2">
          <div className="border border-stone-200 bg-white p-5">
            <h2 className="font-semibold text-stone-800">Recorded revenue trend · completed orders</h2>
            <div className="mt-4 flex h-28 items-end gap-1">
              {analytics.orders.revenue_trend.map((point) => (
                <div
                  key={point.date}
                  title={point.complete ? `${point.date}: ${formatInr(point.amount ?? 0)}` : `${point.date}: unavailable`}
                  className={point.complete ? "flex-1 bg-emerald-700" : "flex-1 bg-stone-200"}
                  style={{ height: point.complete ? `${Math.max(4, (point.amount ?? 0) / revenueTrendPeak * 100)}%` : "8%" }}
                />
              ))}
            </div>
          </div>
          <div className="border border-stone-200 bg-white p-5">
            <h2 className="font-semibold text-stone-800">Popular tiles · completed orders</h2>
            {analytics.orders.best_sellers.length === 0 ? <p className="py-6 text-sm text-stone-500">Zero completed-order tile sales in this date range.</p> : <ul className="mt-3 divide-y divide-stone-100">{analytics.orders.best_sellers.map((tile, index) => <li key={`${tile.tile_id ?? tile.sku}-${index}`} className="flex justify-between gap-3 py-2 text-sm"><span>{tile.name} <span className="text-xs text-stone-500">{tile.sku}</span></span><span className="text-right">{tile.units_sold} units<p className="text-xs">{tile.revenue_available ? formatInr(tile.revenue) : "Revenue unavailable"}</p></span></li>)}</ul>}
          </div>
        </section>
      )}
      {loading ? (
        <div className="flex justify-center gap-2 py-12 text-stone-500"><Loader2 className="animate-spin" /> Loading orders...</div>
      ) : orders.length === 0 ? (
        <p className="py-12 text-center text-stone-500">No orders match this status.</p>
      ) : (
        <section className="space-y-3">
          {orders.map((order) => (
            <article key={order.id} className="border border-stone-200 bg-white p-5">
              <div className="flex flex-wrap justify-between gap-3">
                <div><h2 className="font-semibold text-stone-900">Order #{order.id} · <span className="capitalize">{order.status.replaceAll("_", " ")}</span></h2><p className="mt-1 text-sm text-stone-500">{order.buyer_name} · {order.buyer_email}</p></div>
                <div className="text-right text-sm text-stone-600"><p>{order.placed_at ? `Placed ${new Date(order.placed_at).toLocaleString()}` : "Placed date unavailable"}</p><p className="mt-1 font-medium">{formatInr(order.total_amount, order.total_amount != null)}</p></div>
              </div>
              <div className="mt-4 space-y-1 border-l-2 border-cyan-700 pl-3 text-sm">
                <p className="font-medium text-stone-800">Placed · {order.placed_at ? new Date(order.placed_at).toLocaleString() : "date unavailable"}</p>
                {order.timeline.map((event, index) => <p key={`${event.status}-${index}`} className="capitalize text-stone-700">{event.status.replaceAll("_", " ")} · {event.timestamp ? new Date(event.timestamp).toLocaleString() : "date unavailable"}</p>)}
                {order.dispatched_at && <p className="text-stone-700">Dispatched · {new Date(order.dispatched_at).toLocaleString()}</p>}
                {order.delivered_at && <p className="text-stone-700">Delivered · {new Date(order.delivered_at).toLocaleString()}</p>}
                <p className="text-stone-700">
                  {order.delay_seconds === null
                    ? "Delay: unavailable because no expected delivery date is recorded."
                    : order.delay_seconds > 0
                      ? `Delayed by ${Math.floor(order.delay_seconds / 3600)} hours`
                      : order.delivered_at ? "Delivered on time" : "No delay as of now"}
                  {order.expected_delivery_at && ` · expected ${new Date(order.expected_delivery_at).toLocaleString()}`}
                </p>
                <p className="text-stone-600">Current status: {order.status}</p>
              </div>
              <ul className="mt-3 divide-y divide-stone-100">{order.items.map((item, index) => <li key={`${item.tile_id ?? item.tile_sku}-${index}`} className="py-2 text-sm text-stone-700">{item.tile_name} ({item.tile_sku}) · {item.quantity} ordered · {item.unit_price == null ? "line price unavailable" : formatInr(item.unit_price)} · current stock {item.current_stock ?? "unavailable"}</li>)}</ul>
              <p className="mt-3 text-xs text-stone-600">Carrier: {order.shipment_details?.carrier || "Not specified"} · Tracking number: {order.shipment_details?.tracking_number || "Not specified"}</p>
              <button type="button" onClick={() => editTracking(order)} className="mt-3 rounded-lg border border-stone-300 px-3 py-2 text-sm font-medium text-stone-700 hover:bg-stone-50">Update status / shipment</button>
              {editingOrderId === order.id && (
                <form onSubmit={(event) => { event.preventDefault(); void saveTracking(order.id); }} className="mt-4 grid gap-3 border-t border-stone-100 pt-4 sm:grid-cols-2">
                  <label className="text-xs text-stone-600">Status
                    <select required value={trackingForm.status} onChange={(event) => setTrackingForm((current) => ({ ...current, status: event.target.value }))} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm">
                      {statusOptions.map((value) => <option key={value} value={value}>{value}</option>)}
                    </select>
                  </label>
                  <label className="text-xs text-stone-600">Carrier<input value={trackingForm.carrier} onChange={(event) => setTrackingForm((current) => ({ ...current, carrier: event.target.value }))} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm" /></label>
                  <label className="text-xs text-stone-600">Tracking number<input value={trackingForm.tracking_number} onChange={(event) => setTrackingForm((current) => ({ ...current, tracking_number: event.target.value }))} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm" /></label>
                  <label className="text-xs text-stone-600">Dispatch date<input type="datetime-local" value={trackingForm.dispatched_at} onChange={(event) => setTrackingForm((current) => ({ ...current, dispatched_at: event.target.value }))} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm" /></label>
                  <label className="text-xs text-stone-600">Delivery date<input type="datetime-local" value={trackingForm.delivered_at} onChange={(event) => setTrackingForm((current) => ({ ...current, delivered_at: event.target.value }))} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm" /></label>
                  <label className="text-xs text-stone-600">Expected delivery<input type="datetime-local" value={trackingForm.expected_delivery_at} onChange={(event) => setTrackingForm((current) => ({ ...current, expected_delivery_at: event.target.value }))} className="mt-1 w-full rounded border border-stone-300 px-3 py-2 text-sm" /></label>
                  <div className="flex items-end gap-2"><button type="submit" className="rounded-lg bg-stone-800 px-4 py-2 text-sm font-medium text-white">Save tracking</button><button type="button" onClick={() => setEditingOrderId(null)} className="rounded-lg border border-stone-300 px-4 py-2 text-sm">Cancel</button></div>
                </form>
              )}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return <section className="border border-stone-200 bg-white p-4"><p className="text-sm text-stone-500">{label}</p><p className="mt-2 text-xl font-semibold text-stone-900">{value}</p></section>;
}
