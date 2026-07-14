// Audio-mute helper stdio opcodes (request frame: [uint32 LE len][1 byte opcode][JSON]).
//
// Deliberately decoupled from the automation/OCR helpers — its own opcode space
// and version, owned by Track 2. The pure length-prefixed framing
// (encodeRequest / FrameDecoder) is protocol-agnostic and shared from
// ../ocr/helperProtocol; only the opcodes + version live here.
export const OP_MUTE = 1
export const OP_RESTORE = 2
export const OP_HELLO = 3

// Bumped whenever the wire shape changes; the bridge asserts a match on spawn.
// Must equal ProtocolVersion in src/main/audio/helper/Program.cs.
export const PROTOCOL_VERSION = 1
