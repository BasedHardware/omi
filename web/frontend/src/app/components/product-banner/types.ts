import { APP_STORE_HARDWARE_PRODUCT } from '@/src/constants/app-store-hardware-product';

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
  name: APP_STORE_HARDWARE_PRODUCT.name,
  price: APP_STORE_HARDWARE_PRODUCT.displayPrice,
  url: APP_STORE_HARDWARE_PRODUCT.marketplaceOrderUrl,
  shipping: APP_STORE_HARDWARE_PRODUCT.shipping,
  images: APP_STORE_HARDWARE_PRODUCT.images,
} as const;
