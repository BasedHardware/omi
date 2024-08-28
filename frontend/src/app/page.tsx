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
          className="h-auto w-[50px] mx-auto"
        />
        <h2 className='text-xl md:text-2xl mt-2 text-center'>
          We are working in this feature
        </h2>
        <p className='text-center max-w-xl mt-10'>
        For now, you can order Omi wearable. Remember
        everything you want to remember with Omi.
        </p>
        <Link
          href={`https://basedhardware.com/`}
          target="_blank"
          className="flex items-center gap-2 rounded-md w-fit mx-auto bg-white/90 mt-10 p-1.5 px-3.5 text-black transition-colors hover:bg-white"
        >
          Order now
        </Link>
      </div>
    </main>
  );
}
