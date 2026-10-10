class OmiAudioProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    // Default buffer size if not provided
    this.bufferSize = options.processorOptions?.bufferSize || 4096;
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      if (channelData) {
        for (let i = 0; i < channelData.length; i++) {
          this.buffer[this.bufferIndex++] = channelData[i];

          if (this.bufferIndex >= this.bufferSize) {
            // Send a copy of the Float32Array to the main thread
            // We use slice() to copy the data because the original buffer is reused
            this.port.postMessage(this.buffer.slice());
            this.bufferIndex = 0;
          }
        }
      }
    }
    return true; // Keep processor alive
  }
}

registerProcessor('omi-audio-processor', OmiAudioProcessor);
