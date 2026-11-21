package docstore

import (
	"errors"
	"strings"

	"google.golang.org/api/iterator"
)

// Filter is a Firestore field predicate.
type Filter struct {
	Field, Operator string
	Value           any
}

// HasChildMatching reads at most one matching child in this transaction.
func (t *Tx) HasChildMatching(parent Ref, collection string, filters ...Filter) (bool, error) {
	if collection == "" || strings.Contains(collection, "/") || collection == "." || collection == ".." {
		return false, ErrPath
	}
	query := t.store.client.Doc(parent.path).Collection(collection).Query
	for _, filter := range filters {
		query = query.Where(filter.Field, filter.Operator, filter.Value)
	}
	docs := t.tx.Documents(query.Limit(1))
	defer docs.Stop()
	_, err := docs.Next()
	if errors.Is(err, iterator.Done) {
		return false, nil
	}
	return err == nil, err
}
