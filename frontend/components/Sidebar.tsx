"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Search, Package, LayoutDashboard, LogOut, Boxes, History, ShoppingCart, Users } from "lucide-react";
import { type AccountRole, removeToken } from "@/lib/auth";
import api from "@/lib/api";
import { useState, useEffect } from "react";

const sharedLinks = [
  { href: "/dashboard/search",  label: "Search Tile",    icon: Search },
  { href: "/dashboard/history", label: "Search History", icon: History },
  { href: "/dashboard/cart",    label: "Cart",           icon: ShoppingCart },
];

const adminLinks = [
  { href: "/dashboard",           label: "Dashboard", icon: LayoutDashboard },
  { href: "/dashboard/tiles",     label: "Catalog",   icon: Boxes },
  { href: "/dashboard/inventory", label: "Inventory", icon: Package },
];

export default function Sidebar({ role }: { role: AccountRole }) {
  const pathname = usePathname();
  const router   = useRouter();
  const [cartCount, setCartCount] = useState(0);
  const links = role === "user"
    ? sharedLinks
    : [
        ...adminLinks,
        ...(role === "super_admin"
          ? [{ href: "/dashboard/users", label: "User Management", icon: Users }]
          : []),
        ...sharedLinks,
      ];

  // Refresh cart badge on every navigation
  useEffect(() => {
    let cancelled = false;
    api.get("/api/cart")
      .then((res) => { if (!cancelled) setCartCount(res.data.item_count ?? 0); })
      .catch(() => {/* silently ignore — badge just won't show */});
    return () => { cancelled = true; };
  }, [pathname]);

  const handleLogout = async () => {
    try { await api.post("/api/auth/logout"); } catch {}
    removeToken();
    router.push("/login");
  };

  return (
    <aside className="w-64 bg-stone-900 text-white min-h-screen
                      flex flex-col fixed left-0 top-0">
      {/* Logo */}
      <div className="p-6 border-b border-stone-700">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🪨</span>
          <div>
            <p className="font-bold text-white">Marble AI</p>
            <p className="text-xs text-stone-400">{role === "user" ? "Tile Search" : "Admin Workspace"}</p>
          </div>
        </div>
      </div>

      {/* Nav Links */}
      <nav className="flex-1 p-4 space-y-1">
        {links.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-4 py-2.5 rounded-lg
                          text-sm font-medium transition
                          ${active
                            ? "bg-stone-700 text-white"
                            : "text-stone-400 hover:bg-stone-800 hover:text-white"
                          }`}
            >
              <Icon size={18} />
              <span className="flex-1">{label}</span>
              {href === "/dashboard/cart" && cartCount > 0 && (
                <span className="ml-auto bg-emerald-500 text-white text-xs
                                  font-bold px-1.5 py-0.5 rounded-full
                                  min-w-[20px] text-center leading-none">
                  {cartCount > 99 ? "99+" : cartCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="p-4 border-t border-stone-700">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-2.5 rounded-lg
                     text-sm text-stone-400 hover:text-white
                     hover:bg-stone-800 w-full transition"
        >
          <LogOut size={18} />
          Logout
        </button>
      </div>
    </aside>
  );
}