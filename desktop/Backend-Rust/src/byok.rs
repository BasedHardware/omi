// BYOK (Bring Your Own Keys) header helpers.
//
// Desktop Swift client sends X-BYOK-{OpenAI,Anthropic,Gemini,Deepgram} headers
// on every request via APIKeyService. These helpers extract and validate them.

use axum::http::HeaderMap;

/// Header names for each BYOK provider (case-insensitive in HTTP).
pub const HEADER_OPENAI: &str = "x-byok-openai";
pub const HEADER_ANTHROPIC: &str = "x-byok-anthropic";
pub const HEADER_GEMINI: &str = "x-byok-gemini";
pub const HEADER_DEEPGRAM: &str = "x-byok-deepgram";

/// All four required BYOK headers. Python's `_request_has_all_byok_keys()` checks
/// the same set — a fully enrolled BYOK user sends all four on every request.
const ALL_BYOK_HEADERS: &[&str] = &[
    HEADER_OPENAI,
    HEADER_ANTHROPIC,
    HEADER_GEMINI,
    HEADER_DEEPGRAM,
];

/// Extract a single BYOK header value, trimmed and non-empty.
/// Returns `None` if the header is missing, empty, or whitespace-only.
pub fn get_byok_key<'a>(headers: &'a HeaderMap, header_name: &str) -> Option<&'a str> {
    headers
        .get(header_name)
        .and_then(|v| v.to_str().ok())
        .map(str::trim)
        .filter(|v| !v.is_empty())
}

/// True if the request carries non-empty values for all four BYOK provider headers.
///
/// This mirrors Python's `_request_has_all_byok_keys()`. Presence of all four
/// headers signals the user has fully enrolled BYOK keys. The paywall escape
/// hatch trusts presence here — actual key fingerprint validation happens in
/// Python's `_check_byok_validity`.
pub fn has_all_byok_keys(headers: &HeaderMap) -> bool {
    ALL_BYOK_HEADERS
        .iter()
        .all(|h| get_byok_key(headers, h).is_some())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn headers_with(pairs: &[(&str, &str)]) -> HeaderMap {
        let mut map = HeaderMap::new();
        for (k, v) in pairs {
            map.insert(
                axum::http::HeaderName::from_bytes(k.as_bytes()).unwrap(),
                v.parse().unwrap(),
            );
        }
        map
    }

    #[test]
    fn get_byok_key_present() {
        let h = headers_with(&[("x-byok-openai", "sk-test123")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), Some("sk-test123"));
    }

    #[test]
    fn get_byok_key_trimmed() {
        let h = headers_with(&[("x-byok-openai", "  sk-test  ")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), Some("sk-test"));
    }

    #[test]
    fn get_byok_key_empty() {
        let h = headers_with(&[("x-byok-openai", "")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), None);
    }

    #[test]
    fn get_byok_key_whitespace_only() {
        let h = headers_with(&[("x-byok-openai", "   ")]);
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), None);
    }

    #[test]
    fn get_byok_key_missing() {
        let h = HeaderMap::new();
        assert_eq!(get_byok_key(&h, HEADER_OPENAI), None);
    }

    #[test]
    fn has_all_byok_keys_all_present() {
        let h = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", "sk-a"),
            ("x-byok-gemini", "sk-g"),
            ("x-byok-deepgram", "sk-d"),
        ]);
        assert!(has_all_byok_keys(&h));
    }

    #[test]
    fn has_all_byok_keys_missing_one() {
        let h = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", "sk-a"),
            ("x-byok-gemini", "sk-g"),
            // missing deepgram
        ]);
        assert!(!has_all_byok_keys(&h));
    }

    #[test]
    fn has_all_byok_keys_one_empty() {
        let h = headers_with(&[
            ("x-byok-openai", "sk-o"),
            ("x-byok-anthropic", ""),
            ("x-byok-gemini", "sk-g"),
            ("x-byok-deepgram", "sk-d"),
        ]);
        assert!(!has_all_byok_keys(&h));
    }

    #[test]
    fn has_all_byok_keys_none() {
        let h = HeaderMap::new();
        assert!(!has_all_byok_keys(&h));
    }
}
