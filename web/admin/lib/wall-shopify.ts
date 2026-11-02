/** Read-only orders. SHOPIFY_STORE / SHOPIFY_ACCESS_TOKEN match distributor wiring. */
export interface ShopLine {
  id: string;
  title: string;
  sku: string | null;
  quantity: number;
  discountedTotalSet: { shopMoney: { amount: string; currencyCode: string } };
}
interface Connection<T> {
  nodes: T[];
  pageInfo: { hasNextPage: boolean; endCursor?: string };
}
export interface ShopOrder {
  test: boolean;
  cancelledAt: string | null;
  displayFinancialStatus: string;
  lineItems: Connection<ShopLine>;
  refunds: {
    refundLineItems: Connection<{
      quantity: number;
      subtotalSet: { shopMoney: { amount: string; currencyCode: string } };
      lineItem: { id: string };
    }>;
  }[];
}
// Explicit conservative title fallback until the owner supplies the canonical SKU/bundle map.
export const DEVICE_TITLES = [
  "Omi",
  "Omi Dev Kit 2",
  "Omi Dev Kit",
  "Omi Glass",
  "Omi Glass Dev Kit",
  "Omi Firmware Developer Kit",
];
export function classifyLine(
  line: Pick<ShopLine, "title" | "sku">
): "hardware" | "prepay" | "other" {
  const skus = (process.env.OMI_TV_DEVICE_SKUS || "")
    .split(",")
    .filter(Boolean);
  if (line.sku && skus.includes(line.sku)) return "hardware";
  if (DEVICE_TITLES.includes(line.title)) return "hardware";
  if (/^Omi Unlimited(?::| Yearly Plan)/.test(line.title)) return "prepay";
  return "other";
}
export function aggregateOrders(orders: ShopOrder[]) {
  let units = 0,
    hardwareUsd = 0,
    prepayUsd = 0,
    unmappedLines = 0;
  for (const order of orders) {
    if (
      order.test ||
      order.cancelledAt ||
      !["PAID", "PARTIALLY_REFUNDED", "REFUNDED"].includes(
        order.displayFinancialStatus
      )
    )
      continue;
    if (
      order.lineItems.pageInfo.hasNextPage ||
      order.refunds.some((r) => r.refundLineItems.pageInfo.hasNextPage)
    )
      throw new Error("Shopify nested pagination incomplete");
    for (const line of order.lineItems.nodes) {
      const kind = classifyLine(line);
      if (kind === "other") {
        unmappedLines++;
        continue;
      }
      if (line.discountedTotalSet.shopMoney.currencyCode !== "USD")
        throw new Error("Shopify shop currency needs approved FX");
      let quantity = line.quantity,
        dollars = Number(line.discountedTotalSet.shopMoney.amount);
      for (const refund of order.refunds)
        for (const r of refund.refundLineItems.nodes) {
          if (r.lineItem.id !== line.id) continue;
          if (r.subtotalSet.shopMoney.currencyCode !== "USD")
            throw new Error("Refund FX unavailable");
          quantity -= r.quantity;
          dollars -= Number(r.subtotalSet.shopMoney.amount);
        }
      if (!Number.isFinite(dollars)) throw new Error("Invalid Shopify money");
      if (kind === "hardware") {
        units += quantity;
        hardwareUsd += dollars;
      } else prepayUsd += dollars;
    }
  }
  return {
    units,
    hardwareUsd: Math.round(hardwareUsd * 100) / 100,
    prepayUsd: Math.round(prepayUsd * 100) / 100,
    unmappedLines,
  };
}
const QUERY = `query($q:String!,$after:String) { orders(first:100,after:$after,query:$q) {
 pageInfo { hasNextPage endCursor } nodes { test cancelledAt displayFinancialStatus
 lineItems(first:250) { pageInfo { hasNextPage } nodes { id title sku quantity discountedTotalSet { shopMoney { amount currencyCode } } } }
 refunds { refundLineItems(first:250) { pageInfo { hasNextPage } nodes { quantity subtotalSet { shopMoney { amount currencyCode } } lineItem { id } } } }
 } } }`;
export async function fetchShopifyWeek(start: string, end: string) {
  const store = process.env.SHOPIFY_STORE;
  if (!store || !/^[a-zA-Z0-9-]+\.myshopify\.com$/.test(store))
    throw new Error("SHOPIFY_STORE unavailable/invalid");
  let token = process.env.SHOPIFY_ACCESS_TOKEN;
  if (
    !token &&
    process.env.SHOPIFY_CLIENT_ID &&
    process.env.SHOPIFY_CLIENT_SECRET
  ) {
    const res = await fetch(`https://${store}/admin/oauth/access_token`, {
      method: "POST",
      body: new URLSearchParams({
        grant_type: "client_credentials",
        client_id: process.env.SHOPIFY_CLIENT_ID,
        client_secret: process.env.SHOPIFY_CLIENT_SECRET,
      }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) throw new Error("Shopify token exchange failed");
    token = (await res.json()).access_token;
  }
  if (!token)
    throw new Error("Shopify credentials unavailable (read_orders required)");
  const orders: ShopOrder[] = [];
  let after: string | null = null;
  for (let page = 0; page < 100; page++) {
    const res = await fetch(
      `https://${store}/admin/api/${
        process.env.SHOPIFY_API_VERSION || "2025-10"
      }/graphql.json`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Shopify-Access-Token": token,
        },
        body: JSON.stringify({
          query: QUERY,
          variables: {
            q: `created_at:>=${start} created_at:<${end} -test:true`,
            after,
          },
        }),
        signal: AbortSignal.timeout(60_000),
      }
    );
    if (!res.ok)
      throw new Error(
        `Shopify orders failed (${res.status}; read_orders required)`
      );
    const data = await res.json();
    if (data.errors || !data.data?.orders)
      throw new Error("Shopify orders unavailable (read_orders required)");
    const connection: Connection<ShopOrder> = data.data.orders;
    orders.push(...connection.nodes);
    if (!connection.pageInfo.hasNextPage) return aggregateOrders(orders);
    if (
      !connection.pageInfo.endCursor ||
      connection.pageInfo.endCursor === after
    )
      throw new Error("Shopify cursor did not advance");
    after = connection.pageInfo.endCursor;
  }
  throw new Error("Shopify pagination cap reached");
}
