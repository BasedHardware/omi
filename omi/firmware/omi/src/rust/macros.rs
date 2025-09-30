// Prototypical ergonomics layer for migrating legacy Zephyr firmware into Rust.
// The macros below are intentionally declarative so firmware code feels familiar to
// Python/Node engineers without compromising on safety or determinism.

/// Support types shared by the macros below.
pub mod omi_macro_support {
    use core::fmt;
    use core::future::Future;
    use core::marker::PhantomData;

    /// Specification produced by `omi_task!` describing an async Zephyr/Embassy task.
    /// Keeping this in a dedicated type lets the macro stay const-friendly while the
    /// runtime decides how to actually spawn the future.
    pub struct TaskSpec<F, Fut>
    where
        F: Fn() -> Fut,
        Fut: Future,
    {
        pub name: &'static str,
        pub stack_bytes: usize,
        pub priority: u8,
        pub future_factory: F,
        phantom: PhantomData<Fut>,
    }

    impl<F, Fut> TaskSpec<F, Fut>
    where
        F: Fn() -> Fut,
        Fut: Future,
    {
        pub fn new(name: &'static str, stack_bytes: usize, priority: u8, future_factory: F) -> Self {
            Self {
                name,
                stack_bytes,
                priority,
                future_factory,
                phantom: PhantomData,
            }
        }
    }

    /// High-level peripheral category emitted by `omi_peripheral!`.
    #[derive(Debug, Clone, Copy)]
    pub enum PeripheralKind {
        Gpio,
        Adc,
        Spi,
        Custom(&'static str),
    }

    /// Individual pin description for declarative peripheral setup.
    #[derive(Debug, Clone, Copy)]
    pub struct PinSpec {
        pub name: &'static str,
        pub number: u8,
        pub active_high: bool,
        pub capabilities: &'static [&'static str],
    }

    /// Aggregated peripheral metadata plus init/teardown hooks produced at compile time.
    pub struct PeripheralSpec {
        pub name: &'static str,
        pub kind: PeripheralKind,
        pub power_domain: &'static str,
        pub pins: &'static [PinSpec],
        pub capabilities: &'static [&'static str],
        pub init: fn() -> Result<(), &'static str>,
        pub teardown: fn(),
    }

    /// GATT access directives used by `omi_ble_service!`.
    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    pub enum BleAccess {
        Read,
        Write,
        Notify,
        Indicate,
    }

    /// Serialization options for BLE characteristics so host bindings pick the right codec.
    #[derive(Debug, Clone, Copy)]
    pub enum CodecSpec {
        Cbor { rust_type: &'static str },
        Json { rust_type: &'static str },
        Binary,
    }

    /// Individual characteristic metadata.
    #[derive(Debug, Clone, Copy)]
    pub struct BleCharacteristicSpec {
        pub name: &'static str,
        pub uuid: &'static str,
        pub access: &'static [BleAccess],
        pub codec: CodecSpec,
    }

    impl BleCharacteristicSpec {
        pub fn name(&self) -> &'static str {
            self.name
        }

        pub fn uuid(&self) -> &'static str {
            self.uuid
        }

        pub fn access(&self) -> &'static [BleAccess] {
            self.access
        }

        pub fn codec(&self) -> CodecSpec {
            self.codec
        }
    }

    /// Minimal registry hook to keep host bindings in sync regardless of transport backend.
    pub trait BleRegistry {
        fn register_service(&mut self, spec: &BleServiceSpec);
    }

    /// Service description returned by `omi_ble_service!`.
    #[derive(Debug)]
    pub struct BleServiceSpec {
        pub name: &'static str,
        pub uuid: &'static str,
        pub characteristics: &'static [BleCharacteristicSpec],
        pub advertise: bool,
    }

    impl BleServiceSpec {
        pub fn register(&self, registry: &mut dyn BleRegistry) {
            registry.register_service(self);
        }

        pub fn characteristics(&self) -> &'static [BleCharacteristicSpec] {
            self.characteristics
        }

        pub fn find_characteristic(&self, name: &str) -> Option<&'static BleCharacteristicSpec> {
            self.characteristics.iter().find(|spec| spec.name == name)
        }
    }

    /// Metadata emitted by `omi_config!` for bridging into JS/Python tooling.
    #[derive(Debug, Clone, Copy)]
    pub struct ConfigFieldSpec {
        pub field: &'static str,
        pub symbol: &'static str,
        pub rust_type: &'static str,
        pub default: Option<&'static str>,
    }

    #[derive(Debug, Clone, Copy)]
    pub struct ConfigSpec {
        pub name: &'static str,
        pub fields: &'static [ConfigFieldSpec],
    }

    /// Helper trait for converting Kconfig symbols into strongly typed values.
    pub trait KconfigValue: Sized {
        fn parse(symbol: &'static str, raw: Option<&'static str>, default: Option<Self>) -> Self;
    }

    impl KconfigValue for bool {
        fn parse(symbol: &'static str, raw: Option<&'static str>, default: Option<Self>) -> Self {
            match raw {
                Some("y") | Some("Y") | Some("1") | Some("true") | Some("TRUE") => true,
                Some("n") | Some("N") | Some("0") | Some("false") | Some("FALSE") => false,
                Some(value) => panic!("Unexpected boolean value `{value}` for {symbol}"),
                None => default.unwrap_or(false),
            }
        }
    }

    macro_rules! impl_kconfig_fromstr {
        ($($ty:ty),+ $(,)?) => {
            $(
                impl KconfigValue for $ty {
                    fn parse(symbol: &'static str, raw: Option<&'static str>, default: Option<Self>) -> Self {
                        match raw {
                            Some(value) => value.parse::<$ty>().unwrap_or_else(|err| {
                                panic!("Failed to parse `{value}` for {symbol}: {err:?}")
                            }),
                            None => default.unwrap_or_else(|| {
                                panic!("Missing Kconfig symbol {symbol} and no default provided")
                            }),
                        }
                    }
                }
            )+
        };
    }

    impl_kconfig_fromstr!(
        u8, u16, u32, u64, usize,
        i8, i16, i32, i64, isize,
        f32, f64
    );

    impl KconfigValue for &'static str {
        fn parse(symbol: &'static str, raw: Option<&'static str>, default: Option<Self>) -> Self {
            match raw {
                Some(value) => value,
                None => default.unwrap_or_else(|| {
                    panic!("Missing Kconfig symbol {symbol} and no default provided")
                }),
            }
        }
    }

    /// Runtime parser used by `omi_config!` so the macro can stay tiny.
    pub fn kconfig_value<T>(symbol: &'static str, raw: Option<&'static str>, default: Option<T>) -> T
    where
        T: KconfigValue,
    {
        T::parse(symbol, raw, default)
    }

    /// Guard utility shared by `omi_guard!` and `omi_ffi_export!`.
    pub struct Guard;

    impl Guard {
        #[allow(unused_variables)]
        pub fn fail<E>(
            condition: &'static str,
            file: &'static str,
            line: u32,
            breadcrumbs: &[&'static str],
            error: E,
        ) -> E {
            #[cfg(feature = "std")]
            {
                eprintln!(
                    "omi_guard assertion failed: `{condition}` at {file}:{line} breadcrumbs={:?}",
                    breadcrumbs
                );
            }
            error
        }

        #[allow(unused_variables)]
        pub fn report_ffi_error(name: &'static str, file: &'static str, line: u32, detail: &str) {
            #[cfg(feature = "std")]
            {
                eprintln!("omi_ffi_export error in {name} ({file}:{line}): {detail}");
            }
        }
    }

    /// Dispatch helper for `omi_ffi_export!` that converts a `Result` into an ABI-safe value.
    pub fn ffi_export<F, R, E>(
        name: &'static str,
        file: &'static str,
        line: u32,
        f: F,
        error_value: R,
    ) -> R
    where
        F: FnOnce() -> Result<R, E>,
        E: fmt::Debug,
    {
        match f() {
            Ok(value) => value,
            Err(err) => {
                Guard::report_ffi_error(name, file, line, core::any::type_name::<E>());
                let _ = err; // keep error in scope for post-mortem prints behind feature flags
                error_value
            }
        }
    }
}

#[doc(hidden)]
#[macro_export]
macro_rules! __omi_slice {
    // No-arg form creates a canonical empty slice so generated specs do not allocate.
    () => {
        &[]
    };
    // Any number of expressions becomes a static slice, which works in const contexts.
    ($($item:expr),+ $(,)?) => {
        &[$($item),+]
    };
}

#[macro_export]
macro_rules! omi_task {
    // Primary entry point that accepts explicit field-style arguments. This mirrors how
    // async tasks are configured inside Zephyr Kconfig blocks and keeps call sites readable.
    (
        name: $name:ident,
        stack: $stack:expr,
        priority: $priority:expr,
        future: $future:expr $(,)?
    ) => {{
        $crate::macros::omi_macro_support::TaskSpec::new(
            stringify!($name),
            $stack,
            $priority,
            $future,
        )
    }};
    // Secondary syntax sugar so `omi_task!(my_task, stack = ...)` works without repeating
    // keywords. It simply rewrites the invocation into the canonical form above.
    (
        $name:ident,
        stack = $stack:expr,
        priority = $priority:expr,
        future = $future:expr $(,)?
    ) => {{
        $crate::omi_task!(
            name: $name,
            stack: $stack,
            priority: $priority,
            future: $future
        )
    }};
}

#[macro_export]
macro_rules! omi_peripheral {
    // Internal helpers to normalise optional `active_high` parameters.
    (@active_high $value:expr) => { $value };
    (@active_high) => { true };

    // Declarative description of a peripheral. The macro emits a module containing
    // the init/teardown shims plus a `PeripheralSpec` that higher-level code can index.
    (
        name: $name:ident,
        kind: $kind:ident,
        power: $power:expr,
        pins: [
            $(
                {
                    name: $pin_name:ident,
                    number: $pin_number:expr
                    $(, active_high: $active_high:expr)?
                    $(, capabilities: [ $( $pin_cap:expr ),* $(,)? ])?
                }
            ),* $(,)?
        ],
        capabilities: [ $( $cap:expr ),* $(,)? ],
        init: $init:block,
        teardown: $teardown:block
    ) => {
        pub mod $name {
            use $crate::macros::omi_macro_support::{PeripheralKind, PeripheralSpec, PinSpec};

            pub fn init() -> Result<(), &'static str> $init
            pub fn teardown() $teardown

            pub const SPEC: PeripheralSpec = PeripheralSpec {
                name: stringify!($name),
                kind: PeripheralKind::$kind,
                power_domain: $power,
                pins: &[
                    $(
                        PinSpec {
                            name: stringify!($pin_name),
                            number: $pin_number,
                            active_high: $crate::omi_peripheral!(@active_high $( $active_high )?),
                            capabilities: $crate::__omi_slice!( $( $( $pin_cap ),* )? ),
                        }
                    ),*
                ],
                capabilities: $crate::__omi_slice!( $( $cap ),* ),
                init: init,
                teardown: teardown,
            };
        }

        pub use $name::SPEC as $name;
    };
}

#[macro_export]
macro_rules! omi_ble_service {
    // Access/codec helpers keep macro bodies readable and guarantee exhaustive mapping.
    (@access Read) => { $crate::macros::omi_macro_support::BleAccess::Read };
    (@access Write) => { $crate::macros::omi_macro_support::BleAccess::Write };
    (@access Notify) => { $crate::macros::omi_macro_support::BleAccess::Notify };
    (@access Indicate) => { $crate::macros::omi_macro_support::BleAccess::Indicate };

    (@codec_kind Cbor($ty:ty)) => {
        $crate::macros::omi_macro_support::CodecSpec::Cbor { rust_type: stringify!($ty) }
    };
    (@codec_kind Json($ty:ty)) => {
        $crate::macros::omi_macro_support::CodecSpec::Json { rust_type: stringify!($ty) }
    };
    (@codec_kind Binary) => { $crate::macros::omi_macro_support::CodecSpec::Binary };
    (@codec_kind Binary()) => { $crate::macros::omi_macro_support::CodecSpec::Binary };
    (@codec_kind Raw) => { $crate::macros::omi_macro_support::CodecSpec::Binary };
    (@codec_kind Raw()) => { $crate::macros::omi_macro_support::CodecSpec::Binary };
    (@codec_kind $other:ident($($rest:tt)*)) => {
        compile_error!(concat!("Unsupported codec `", stringify!($other), "`"))
    };

    (
        name: $name:ident,
        uuid: $uuid:expr,
        advertise: $advertise:expr,
        characteristics: []
    ) => {
        compile_error!("omi_ble_service! requires at least one characteristic");
    };

    (
        name: $name:ident,
        uuid: $uuid:expr,
        advertise: $advertise:expr,
        characteristics: [
            $(
                {
                    name: $char_name:ident,
                    uuid: $char_uuid:expr,
                    access: [ $( $access:ident ),* $(,)? ],
                    codec: $codec_kind:ident $( ( $codec_ty:ty ) )?
                }
            ),+ $(,)?
        ]
    ) => {
        #[allow(non_snake_case)]
        pub mod $name {
            use $crate::macros::omi_macro_support::{BleAccess, BleCharacteristicSpec, BleRegistry, BleServiceSpec, CodecSpec};

            $(
                #[allow(non_upper_case_globals)]
                pub const $char_name: BleCharacteristicSpec = BleCharacteristicSpec {
                    name: stringify!($char_name),
                    uuid: $char_uuid,
                    access: $crate::__omi_slice!( $( $crate::omi_ble_service!(@access $access) ),* ),
                    codec: $crate::omi_ble_service!(@codec_kind $codec_kind( $( $codec_ty )? )),
                };
            )*

            pub const CHARACTERISTICS: &[BleCharacteristicSpec] = $crate::__omi_slice!( $( $char_name ),* );

            pub const SPEC: BleServiceSpec = BleServiceSpec {
                name: stringify!($name),
                uuid: $uuid,
                characteristics: CHARACTERISTICS,
                advertise: $advertise,
            };

            pub fn uuid_str() -> &'static str {
                $uuid
            }

            pub fn uuid_cstr() -> &'static str {
                concat!($uuid, "\0")
            }

            #[allow(non_camel_case_types)]
            #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
            pub enum Characteristic {
                $( $char_name ),*
            }

            impl Characteristic {
                pub fn spec(self) -> &'static BleCharacteristicSpec {
                    match self {
                        $( Self::$char_name => &$char_name, )*
                    }
                }

                pub fn uuid(self) -> &'static str {
                    self.spec().uuid
                }

                pub fn access(self) -> &'static [BleAccess] {
                    self.spec().access
                }

                pub fn codec(self) -> CodecSpec {
                    self.spec().codec
                }

                pub fn uuid_cstr(self) -> &'static str {
                    match self {
                        $( Self::$char_name => concat!($char_uuid, "\0"), )*
                    }
                }
            }

            pub fn spec() -> &'static BleServiceSpec {
                &SPEC
            }

            pub fn register(registry: &mut dyn BleRegistry) {
                registry.register_service(&SPEC);
            }
        }
    };

    // Allow codec helper reuse inside generated modules without qualifying.
    (@access $role:ident) => { compile_error!(concat!("Unsupported access role `", stringify!($role), "`")) };
}

#[macro_export]
macro_rules! omi_config {
    // Struct definition macro that wires Kconfig symbols into a typed configuration bucket.
    (
        $(#[$meta:meta])* struct $name:ident {
            $(
                $(#[$field_meta:meta])* $field:ident : $ty:ty $(= default($default:expr))? => $symbol:literal $(,)?
            )*
        }
    ) => {
        $(#[$meta])* pub struct $name {
            $(
                $(#[$field_meta])* pub $field: $ty,
            )*
        }

        impl $name {
            pub fn load() -> Self {
                Self {
                    $(
                        // Each field pulls from `option_env!` so the same code works in tests.
                        $field: $crate::omi_macro_support::kconfig_value(
                            $symbol,
                            option_env!($symbol),
                            $crate::omi_config!(@default $( $default )?)
                        ),
                    )*
                }
            }

            pub const FIELD_SPECS: &'static [$crate::omi_macro_support::ConfigFieldSpec] = &[
                $(
                    $crate::omi_macro_support::ConfigFieldSpec {
                        field: stringify!($field),
                        symbol: $symbol,
                        rust_type: stringify!($ty),
                        default: $crate::omi_config!(@default_str $( $default )?),
                    }
                ),*
            ];

            pub fn spec() -> $crate::omi_macro_support::ConfigSpec {
                $crate::omi_macro_support::ConfigSpec {
                    name: stringify!($name),
                    fields: Self::FIELD_SPECS,
                }
            }
        }

        impl Default for $name {
            fn default() -> Self {
                Self::load()
            }
        }
    };

    (@default $default:expr) => { Some($default) };
    (@default) => { None };

    (@default_str $default:expr) => { Some(stringify!($default)) };
    (@default_str) => { None };
}

#[macro_export]
macro_rules! omi_guard {
    // Runtime guard patterned after Python's assert, but returning early with a caller-supplied error.
    ($cond:expr, $err:expr $(, $breadcrumb:expr )* $(,)?) => {{
        if !$cond {
            return Err($crate::omi_macro_support::Guard::fail(
                stringify!($cond),
                file!(),
                line!(),
                &[$( $breadcrumb ),*],
                $err,
            ));
        }
    }};
}

#[macro_export]
macro_rules! omi_ffi_export {
    // Wrap extern "C" functions so they return ABI-safe values while logging rich errors.
    (
        $(#[$meta:meta])* fn $name:ident ( $( $arg:ident : $ty:ty ),* $(,)? ) -> $ret:ty {
            $($body:tt)*
        } catch $error_value:expr
    ) => {
        $(#[$meta])* #[no_mangle]
        pub extern "C" fn $name( $( $arg : $ty ),* ) -> $ret {
            $crate::omi_macro_support::ffi_export(
                stringify!($name),
                file!(),
                line!(),
                || -> Result<$ret, _> { $($body)* },
                $error_value,
            )
        }
    };
}

#[cfg(test)]
mod tests {
    use super::omi_macro_support::{BleRegistry, BleServiceSpec, PeripheralSpec};
    use super::*;

    struct FakeRegistry;
    impl BleRegistry for FakeRegistry {
        fn register_service(&mut self, spec: &BleServiceSpec) {
            assert_eq!(spec.name, "demo_audio");
        }
    }

    #[test]
    fn task_macro_builds_spec() {
        let spec = omi_task!(
            name: blink_task,
            stack: 1024,
            priority: 3,
            future: || async { Ok::<(), &'static str>(()) }
        );

        assert_eq!(spec.name, "blink_task");
        assert_eq!(spec.stack_bytes, 1024);
        assert_eq!(spec.priority, 3);

        // ensure future factory is callable without pinning infrastructure
        let _future = (spec.future_factory)();
    }

    #[test]
    fn peripheral_macro_registers_spec() {
        omi_peripheral!(
            name: demo_led,
            kind: Gpio,
            power: "vdd_main",
            pins: [
                { name: red, number: 17, active_high: true, capabilities: ["pwm"] },
                { name: green, number: 18, capabilities: ["pwm"] },
                { name: blue, number: 19, capabilities: ["pwm"] }
            ],
            capabilities: ["status-led"],
            init: { Ok(()) },
            teardown: { {} }
        );

        fn assert_spec(spec: &PeripheralSpec) {
            assert_eq!(spec.name, "demo_led");
            assert_eq!(spec.power_domain, "vdd_main");
            assert_eq!(spec.pins.len(), 3);
            assert!((spec.init)().is_ok());
            (spec.teardown)();
        }

        assert_spec(&demo_led);
    }

    #[test]
    fn ble_service_macro_creates_spec() {
        omi_ble_service!(
            name: demo_audio,
            uuid: "814b9b7c-25fd-4acd-8604-d28877beee6d",
            advertise: true,
            characteristics: [
                {
                    name: audio_data,
                    uuid: "814b9b7c-25fd-4acd-8604-d28877beee6e",
                    access: [Read, Notify],
                    codec: Cbor(u8)
                },
                {
                    name: codec_format,
                    uuid: "814b9b7c-25fd-4acd-8604-d28877beee6f",
                    access: [Read],
                    codec: Json(u16)
                }
            ]
        );

        assert_eq!(demo_audio::SPEC.characteristics().len(), 2);
        assert!(demo_audio::SPEC.advertise);

        let audio_char = demo_audio::Characteristic::audio_data.spec();
        assert_eq!(audio_char.name, "audio_data");
        assert_eq!(audio_char.uuid, "814b9b7c-25fd-4acd-8604-d28877beee6e");

        assert!(demo_audio::SPEC.find_characteristic("codec_format").is_some());

        let mut registry = FakeRegistry;
        demo_audio::register(&mut registry);
    }

    omi_config!(
        #[derive(Debug)]
        struct DemoConfig {
            sample_rate_hz: u32 = default(44100) => "CONFIG_OMI_SAMPLE_RATE",
            enable_leds: bool = default(true) => "CONFIG_OMI_ENABLE_LEDS",
        }
    );

    #[test]
    fn config_macro_loads_defaults() {
        let cfg = DemoConfig::load();
        assert_eq!(cfg.sample_rate_hz, 44100);
        assert!(cfg.enable_leds);

        let spec = DemoConfig::spec();
        assert_eq!(spec.name, "DemoConfig");
        assert_eq!(spec.fields.len(), 2);
        let enable_field = &spec.fields[1];
        assert_eq!(enable_field.field, "enable_leds");
        assert_eq!(enable_field.symbol, "CONFIG_OMI_ENABLE_LEDS");
        assert_eq!(enable_field.default, Some("true"));

        let defaults = DemoConfig::default();
        assert_eq!(defaults.sample_rate_hz, 44100);
    }

    #[test]
    fn guard_macro_short_circuits() {
        fn ensure_under_limit(value: u8) -> Result<(), &'static str> {
            omi_guard!(value < 10, "too-large", "ensure_under_limit", "value");
            Ok(())
        }

        assert!(ensure_under_limit(5).is_ok());
        assert!(matches!(ensure_under_limit(42), Err("too-large")));
    }

    omi_ffi_export!(
        fn ffi_checked_add(a: i32, b: i32) -> i32 {
            if let Some(sum) = a.checked_add(b) {
                Ok(sum)
            } else {
                Err("overflow")
            }
        } catch -1
    );

    #[test]
    fn ffi_macro_wraps_result() {
        assert_eq!(ffi_checked_add(2, 3), 5);
        assert_eq!(ffi_checked_add(i32::MAX, 1), -1);
    }
}
