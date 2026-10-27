import { jsPDF } from "jspdf";

export type QuotationPdfItem = {
  tile_name: string;
  tile_sku: string;
  material: string | null;
  size_label: string | null;
  quantity: number;
  area_sqm: number;
  rate_per_sqm: number;
  line_total: number;
};

export type QuotationPdf = {
  quotation_number: string;
  client_name: string;
  company_name: string | null;
  project_name: string | null;
  email: string | null;
  phone: string | null;
  address: string | null;
  gst_rate: number;
  subtotal: number;
  gst_amount: number;
  grand_total: number;
  created_at: string;
  valid_until: string;
  created_by_name: string;
  items: QuotationPdfItem[];
};

const inr = (value: number) =>
  `INR ${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const textOrDash = (value: string | null | undefined) => value?.trim() || "Not specified";

export function downloadQuotationPdf(quotation: QuotationPdf) {
  const doc = new jsPDF({ unit: "mm", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const margin = 14;
  let y = 18;

  doc.setFillColor(28, 25, 23);
  doc.rect(0, 0, pageWidth, 28, "F");
  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(16);
  doc.text("MARBLE AI", margin, 12);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  doc.text("B2B Tile Quotation", margin, 20);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(12);
  doc.text(quotation.quotation_number, pageWidth - margin, 12, { align: "right" });
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.text("Currency: INR (Rs.)", pageWidth - margin, 20, { align: "right" });

  y = 38;
  doc.setTextColor(28, 25, 23);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Client / Project", margin, y);
  doc.text("Quotation details", 118, y);
  y += 6;
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  const left = [
    `Client: ${quotation.client_name}`,
    `Company: ${textOrDash(quotation.company_name)}`,
    `Project: ${textOrDash(quotation.project_name)}`,
    `Email: ${textOrDash(quotation.email)}`,
    `Phone: ${textOrDash(quotation.phone)}`,
    `Address: ${textOrDash(quotation.address)}`,
  ];
  const issued = new Date(quotation.created_at).toLocaleDateString("en-IN");
  const valid = new Date(quotation.valid_until).toLocaleDateString("en-IN");
  const right = [
    `Issue date: ${issued}`,
    `Valid until: ${valid} (15 days)`,
    `Prepared by: ${quotation.created_by_name}`,
    `GST: ${quotation.gst_rate.toFixed(2)}%`,
    "This document is a quotation only.",
    "It does not place an order or reserve stock.",
  ];
  left.forEach((line, index) => {
    doc.text(doc.splitTextToSize(line, 95), margin, y + index * 5);
    doc.text(right[index], 118, y + index * 5);
  });

  y += 38;
  const columns = [
    { label: "SKU / Tile", x: margin, width: 48 },
    { label: "Material / Size", x: 64, width: 38 },
    { label: "Qty", x: 104, width: 12 },
    { label: "Area m2", x: 118, width: 20 },
    { label: "Rate/m2", x: 140, width: 24 },
    { label: "Amount", x: 166, width: 30 },
  ];
  doc.setFillColor(245, 245, 244);
  doc.rect(margin, y - 5, pageWidth - margin * 2, 8, "F");
  doc.setFont("helvetica", "bold");
  columns.forEach((column) => doc.text(column.label, column.x, y));
  y += 7;
  doc.setFont("helvetica", "normal");

  quotation.items.forEach((item, index) => {
    if (y > 250) {
      doc.addPage();
      y = 20;
    }
    const nameLines = doc.splitTextToSize(`${item.tile_sku}\n${item.tile_name}`, 46);
    const spec = doc.splitTextToSize(
      `${textOrDash(item.material)}\n${textOrDash(item.size_label)}`,
      36,
    );
    const rowHeight = Math.max(10, nameLines.length * 4, spec.length * 4);
    if (index % 2 === 1) {
      doc.setFillColor(250, 250, 249);
      doc.rect(margin, y - 3.5, pageWidth - margin * 2, rowHeight + 1, "F");
    }
    doc.text(nameLines, columns[0].x, y);
    doc.text(spec, columns[1].x, y);
    doc.text(String(item.quantity), columns[2].x, y);
    doc.text(item.area_sqm.toFixed(3), columns[3].x, y);
    doc.text(item.rate_per_sqm.toFixed(2), columns[4].x, y);
    doc.text(inr(item.line_total), columns[5].x, y);
    y += rowHeight + 2;
  });

  y += 4;
  doc.line(130, y, pageWidth - margin, y);
  y += 7;
  doc.setFont("helvetica", "normal");
  doc.text("Subtotal", 140, y);
  doc.text(inr(quotation.subtotal), pageWidth - margin, y, { align: "right" });
  y += 6;
  doc.text(`GST (${quotation.gst_rate.toFixed(2)}%)`, 140, y);
  doc.text(inr(quotation.gst_amount), pageWidth - margin, y, { align: "right" });
  y += 7;
  doc.setFont("helvetica", "bold");
  doc.text("Grand total", 140, y);
  doc.text(inr(quotation.grand_total), pageWidth - margin, y, { align: "right" });

  y += 16;
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.text("Terms", margin, y);
  doc.setFont("helvetica", "normal");
  doc.setFontSize(8.5);
  const terms = [
    "1. This quotation is valid for 15 days from the issue date.",
    "2. Quoted rates apply to this document only and do not change catalog prices.",
    "3. Saving or issuing a quotation does not place an order, change order status, or deduct stock.",
    "4. Supply is subject to confirmation and available inventory at the time of order.",
    "5. GST is charged at the rate shown. Fields marked Not specified were unavailable in the catalog.",
  ];
  terms.forEach((term, index) => {
    doc.text(term, margin, y + 6 + index * 5);
  });

  doc.save(`${quotation.quotation_number}.pdf`);
}
