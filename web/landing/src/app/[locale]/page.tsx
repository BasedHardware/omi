import { Navbar } from '@/components/navbar';
import { Hero } from '@/components/hero';
import { TrustBar } from '@/components/trust-bar';
import { Manifesto } from '@/components/manifesto';
import { ProductShowcase } from '@/components/product-showcase';
import { HowItWorks } from '@/components/how-it-works';
import { VideoSection } from '@/components/video-section';
import { MeetNooto } from '@/components/meet-nooto';
import { Features } from '@/components/features';
import { CTASection } from '@/components/cta-section';
import { Footer } from '@/components/footer';

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <TrustBar />
        <Manifesto />
        <ProductShowcase />
        <HowItWorks />
        <VideoSection />
        <MeetNooto />
        <Features />
        <CTASection />
      </main>
      <Footer />
    </>
  );
}
