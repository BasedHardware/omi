/// Perceptual difference hash (dHash) for deduplication of captured frames.
///
/// Algorithm:
///   1. Decode the JPEG to a grayscale image.
///   2. Resize to 9×8 pixels.
///   3. For each of the 8 rows, compare each pixel with its right neighbour.
///      Set the corresponding bit to 1 if left < right.
///   4. Pack all 64 bits into a u64.
///
/// Empirically tuned threshold (matches the Swift Rewind app):
///   - Spinner frame change  → ~1 bit difference
///   - Cursor-only movement  → ~4 bit difference
///   - Real content change   → 23+ bit difference
///
/// Therefore `DEDUP_THRESHOLD = 5` safely skips cursor/spinner noise while
/// capturing genuine screen changes.

use image::{imageops::FilterType, GrayImage};

/// Frames whose hashes differ by at most this many bits are considered
/// duplicates and will be skipped (no OCR, no DB write).
pub const DEDUP_THRESHOLD: u32 = 5;

// ---------------------------------------------------------------------------
// Core hash computation
// ---------------------------------------------------------------------------

/// Decode `jpeg_data` and compute a 64-bit dHash.
///
/// Returns `Err` only if the bytes cannot be decoded as an image.
pub fn compute_dhash(jpeg_data: &[u8]) -> Result<u64, String> {
    // Decode the raw bytes as any supported image format (JPEG in practice).
    let img = image::load_from_memory(jpeg_data).map_err(|e| format!("image decode failed: {}", e))?;

    // Convert to luma (grayscale) and resize to 9×8.
    // 9 columns → 8 comparisons per row × 8 rows = 64 bits total.
    let gray: GrayImage = image::imageops::resize(&img.to_luma8(), 9, 8, FilterType::Triangle);

    let mut hash: u64 = 0u64;
    let mut bit: u64 = 1;

    for row in 0..8usize {
        for col in 0..8usize {
            let left = gray.get_pixel(col as u32, row as u32).0[0];
            let right = gray.get_pixel((col + 1) as u32, row as u32).0[0];
            if left < right {
                hash |= bit;
            }
            bit <<= 1;
        }
    }

    Ok(hash)
}

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------

/// Count the number of bit positions where `a` and `b` differ.
#[inline]
pub fn hamming_distance(a: u64, b: u64) -> u32 {
    (a ^ b).count_ones()
}

/// Encode a dHash as a 16-character lowercase hex string for database storage.
#[inline]
pub fn dhash_to_hex(hash: u64) -> String {
    format!("{:016x}", hash)
}

/// Parse a hex string (as produced by [`dhash_to_hex`]) back to a u64.
///
/// Returns `Err` if `hex` is not a valid hex-encoded u64.
pub fn hex_to_dhash(hex: &str) -> Result<u64, String> {
    u64::from_str_radix(hex.trim(), 16).map_err(|e| format!("invalid dhash hex '{}': {}", hex, e))
}

/// Return `true` when `new_hash` and `previous_hash` are close enough that
/// the new frame should be considered a duplicate and skipped.
#[inline]
pub fn is_duplicate(new_hash: u64, previous_hash: u64) -> bool {
    hamming_distance(new_hash, previous_hash) <= DEDUP_THRESHOLD
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hamming_distance_identical() {
        assert_eq!(hamming_distance(0xDEADBEEF_CAFEBABE, 0xDEADBEEF_CAFEBABE), 0);
    }

    #[test]
    fn hamming_distance_all_differ() {
        assert_eq!(hamming_distance(0u64, u64::MAX), 64);
    }

    #[test]
    fn hamming_distance_one_bit() {
        assert_eq!(hamming_distance(0b0001, 0b0000), 1);
    }

    #[test]
    fn dhash_hex_round_trip() {
        let hash: u64 = 0x0123456789abcdef;
        let hex = dhash_to_hex(hash);
        assert_eq!(hex, "0123456789abcdef");
        assert_eq!(hex_to_dhash(&hex).unwrap(), hash);
    }

    #[test]
    fn dhash_hex_zero() {
        let hex = dhash_to_hex(0u64);
        assert_eq!(hex, "0000000000000000");
        assert_eq!(hex_to_dhash(&hex).unwrap(), 0u64);
    }

    #[test]
    fn is_duplicate_below_threshold() {
        // 3 bits differ → duplicate
        let a = 0u64;
        let b = 0b111u64;
        assert!(is_duplicate(a, b));
    }

    #[test]
    fn is_duplicate_at_threshold() {
        // Exactly DEDUP_THRESHOLD bits differ → still a duplicate
        let a = 0u64;
        let b = (1u64 << DEDUP_THRESHOLD) - 1; // 5 lowest bits set
        assert_eq!(hamming_distance(a, b), DEDUP_THRESHOLD);
        assert!(is_duplicate(a, b));
    }

    #[test]
    fn is_not_duplicate_above_threshold() {
        // 6 bits differ → not a duplicate
        let a = 0u64;
        let b = (1u64 << (DEDUP_THRESHOLD + 1)) - 1; // 6 lowest bits set
        assert!(!is_duplicate(a, b));
    }
}
