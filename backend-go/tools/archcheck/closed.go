package main

import (
	"fmt"
	"go/ast"
	"go/types"
	"slices"
)

// Listers are deliberately plain slices of constants. Compare constant
// objects, including unexported ones and declarations in other package files.
func closedLists(file *ast.File, pkg *types.Package, info *types.Info) []string {
	var problems []string
	for _, decl := range file.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if !ok || fn.Recv != nil || fn.Name.Name != "States" && fn.Name.Name != "Terminals" {
			continue
		}
		name := fn.Name.Name[:len(fn.Name.Name)-1]
		set := pkg.Scope().Lookup(name)
		var want, got []string
		for _, id := range pkg.Scope().Names() {
			c, ok := pkg.Scope().Lookup(id).(*types.Const)
			if ok && set != nil && types.Identical(c.Type(), set.Type()) {
				want = append(want, id)
			}
		}
		lit := returnedSlice(fn)
		if lit != nil {
			for _, item := range lit.Elts {
				id, ok := item.(*ast.Ident)
				if !ok || info.Uses[id] != pkg.Scope().Lookup(id.Name) {
					got = append(got, "<expression>")
				} else {
					got = append(got, id.Name)
				}
			}
		}
		slices.Sort(got)
		if lit == nil || !slices.Equal(got, want) {
			problems = append(problems, fmt.Sprintf("%s must list every %s constant once: got %v, want %v", fn.Name, name, got, want))
		}
	}
	return problems
}

func returnedSlice(fn *ast.FuncDecl) *ast.CompositeLit {
	if fn.Body == nil || len(fn.Body.List) != 1 {
		return nil
	}
	ret, ok := fn.Body.List[0].(*ast.ReturnStmt)
	if !ok || len(ret.Results) != 1 {
		return nil
	}
	lit, ok := ret.Results[0].(*ast.CompositeLit)
	if !ok {
		return nil
	}
	return lit
}
