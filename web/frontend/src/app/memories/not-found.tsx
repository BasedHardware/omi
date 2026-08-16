/** Generic /memories group boundary — conversation-specific copy lives under [id]/not-found. */
export default function NotFound() {
  return (
    <div className="font-system-ui min-h-screen bg-black">
      <section className="relative mx-auto max-w-screen-md px-6 py-24 text-center md:px-12 md:py-32">
        <h1 className="text-2xl font-bold text-white sm:text-3xl">Page not found</h1>
        <p className="mx-auto mt-4 max-w-md text-base leading-7 text-gray-400">
          That page may have moved or no longer exists.
        </p>
        <a
          href="https://omi.me"
          className="mt-10 inline-block rounded-2xl bg-white px-10 py-4 text-lg font-semibold text-black transition-all duration-300 hover:translate-y-[-2px] hover:bg-gray-100"
        >
          Go to Omi
        </a>
      </section>
    </div>
  );
}
