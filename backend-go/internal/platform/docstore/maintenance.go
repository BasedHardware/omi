package docstore

import (
	"context"
	"strings"

	"cloud.google.com/go/firestore"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// UpdateMaintenance commits a retryable update to a global maintenance
// checkpoint. It cannot address tenant documents.
func (s *Store) UpdateMaintenance(ctx context.Context, id string, apply func(map[string]any) map[string]any) error {
	path, err := Doc("maintenance", id)
	if err != nil {
		return err
	}
	ref := s.client.Doc(path.path)
	return classify(s.client.RunTransaction(ctx, func(_ context.Context, tx *firestore.Transaction) error {
		snapshot, readErr := tx.Get(ref)
		if readErr != nil && status.Code(readErr) != codes.NotFound {
			return readErr
		}
		row := make(map[string]any)
		if readErr == nil {
			row = snapshot.Data()
		}
		fields := apply(row)
		if len(fields) == 0 {
			return nil
		}
		paths := make([]firestore.FieldPath, 0, len(fields))
		for key := range fields {
			paths = append(paths, firestore.FieldPath{key})
		}
		return tx.Set(ref, fields, firestore.Merge(paths...))
	}))
}

// ScanOrder specifies indexed field ordering for bounded collection-group scans.
type ScanOrder struct {
	Field      string
	Descending bool
}

// GroupScan selects indexed fields. Ties are ordered by document path. Cursor
// values must match Orders, followed by the stored relative document path.
type GroupScan struct {
	Collection string
	Filters    []Filter
	Orders     []ScanOrder
	Fields     []string
	After      []any
	AfterPath  string
	Limit      int
}

// ScanRow contains indexed metadata rather than an unrestricted document.
type ScanRow struct {
	Path   string
	Fields map[string]any
}

// ScanGroup reads one bounded page of projected metadata.
func (s *Store) ScanGroup(ctx context.Context, scan GroupScan) ([]ScanRow, error) {
	return s.scanProjected(ctx, scan, true)
}

// ScanCollection reads one bounded page from an explicitly named root collection.
func (s *Store) ScanCollection(ctx context.Context, scan GroupScan) ([]ScanRow, error) {
	return s.scanProjected(ctx, scan, false)
}

func (s *Store) scanProjected(ctx context.Context, scan GroupScan, group bool) ([]ScanRow, error) {
	if scan.Limit <= 0 || scan.Limit > 500 || scan.Collection == "" || strings.Contains(scan.Collection, "/") || len(scan.Fields) == 0 {
		return nil, ErrPath
	}
	q := s.client.Collection(scan.Collection).Select(scan.Fields...)
	if group {
		q = s.client.CollectionGroup(scan.Collection).Select(scan.Fields...)
	}
	for _, f := range scan.Filters {
		q = q.Where(f.Field, f.Operator, f.Value)
	}
	for _, order := range scan.Orders {
		direction := firestore.Asc
		if order.Descending {
			direction = firestore.Desc
		}
		q = q.OrderBy(order.Field, direction)
	}
	q = q.OrderBy(firestore.DocumentID, firestore.Asc)
	if scan.AfterPath != "" {
		ref := s.client.Doc(scan.AfterPath)
		if ref == nil || len(scan.After) != len(scan.Orders) {
			return nil, ErrPath
		}
		values := append(append([]any(nil), scan.After...), ref)
		q = q.StartAfter(values...)
	}
	rows, err := q.Limit(scan.Limit).Documents(ctx).GetAll()
	if err != nil {
		return nil, classify(err)
	}
	result := make([]ScanRow, 0, len(rows))
	for _, row := range rows {
		_, path, _ := strings.Cut(row.Ref.Path, "/documents/")
		result = append(result, ScanRow{Path: path, Fields: row.Data()})
	}
	return result, nil
}
