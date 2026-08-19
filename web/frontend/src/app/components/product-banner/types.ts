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
  url: 'https://www.omi.me/',
  shipping: 'Ships Worldwide',
  images: {
    primary: '/omi_1.webp',
    secondary: '/omi_2.webp',
  },
} as const;
