'use strict';

class FakeMediaStream {
  constructor(tracks = []) {
    this._tracks = tracks;
  }
  getAudioTracks() {
    return this._tracks;
  }
  getTracks() {
    return this._tracks;
  }
}

class FakeRTCPeerConnection {
  iceGatheringState = 'new';
  localDescription = null;
  addTrack() {}
  createDataChannel() {
    return {
      readyState: 'connecting',
      send() {},
      close() {},
      addEventListener() {},
      removeEventListener() {},
    };
  }
  async createOffer() {
    return {type: 'offer', sdp: ''};
  }
  async setLocalDescription() {}
  async setRemoteDescription() {}
  addEventListener() {}
  removeEventListener() {}
  close() {}
}

module.exports = {
  RTCPeerConnection: FakeRTCPeerConnection,
  MediaStream: FakeMediaStream,
  mediaDevices: {
    getUserMedia: async () => new FakeMediaStream([]),
  },
  registerGlobals() {},
};
