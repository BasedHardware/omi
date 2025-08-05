"""
Python representation for SIMD types in (Objective)C

This module only defines the vector types that are
used in framework bindings.
"""

import objc
import operator

__all__ = (
    "simd_int2",
    "simd_int3",
    "simd_int4",
    "simd_uint2",
    "simd_uint3",
    "simd_double2",
    "simd_double3",
    "simd_double4",
    "simd_float2",
    "simd_float3",
    "simd_float4",
    "simd_short2",
    "simd_ushort2",
    "simd_ushort3",
    "simd_ushort4",
    "simd_uchar16",
    "vector_float2",
    "vector_float3",
    "vector_float4",
    "vector_double2",
    "vector_double3",
    "vector_double4",
    "vector_short2",
    "vector_ushort2",
    "vector_ushort3",
    "vector_ushort4",
    "vector_int2",
    "vector_int3",
    "vector_int4",
    "vector_uint2",
    "vector_uint3",
    "vector_uchar16",
    "matrix_float2x2",
    "matrix_float3x3",
    "matrix_float4x3",
    "matrix_float4x4",
    "matrix_double4x4",
    "simd_quatf",
    "simd_quatd",
    "simd_float4x4",
)


def make_type(
    name,
    zero,
    cast_type,
    count,
    len2_type=None,
    len3_type=None,
    is_signed=True,
    limitrange=lambda x: x,
    typestr=None,
):
    assert typestr is not None
    assert count > 0
    if count in (3, 4):
        assert len2_type is not None
    if count == 4:
        assert len3_type is not None

    if count > 4:

        def __init__(self, *values):
            if len(values) == 0:
                self._values = [zero] * count

            elif len(values) == 1:
                v = values[0]
                v = cast_type(v)

                self._values = [v] * count
            elif len(values) != count:
                raise ValueError(values)

            else:
                self._values = [limitrange(cast_type(v)) for v in values]

    else:

        def __init__(self, *values):
            if len(values) == 0:
                self._values = [zero] * count
                return

            parts = []
            for p in values:
                if isinstance(p, self.__class__):
                    parts.extend(p._values)
                elif len2_type is not None and isinstance(p, len2_type):
                    parts.extend(p._values)
                elif len3_type is not None and isinstance(p, len3_type):
                    parts.extend(p._values)
                else:
                    parts.append(cast_type(p))

            if len(parts) == 1:
                self._values = parts * count

            elif len(parts) == count:
                self._values = parts

            else:
                raise ValueError(f"Expecting {count} values, got {len(parts)}")

            self._values = [limitrange(v) for v in self._values]

    def as_tuple(self):
        return tuple(self._values)

    def __repr__(self):
        return f"objc.simd.{name}({', '.join(map(str, self._values))})"

    def _objc_literal(self):
        return f"({name}){{{', '.join(map(str, self._values))}}}"

    def __len__(self):
        return count

    def __getitem__(self, idx):
        return self._values[idx]

    def __setitem__(self, idx, value):
        if not isinstance(idx, int):
            raise TypeError(idx)
        self._values[idx] = cast_type(value)

    def _cast_self(self, other):
        if not isinstance(other, self.__class__):
            try:
                return self.__class__(cast_type(other))
            except (ValueError, TypeError):
                return NotImplemented

        return other

    def __add__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self.__class__(*(limitrange(x + y) for x, y in zip(self, other)))

    def __radd__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self.__class__(*(limitrange(y + x) for x, y in zip(self, other)))

    def __mul__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self.__class__(*(limitrange(x * y) for x, y in zip(self, other)))

    def __rmul__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self.__class__(*(limitrange(y * x) for x, y in zip(self, other)))

    def __matmul__(self, other: "vector_float2") -> "vector_float2":
        if not isinstance(other, self.__class__):
            return NotImplemented

        return sum(x * y for x, y in zip(self, other))

    def __abs__(self):
        return self.__class__(*(abs(x) for x in self._values))

    def __eq__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self._values == other._values

    def __ne__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self._values != other._values

    def __lt__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self._values < other._values

    def __le__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self._values <= other._values

    def __gt__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self._values > other._values

    def __ge__(self, other):
        other = self._cast_self(other)
        if other is NotImplemented:
            return NotImplemented

        return self._values >= other._values

    def __neg__(self):
        return self.__class__(*(-n for n in self._values))

    def __pos__(self):
        return self.__class__(self)

    class_dict = {
        "__slots__": ("_values",),
        "__init__": __init__,
        "as_tuple": as_tuple,
        "_cast_self": _cast_self,
        "__repr__": __repr__,
        "_objc_literal": _objc_literal,
        "__len__": __len__,
        "__getitem__": __getitem__,
        "__setitem__": __setitem__,
        "__add__": __add__,
        "__radd__": __radd__,
        "__mul__": __mul__,
        "__rmul__": __rmul__,
        "__matmul__": __matmul__,
        "__abs__": __abs__,
        "__eq__": __eq__,
        "__ne__": __ne__,
        "__lt__": __lt__,
        "__le__": __le__,
        "__gt__": __gt__,
        "__ge__": __ge__,
    }

    if is_signed:
        class_dict.update(
            {
                "__neg__": __neg__,
                "__pos__": __pos__,
            }
        )

    if 2 <= count <= 4:

        @property
        def x(self):
            return self._values[0]

        @x.setter
        def x(self, value):
            self._values[0] = cast_type(value)

        @property
        def y(self):
            return self._values[1]

        @y.setter
        def y(self, value):
            self._values[1] = cast_type(value)

        class_dict["x"] = x
        class_dict["y"] = y

    if count == 2:

        @property
        def xy(self):
            return self.__class__(*self._values)

        @xy.setter
        def xy(self, value):
            if not isinstance(value, self.__class__):
                raise TypeError(value)
            self._values[:] = value._values[:]

        class_dict["xy"] = xy

    elif count in (3, 4):

        @property
        def z(self):
            return self._values[2]

        @z.setter
        def z(self, value):
            self._values[2] = cast_type(value)

        class_dict["z"] = z

        @property
        def xy(self):
            return len2_type(*self._values[0:2])

        @xy.setter
        def xy(self, value):
            if not isinstance(value, len2_type):
                raise TypeError(value)
            self._values[0:2] = value._values[0:2]

        class_dict["xy"] = xy

        @property
        def yz(self):
            return len2_type(*self._values[1:3])

        @yz.setter
        def yz(self, value):
            if not isinstance(value, len2_type):
                raise TypeError(value)
            self._values[1:3] = value._values[:]

        class_dict["yz"] = yz

    if count == 3:

        @property
        def xyz(self):
            return self.__class__(*self._values[0:3])

        @xyz.setter
        def xyz(self, value):
            if not isinstance(value, self.__class__):
                raise TypeError(value)
            self._values[0:3] = value._values[:]

        class_dict["xyz"] = xyz

    if count == 4:

        @property
        def xyz(self):
            return len3_type(*self._values[0:3])

        @xyz.setter
        def xyz(self, value):
            if not isinstance(value, len3_type):
                raise TypeError(value)
            self._values[0:3] = value._values[:]

        class_dict["xyz"] = xyz

        @property
        def w(self):
            return self._values[3]

        @w.setter
        def w(self, value):
            self._values[3] = cast_type(value)

        class_dict["w"] = w

        @property
        def zw(self):
            return len2_type(*self._values[2:4])

        @zw.setter
        def zw(self, value):
            if not isinstance(value, len2_type):
                raise TypeError(value)
            self._values[2:4] = value._values[:]

        class_dict["zw"] = zw

        @property
        def yzw(self):
            return len3_type(*self._values[1:4])

        @yzw.setter
        def yzw(self, value):
            if not isinstance(value, len3_type):
                raise TypeError(value)
            self._values[1:4] = value._values[:]

        class_dict["yzw"] = yzw

        @property
        def xyzw(self):
            return self.__class__(*self._values)

        @xyzw.setter
        def xyzw(self, value):
            if not isinstance(value, self.__class__):
                raise TypeError(value)
            self._values[:] = value._values[:]

        class_dict["xyzw"] = xyzw

    class_dict["__typestr__"] = typestr

    result = type(name, (object,), class_dict)
    objc._registerVectorType(result)
    return result


vector_float2 = make_type("vector_float2", 0.0, float, 2, typestr=b"<2f>")
vector_float3 = make_type(
    "vector_float3", 0.0, float, 3, vector_float2, typestr=b"<3f>"
)
vector_float4 = make_type(
    "vector_float4", 0.0, float, 4, vector_float2, vector_float3, typestr=b"<4f>"
)

vector_double2 = make_type("vector_double2", 0.0, float, 2, typestr=b"<2d>")
vector_double3 = make_type(
    "vector_double3", 0.0, float, 3, vector_double2, typestr=b"<3d>"
)
vector_double4 = make_type(
    "vector_double4", 0.0, float, 4, vector_double2, vector_double3, typestr=b"<4d>"
)


def limit_short(v):
    v = v & 0xFFFF
    if v & 0x8000:
        v = ~v + 1 & 0xFFFF
        return -v
    else:
        return v


def limit_int(v):
    v = v & 0xFFFFFFFF
    if v & 0x80000000:
        v = ~v + 1 & 0xFFFFFFFF
        return -v
    else:
        return v


def limit_uchar(v):
    return v % 0xFF


def limit_ushort(v):
    return v % 0xFFFF


def limit_uint(v):
    return v % 0xFFFFFFFF


vector_short2 = make_type(
    "vector_short2", 0, operator.index, 2, limitrange=limit_short, typestr=b"<2s>"
)
vector_ushort2 = make_type(
    "vector_ushort2",
    0,
    operator.index,
    2,
    is_signed=False,
    limitrange=limit_ushort,
    typestr=b"<2S>",
)
vector_ushort3 = make_type(
    "vector_ushort3",
    0,
    operator.index,
    3,
    vector_ushort2,
    is_signed=False,
    limitrange=limit_ushort,
    typestr=b"<3S>",
)
vector_ushort4 = make_type(
    "vector_ushort4",
    0,
    operator.index,
    4,
    vector_ushort2,
    vector_ushort3,
    is_signed=False,
    limitrange=limit_ushort,
    typestr=b"<4S>",
)

vector_int2 = make_type(
    "vector_int2", 0, operator.index, 2, limitrange=limit_int, typestr=b"<2i>"
)
vector_int3 = make_type(
    "vector_int3",
    0,
    operator.index,
    3,
    vector_int2,
    limitrange=limit_int,
    typestr=b"<3i>",
)
vector_int4 = make_type(
    "vector_int4",
    0,
    operator.index,
    4,
    vector_int2,
    vector_int3,
    limitrange=limit_int,
    typestr=b"<4i>",
)
vector_uint2 = make_type(
    "vector_uint2",
    0,
    operator.index,
    2,
    is_signed=False,
    limitrange=limit_uint,
    typestr=b"<2I>",
)
vector_uint3 = make_type(
    "vector_uint3",
    0,
    operator.index,
    3,
    vector_uint2,
    is_signed=False,
    limitrange=limit_uint,
    typestr=b"<3I>",
)

vector_uchar16 = make_type(
    "vector_uchar16",
    0,
    operator.index,
    16,
    is_signed=False,
    limitrange=limit_uchar,
    typestr=b"<16C>",
)

simd_int2 = vector_int2
simd_int3 = vector_int3
simd_int4 = vector_int4
simd_uint2 = vector_uint2
simd_uint3 = vector_uint3
simd_float2 = vector_float2
simd_float3 = vector_float3
simd_float4 = vector_float4
simd_double2 = vector_double2
simd_double3 = vector_double3
simd_double4 = vector_double4
simd_short2 = vector_short2
simd_ushort2 = vector_ushort2
simd_ushort3 = vector_ushort3
simd_ushort4 = vector_ushort4
simd_uchar16 = vector_uchar16


simd_quatf = objc.createStructType("simd_quatf", b"{simd_quatf=<4f>}", ["vector"])
simd_quatd = objc.createStructType("simd_quatd", b"{simd_quatd=<4d>}", ["vector"])

simd_float2x2 = objc.createStructType(
    "simd_float2x2", b"{simd_float2x2=[2<2f>]}", ["columns"]
)
simd_float3x3 = objc.createStructType(
    "simd_float3x3", b"{simd_float3x3=[3<3f>]}", ["columns"]
)
simd_float4x4 = objc.createStructType(
    "simd_float4x4", b"{simd_float4x4=[4<4f>]}", ["columns"]
)
simd_float4x3 = objc.createStructType(
    "simd_float4x3", b"{simd_float4x3=[4<3f>]}", ["columns"]
)
simd_double4x4 = objc.createStructType(
    "simd_double4x4", b"{simd_double4x4=[4<4d>]}", ["columns"]
)
simd_double3x3 = objc.createStructType(
    "simd_double3x3", b"{simd_double3x3=[3<3d>]}", ["columns"]
)
simd_double4x3 = objc.createStructType(
    "simd_double4x3", b"{simd_double4x3=[4<3d>]}", ["columns"]
)

# Aliases for compatibility with system headers:
matrix_float2x2 = simd_float2x2
matrix_float3x3 = simd_float3x3
matrix_float4x3 = simd_float4x3
matrix_float4x4 = simd_float4x4
matrix_double3x3 = simd_double3x3
matrix_double4x4 = simd_double4x4
matrix_double4x3 = simd_double4x3
