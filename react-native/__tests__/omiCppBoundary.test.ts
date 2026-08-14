test('C++ boundary wrapper forwards the packet and capability calls', async () => {
  const boundary = {
    normalizePacket: jest.fn().mockResolvedValue([1, 2, 3]),
    getNativeCapabilities: jest.fn().mockResolvedValue({
      simd: true,
      abi_version: 1,
      max_packet_bytes: 4096,
    }),
  };
  jest.resetModules();
  jest.doMock('react-native', () => ({NativeModules: {OmiCppBoundary: boundary}}));

  const loaded = require('../src/omiCppBoundary') as typeof import('../src/omiCppBoundary');
  expect(loaded.isCppBoundaryInstalled).toBe(true);
  await expect(loaded.omiCppBoundary?.normalizePacket([0xaa, 0x55])).resolves.toEqual([1, 2, 3]);
  await expect(loaded.omiCppBoundary?.getNativeCapabilities()).resolves.toEqual({
    simd: true,
    abi_version: 1,
    max_packet_bytes: 4096,
  });
  expect(boundary.normalizePacket).toHaveBeenCalledWith([0xaa, 0x55]);
  jest.dontMock('react-native');
});
