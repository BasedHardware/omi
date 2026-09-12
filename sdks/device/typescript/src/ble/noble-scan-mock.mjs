export let starts = 0;
export let stops = 0;
export let discoverImpl = async function* () {
  await new Promise(() => {});
};

export function resetAdapter() {
  starts = 0;
  stops = 0;
  discoverImpl = async function* () {
    await new Promise(() => {});
  };
}

export function setDiscoverImpl(fn) {
  discoverImpl = fn;
}

const adapter = {
  state: 'poweredOn',
  async startScanningAsync() {
    starts += 1;
  },
  async stopScanningAsync() {
    stops += 1;
  },
  async *discoverAsync() {
    yield* discoverImpl();
  },
};

export default adapter;
