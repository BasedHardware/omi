export default {
  async compress(source: Uint8Array): Promise<{ format: string, data: Uint8Array }> {
    return { format: 'wav', data: source };
  },
};
