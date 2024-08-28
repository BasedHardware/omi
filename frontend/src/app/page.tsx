import Image from 'next/image';
import Link from 'next/link';

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-12 text-xl text-white md:p-24 md:text-lg">
      <div>
        <Image
          src={'/logo.webp'}
          alt="Based Hardware Logo"
          width={100}
          height={64}
          className="mx-auto h-auto w-[50px]"
        />
        <h2 className="mt-2 text-center text-xl md:text-2xl">
          We are working in this feature
        </h2>
        <p className="mt-10 max-w-xl text-center">
          For now, you can order Omi wearable. Remember everything you want to remember
          with Omi.
        </p>
        <Link
          href={`https://basedhardware.com/`}
          target="_blank"
          className="mx-auto mt-10 flex w-fit items-center gap-2 rounded-md bg-white/90 p-1.5 px-3.5 text-black transition-colors hover:bg-white"
        >
          Order now
        </Link>
      </div>
    </main>
  );
}
