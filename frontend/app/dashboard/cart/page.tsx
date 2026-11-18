"use client";
import { useEffect, useState, useCallback } from "react";
import api, { API_BASE_URL } from "@/lib/api";
import OrderSuccessToast from "@/components/OrderSuccessToast";
import { Trash2, Plus, Minus, ShoppingCart, Loader2, PackageX } from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

type CartItem = {
  id: number;
  tile_id: number;
  tile_name: string;
  tile_sku: string;
  tile_image_url: string | null;
  unit_price: number | null;
  subtotal: number | null;
  quantity: number;
  stock_quantity: number | null;
  stock_unit: string;
  is_low_stock: boolean;
};

type Cart = {
  id: number;
  item_count: number;
  estimated_total: number | null;
  items: CartItem[];
};

type StockError = { message: string; errors: string[] };

// ── Component ─────────────────────────────────────────────────────────────────

export default function CartPage() {
  const [cart, setCart]           = useState<Cart | null>(null);
  const [loading, setLoading]     = useState(true);
  const [checkingOut, setCheckingOut] = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [stockErrors, setStockErrors] = useState<string[]>([]);
  const [successOrderId, setSuccessOrderId] = useState<number | null>(null);
  // Track which items are mid-update to show per-item spinners
  const [updatingItems, setUpdatingItems] = useState<Set<number>>(new Set());

  const fetchCart = useCallback(async () => {
    try {
      const res = await api.get("/api/cart");
      setCart(res.data);
    } catch {
      setError("Failed to load cart.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCart();
  }, [fetchCart]);

  // ── Quantity update ──────────────────────────────────────
  const updateQuantity = async (itemId: number, delta: number, currentQty: number) => {
    const newQty = currentQty + delta;
    if (newQty < 1) return removeItem(itemId);

    setUpdatingItems((s) => new Set(s).add(itemId));
    try {
      await api.patch(`/api/cart/item/${itemId}`, { quantity: newQty });
      await fetchCart();
    } catch {
      setError("Could not update quantity.");
    } finally {
      setUpdatingItems((s) => { const n = new Set(s); n.delete(itemId); return n; });
    }
  };

  // ── Remove item ─────────────────────────────────────────
  const removeItem = async (itemId: number) => {
    setUpdatingItems((s) => new Set(s).add(itemId));
    try {
      await api.delete(`/api/cart/item/${itemId}`);
      await fetchCart();
    } catch {
      setError("Could not remove item.");
    } finally {
      setUpdatingItems((s) => { const n = new Set(s); n.delete(itemId); return n; });
    }
  };

  // ── Checkout ────────────────────────────────────────────
  const handleCheckout = async () => {
    setCheckingOut(true);
    setError(null);
    setStockErrors([]);
    try {
      const res = await api.post("/api/cart/checkout");
      setSuccessOrderId(res.data.id);
      await fetchCart(); // cart is now empty
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown } } };
      const detail = e.response?.data?.detail;
      if (detail && typeof detail === "object" && "errors" in detail) {
        const d = detail as StockError;
        setStockErrors(d.errors);
        setError(d.message);
      } else if (typeof detail === "string") {
        setError(detail);
      } else {
        setError("Checkout failed. Please try again.");
      }
    } finally {
      setCheckingOut(false);
    }
  };

  // ── Render helpers ──────────────────────────────────────

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4 text-stone-400">
        <Loader2 size={36} className="animate-spin" />
        <p>Loading cart…</p>
      </div>
    );
  }

  const isEmpty = !cart || cart.items.length === 0;

  return (
    <div className="max-w-4xl mx-auto">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-stone-800 flex items-center gap-2">
          <ShoppingCart size={24} />
          Your Cart
        </h1>
        {!isEmpty && (
          <p className="mt-1 text-sm text-stone-500">
            {cart.item_count} {cart.item_count === 1 ? "item" : "items"} in cart
          </p>
        )}
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-4 rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700">
          <p className="font-semibold mb-1">{error}</p>
          {stockErrors.length > 0 && (
            <ul className="list-disc ml-4 mt-1 space-y-0.5 text-xs">
              {stockErrors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* Empty state */}
      {isEmpty ? (
        <div className="flex flex-col items-center justify-center py-24 text-stone-400 gap-4">
          <PackageX size={52} strokeWidth={1.25} />
          <p className="text-lg font-medium">Your cart is empty</p>
          <p className="text-sm">Search for tiles and add them to your cart.</p>
          <a
            href="/dashboard/search"
            className="mt-2 bg-stone-800 text-white text-sm font-medium px-5 py-2.5 rounded-lg hover:bg-stone-700 transition"
          >
            Start searching
          </a>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Item list */}
          <div className="lg:col-span-2 space-y-3">
            {cart!.items.map((item) => {
              const busy = updatingItems.has(item.id);
              const imageUrl = item.tile_image_url
                ? `${API_BASE_URL}${item.tile_image_url}`
                : null;

              return (
                <div
                  key={item.id}
                  className={`bg-white rounded-xl border border-stone-200 p-4 flex gap-4
                              shadow-sm transition-opacity duration-200
                              ${busy ? "opacity-50 pointer-events-none" : ""}`}
                >
                  {/* Tile thumbnail */}
                  <div className="w-16 h-16 flex-shrink-0 rounded-lg overflow-hidden bg-stone-100 border border-stone-200">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={item.tile_name}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                        }}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-2xl text-stone-300">
                        🪨
                      </div>
                    )}
                  </div>

                  {/* Details */}
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-stone-800 text-sm leading-snug truncate">
                      {item.tile_name}
                    </p>
                    <p className="text-xs text-stone-400 mt-0.5">{item.tile_sku}</p>

                    {/* Stock indicator */}
                    <p className={`text-xs mt-1 ${item.is_low_stock ? "text-amber-600" : "text-stone-400"}`}>
                      {item.stock_quantity !== null
                        ? `${item.stock_quantity} ${item.stock_unit} available${item.is_low_stock ? " ⚠️" : ""}`
                        : "Stock info unavailable"}
                    </p>

                    {/* Quantity controls + price */}
                    <div className="flex items-center justify-between mt-3">
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => updateQuantity(item.id, -1, item.quantity)}
                          className="w-7 h-7 rounded-lg border border-stone-200 flex items-center justify-center
                                     text-stone-600 hover:bg-stone-100 transition"
                          aria-label="Decrease quantity"
                        >
                          <Minus size={13} />
                        </button>
                        <span className="text-sm font-semibold text-stone-700 w-6 text-center">
                          {item.quantity}
                        </span>
                        <button
                          onClick={() => updateQuantity(item.id, 1, item.quantity)}
                          className="w-7 h-7 rounded-lg border border-stone-200 flex items-center justify-center
                                     text-stone-600 hover:bg-stone-100 transition"
                          aria-label="Increase quantity"
                        >
                          <Plus size={13} />
                        </button>
                      </div>

                      <div className="text-right">
                        {item.unit_price != null ? (
                          <>
                            <p className="text-xs text-stone-400">₹{item.unit_price}/sqm</p>
                            <p className="text-sm font-bold text-stone-800">
                              ₹{item.subtotal?.toFixed(2)}
                            </p>
                          </>
                        ) : (
                          <p className="text-xs text-stone-400 italic">Price N/A</p>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Remove button */}
                  <button
                    onClick={() => removeItem(item.id)}
                    className="flex-shrink-0 self-start text-stone-300 hover:text-red-500 transition p-1"
                    aria-label="Remove item"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              );
            })}
          </div>

          {/* Order summary */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl border border-stone-200 shadow-sm p-5 sticky top-6">
              <h2 className="font-semibold text-stone-800 mb-4">Order Summary</h2>

              <div className="space-y-2 text-sm text-stone-600 border-b border-stone-100 pb-4 mb-4">
                <div className="flex justify-between">
                  <span>Items</span>
                  <span>{cart!.item_count}</span>
                </div>
                <div className="flex justify-between font-semibold text-stone-800">
                  <span>Estimated Total</span>
                  <span>
                    {cart!.estimated_total != null
                      ? `₹${cart!.estimated_total.toFixed(2)}`
                      : "—"}
                  </span>
                </div>
              </div>

              {cart!.estimated_total == null && (
                <p className="text-xs text-stone-400 mb-4 italic">
                  Some items don't have a listed price — total is indicative.
                </p>
              )}

              <button
                onClick={handleCheckout}
                disabled={checkingOut}
                className="w-full bg-gradient-to-r from-emerald-600 to-teal-600
                           text-white font-semibold py-3 rounded-xl text-sm
                           hover:from-emerald-500 hover:to-teal-500
                           active:scale-[0.98] transition-all duration-200
                           disabled:opacity-50 disabled:cursor-not-allowed
                           flex items-center justify-center gap-2"
              >
                {checkingOut ? (
                  <><Loader2 size={16} className="animate-spin" /> Processing…</>
                ) : (
                  "Place Order"
                )}
              </button>

              <p className="text-xs text-stone-400 text-center mt-3">
                Mock checkout — no payment required.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Success toast */}
      {successOrderId !== null && (
        <OrderSuccessToast
          orderId={successOrderId}
          onClose={() => setSuccessOrderId(null)}
        />
      )}
    </div>
  );
}
