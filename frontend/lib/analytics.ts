export type TrendPoint = { date: string; count: number };
export type RevenueTrendPoint = { date: string; amount: number | null; complete: boolean };

export type Analytics = {
  date_range: { start_date: string; end_date: string };
  definitions: {
    completed_statuses: string[];
    sales: string;
    visual_search_popularity: string;
    inventory: string;
  };
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
    revenue: number | null;
    average_order_value: number | null;
    revenue_available: boolean;
    revenue_reason: string;
    aov_available: boolean;
    aov_reason: string;
    conversion_rate: number | null;
    conversion_available: boolean;
    trend: TrendPoint[];
    revenue_trend: RevenueTrendPoint[];
    recent: {
      id: number;
      status: string;
      total_amount: number | null;
      placed_at: string | null;
      account_email: string;
    }[];
    best_sellers: {
      tile_id: number | null;
      sku: string;
      name: string;
      units_sold: number;
      revenue: number | null;
      revenue_available: boolean;
    }[];
    top_searched_tiles: { tile_id: number; sku: string; name: string; searches: number }[];
    top_buyers: {
      account_id: number;
      name: string;
      email: string;
      completed_orders: number;
      revenue: number | null;
      revenue_available: boolean;
    }[];
    production_vs_sales: {
      available: boolean;
      produced_quantity: number;
      sold_quantity: number;
      trend: { date: string; produced: number; sold: number }[];
      reason: string;
    };
    search_to_quotation_to_order: {
      available: boolean;
      searches: number;
      linked_searches: number;
      linked_quotes: number;
      linked_orders: number;
      search_to_quote_rate: number;
      quote_to_order_rate: number;
      reason: string;
    };
  };
  inventory: {
    records: number;
    not_configured_products: number;
    quantity_total: number;
    out_of_stock: number;
    low_stock: number;
    in_stock: number;
    low_stock_items: {
      tile_id: number;
      sku: string;
      name: string;
      quantity: number;
      threshold: number;
    }[];
    stock_aging_and_turnover: {
      available: boolean;
      reason: string;
      items: {
        tile_id: number;
        sku: string;
        name: string;
        current_stock: number;
        average_stock: number;
        outflow_quantity: number;
        turnover: number;
        stock_age_days: number | null;
        available: boolean;
      }[];
    };
  };
};

export const localDate = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

export const rangeParams = (rangeDays: number) => {
  const end = new Date();
  const start = new Date(end);
  start.setDate(start.getDate() - rangeDays + 1);
  return { start_date: localDate(start), end_date: localDate(end) };
};

export const formatInr = (value: number | null | undefined, available = true) => {
  if (!available || value == null) return "Unavailable";
  return `₹${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

export const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Date unavailable";
