import Image from 'next/image';
import Link from 'next/link';
import { redirect } from 'next/navigation';

export default function Home() {
  redirect('/apps');
  return (
    <div className="flex min-h-screen flex-col items-center justify-between p-[3rem] text-xl text-white md:p-[6rem] md:text-lg">
      <div className="mt-[2.5rem]">
        <Image
          src={'/omi-white.webp'}
          alt="Based Hardware Logo"
          width={100}
          height={64}
          className="mx-auto h-auto w-[5rem]"
        />
        <h2 className="mt-[1.25rem] text-center text-lg md:text-xl">
          We are working in this feature
        </h2>
        <p className="mt-[2.5rem] max-w-xl text-center">
          For now, you can order Omi wearable. Remember everything you want to remember
          with Omi.
        </p>
        <Link
          href={`https://basedhardware.com/`}
          target="_blank"
          className="mx-auto mt-[2.5rem] flex w-fit items-center gap-[0.5rem] rounded-md bg-white/90 p-[0.375rem] px-[0.875rem] text-black transition-colors hover:bg-white"
        >
          Order now
        </Link>
      </div>
    </div>
  );
}
