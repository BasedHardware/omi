import Image from 'next/image';
import Link from 'next/link';
import { redirect } from 'next/navigation';

export default function Home() {
  redirect('/memories');
  return (
    <div className="flex min-h-screen flex-col items-center justify-between p-12 text-xl text-white md:p-24 md:text-lg">
      <div className="mt-10">
        <Image
          src={'/omi-white.webp'}
          alt="Based Hardware Logo"
          width={100}
          height={64}
          className="mx-auto h-auto w-[80px]"
        />
        <h2 className="mt-5 text-center text-lg md:text-xl">
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
    </div>
  );
}
