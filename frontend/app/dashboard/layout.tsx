"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { type AccountRole, isAccountRole, isLoggedIn, removeToken, setRole } from "@/lib/auth";
import Sidebar from "@/components/Sidebar";
import api from "@/lib/api";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [role, setAccountRole] = useState<AccountRole | null>(null);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace("/login");
      return;
    }

    api.get("/api/auth/me")
      .then(({ data }) => {
        if (!isAccountRole(data.role)) {
          removeToken();
          router.replace("/login");
          return;
        }
        const accountRole: AccountRole = data.role;
        setRole(accountRole);
        setAccountRole(accountRole);

        const isAdminPage = pathname === "/dashboard"
          || pathname === "/dashboard/tiles"
          || pathname.startsWith("/dashboard/inventory");
        if (accountRole === "user" && isAdminPage) {
          router.replace("/dashboard/search");
        }
        if (accountRole !== "super_admin" && pathname.startsWith("/dashboard/users")) {
          router.replace("/dashboard");
        }
      })
      .catch(() => {
        removeToken();
        router.replace("/login");
      });
  }, [pathname, router]);

  if (!role) {
    return <div className="min-h-screen bg-stone-50" aria-busy="true" />;
  }

  return (
    <div className="flex min-h-screen bg-stone-50">
      <Sidebar role={role} />
      <main className="ml-0 md:ml-64 flex-1 p-4 sm:p-8 pt-20 md:pt-8">{children}</main>
    </div>
  );
}