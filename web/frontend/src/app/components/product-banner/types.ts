export interface ProductBannerBase {
  className?: string;
  onClick?: () => void;
  productUrl?: string;
}

export interface DetailBannerProps extends ProductBannerBase {
  appName: string;
  appCategory: string;
}

export interface FloatingBannerProps extends ProductBannerBase {
  showShipping?: boolean;
}

export interface CategoryBannerProps extends ProductBannerBase {
  category: string;
  appsCount: number;
}

export const PRODUCT_INFO = {
  name: 'Omi',
  price: '$89',
  // Canonical storefront (legacy omi-dev-kit-2 / friend-dev-kit-2 slugs redirect into the storefront).
  url: 'https://www.omi.me/?ref=omi_marketplace&utm_source=h.omi.me&utm_campaign=omi_marketplace_app_detail_page',
  shipping: 'Ships Worldwide',
  images: {
    primary: '/omi_1.webp',
    secondary: '/omi_2.webp',
  },
} as const;
