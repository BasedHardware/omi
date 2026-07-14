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
// v2: MUTE's no-op response carries {reason, peak}, and the "is audio playing"
//     test samples a window instead of a single instant (a single MasterPeakValue
//     read is 0 between the render client's buffer fills, so v1 silently refused
//     to mute while audio WAS playing).
export const PROTOCOL_VERSION = 2
