"use client";
import { useEffect, useState } from "react";
import { CheckCircle2, X } from "lucide-react";

interface OrderSuccessToastProps {
  orderId: number;
  onClose: () => void;
}

export default function OrderSuccessToast({ orderId, onClose }: OrderSuccessToastProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Trigger enter animation on mount
    const enterTimer = setTimeout(() => setVisible(true), 10);
    // Auto-dismiss after 4s
    const exitTimer = setTimeout(() => {
      setVisible(false);
      setTimeout(onClose, 350); // wait for exit animation
    }, 4000);
    return () => {
      clearTimeout(enterTimer);
      clearTimeout(exitTimer);
    };
  }, [onClose]);

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-start gap-3
                  bg-white border border-emerald-200 rounded-2xl shadow-2xl
                  p-4 max-w-sm w-full
                  transition-all duration-350 ease-out
                  ${visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"}`}
    >
      <div className="flex-shrink-0 mt-0.5">
        <CheckCircle2 size={22} className="text-emerald-500" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold text-stone-800 text-sm">Order placed successfully!</p>
        <p className="text-stone-500 text-xs mt-0.5">
          Order #{orderId} has been confirmed.
        </p>
      </div>
      <button
        onClick={() => {
          setVisible(false);
          setTimeout(onClose, 350);
        }}
        className="flex-shrink-0 text-stone-400 hover:text-stone-600 transition"
        aria-label="Dismiss"
      >
        <X size={16} />
      </button>
    </div>
  );
}
