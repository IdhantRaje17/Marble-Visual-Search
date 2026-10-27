"use client";

import { useEffect, useState } from "react";
import { ClipboardList, Loader2 } from "lucide-react";
import api from "@/lib/api";

type OrderItem = {
  tile_id: number | null;
  tile_name: string;
  tile_sku: string;
  quantity: number;
  unit_price: number | null;
  subtotal: number | null;
};

type CustomerOrder = {
  id: number;
  status: string;
  total_amount: number | null;
  placed_at: string | null;
  shipment: { tracking_number: string | null; carrier: string | null; dispatched_at: string | null; delivered_at: string | null; expected_delivery_at: string | null } | null;
  timeline: { status: string; timestamp: string | null }[];
  items: OrderItem[];
};

const money = (value: number | null) =>
  value == null
    ? "Not available"
    : `₹${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function MyOrdersPage() {
  const [orders, setOrders] = useState<CustomerOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get<CustomerOrder[]>("/api/cart/orders/mine")
      .then(({ data }) => setOrders(data))
      .catch(() => setError("Your orders could not be loaded. Please try again."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex items-center gap-3">
        <ClipboardList className="text-cyan-700" />
        <div>
          <h1 className="text-2xl font-bold text-stone-900">My Orders</h1>
          <p className="text-sm text-stone-500">Orders placed from your account</p>
        </div>
      </header>
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-stone-500"><Loader2 className="animate-spin" /> Loading your orders...</div>
      ) : orders.length === 0 ? (
        <p className="rounded-xl border border-stone-200 bg-white py-16 text-center text-stone-500">You have no orders yet.</p>
      ) : (
        <div className="space-y-4">
          {orders.map((order) => (
            <article key={order.id} className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-stone-100 pb-4">
                <div>
                  <h2 className="font-semibold text-stone-900">Order #{order.id}</h2>
                  <p className="mt-1 text-sm text-stone-500">{order.placed_at ? new Date(order.placed_at).toLocaleString() : "Date unavailable"}</p>
                </div>
                <div className="text-right">
                  <span className="inline-block rounded-full bg-cyan-50 px-3 py-1 text-xs font-semibold capitalize text-cyan-800">{order.status.replaceAll("_", " ")}</span>
                  <p className="mt-2 font-semibold text-stone-900">{money(order.total_amount)}</p>
                </div>
              </div>
              <ul className="divide-y divide-stone-100">
                {order.items.map((item, index) => (
                  <li key={`${item.tile_id ?? item.tile_sku}-${index}`} className="flex flex-wrap justify-between gap-2 py-3 text-sm">
                    <div><p className="font-medium text-stone-800">{item.tile_name}</p><p className="text-xs text-stone-500">{item.tile_sku} · Quantity {item.quantity}</p></div>
                    <p className="text-stone-700">{money(item.subtotal)}</p>
                  </li>
                ))}
              </ul>
              <div className="border-t border-stone-100 pt-3 text-xs text-stone-600">
                {order.shipment ? (
                  <div className="space-y-1">
                    <p>Carrier: {order.shipment.carrier || "Not specified"} · Tracking: {order.shipment.tracking_number || "Not specified"}</p>
                    <p>Dispatched: {order.shipment.dispatched_at ? new Date(order.shipment.dispatched_at).toLocaleString() : "Not recorded"} · Delivered: {order.shipment.delivered_at ? new Date(order.shipment.delivered_at).toLocaleString() : "Not recorded"}</p>
                    <p>Expected delivery: {order.shipment.expected_delivery_at ? new Date(order.shipment.expected_delivery_at).toLocaleString() : "Not recorded"}</p>
                  </div>
                ) : <p>Shipment and tracking details have not been recorded.</p>}
                {order.timeline.length > 0 && <ul className="mt-2 space-y-1">{order.timeline.map((event, index) => <li key={`${event.status}-${index}`} className="capitalize">{event.status.replaceAll("_", " ")} · {event.timestamp ? new Date(event.timestamp).toLocaleString() : "date unavailable"}</li>)}</ul>}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
