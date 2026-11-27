package docstore

import (
	"errors"
	"strings"

	"cloud.google.com/go/firestore/apiv1/firestorepb"
	"google.golang.org/protobuf/proto"
)

var errValueMap = errors.New("docstore: invalid stored value map")

// ErrValueMapSize signals that a prepared field update needs a larger payload
// than the caller can publish in one transaction.
var ErrValueMapSize = errors.New("docstore: prepared value map exceeds byte budget")

// DecodeValueMap reads the Firestore wire values used in prepared transcript
// and notes fields. Unsupported types fail closed.
func DecodeValueMap(data []byte) (map[string]any, error) {
	msg, err := parseValueMap(data)
	if err != nil {
		return nil, err
	}
	fields, ok := decodeFields(msg.GetFields())
	if !ok {
		return nil, errValueMap
	}
	return fields, nil
}

// PatchNestedValueMap changes the named children of an existing stored map.
// Other wire values remain in their original Firestore types.
func PatchNestedValueMap(data []byte, parent string, updates map[string]any, maxBytes int) ([]byte, error) {
	msg, err := parseValueMap(data)
	if err != nil {
		return nil, err
	}
	nested := msg.GetFields()[parent].GetMapValue()
	if nested == nil {
		return nil, errValueMap
	}
	if nested.Fields == nil {
		nested.Fields = make(map[string]*firestorepb.Value, len(updates))
	}
	for key, value := range updates {
		encoded, ok := encodeMapUpdate(value)
		if !ok || key == "" || strings.Contains(key, ".") {
			return nil, errValueMap
		}
		nested.Fields[key] = encoded
	}
	if proto.Size(msg) > maxBytes {
		return nil, ErrValueMapSize
	}
	return (proto.MarshalOptions{Deterministic: true}).Marshal(msg)
}

func parseValueMap(data []byte) (*firestorepb.MapValue, error) {
	msg := &firestorepb.MapValue{}
	if err := (proto.UnmarshalOptions{RecursionLimit: 64}).Unmarshal(data, msg); err != nil {
		return nil, errValueMap
	}
	return msg, nil
}

// These are the types written by the finalizer's title, overview and sections
// patches. Other stored types are retained directly by PatchNestedValueMap.
func encodeMapUpdate(value any) (*firestorepb.Value, bool) {
	switch v := value.(type) {
	case string:
		return stringValue(v), true
	case []map[string]any:
		items := make([]*firestorepb.Value, 0, len(v))
		for _, entry := range v {
			fields := make(map[string]*firestorepb.Value, len(entry))
			for key, child := range entry {
				str, ok := child.(string)
				if !ok {
					return nil, false
				}
				fields[key] = stringValue(str)
			}
			items = append(items, &firestorepb.Value{
				ValueType: &firestorepb.Value_MapValue{MapValue: &firestorepb.MapValue{Fields: fields}},
			})
		}
		return &firestorepb.Value{ValueType: &firestorepb.Value_ArrayValue{ArrayValue: &firestorepb.ArrayValue{Values: items}}}, true
	default:
		return nil, false
	}
}

func stringValue(s string) *firestorepb.Value {
	return &firestorepb.Value{ValueType: &firestorepb.Value_StringValue{StringValue: s}}
}

func decodeFields(fields map[string]*firestorepb.Value) (map[string]any, bool) {
	result := make(map[string]any, len(fields))
	for name, value := range fields {
		decoded, ok := decodeValue(value)
		if !ok {
			return nil, false
		}
		result[name] = decoded
	}
	return result, true
}

func decodeValue(value *firestorepb.Value) (any, bool) {
	switch v := value.GetValueType().(type) {
	case *firestorepb.Value_NullValue:
		return nil, true
	case *firestorepb.Value_BooleanValue:
		return v.BooleanValue, true
	case *firestorepb.Value_IntegerValue:
		return v.IntegerValue, true
	case *firestorepb.Value_DoubleValue:
		return v.DoubleValue, true
	case *firestorepb.Value_StringValue:
		return v.StringValue, true
	case *firestorepb.Value_BytesValue:
		return v.BytesValue, true
	case *firestorepb.Value_TimestampValue:
		if err := v.TimestampValue.CheckValid(); err != nil {
			return nil, false
		}
		return v.TimestampValue.AsTime(), true
	case *firestorepb.Value_MapValue:
		return decodeFields(v.MapValue.GetFields())
	case *firestorepb.Value_ArrayValue:
		items := v.ArrayValue.GetValues()
		result := make([]any, len(items))
		for i, item := range items {
			decoded, ok := decodeValue(item)
			if !ok {
				return nil, false
			}
			result[i] = decoded
		}
		return result, true
	case nil, *firestorepb.Value_FieldReferenceValue, *firestorepb.Value_FunctionValue,
		*firestorepb.Value_GeoPointValue, *firestorepb.Value_PipelineValue,
		*firestorepb.Value_ReferenceValue, *firestorepb.Value_VariableReferenceValue:
		return nil, false
	}
	return nil, false
}
