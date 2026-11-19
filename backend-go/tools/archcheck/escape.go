package main

import (
	"fmt"
	"go/ast"
	"go/token"
	"go/types"
	"slices"
)

func typedCapability(t types.Type, queuePath string) bool {
	if t == nil {
		return false
	}
	t = types.Unalias(t)
	if ptr, ok := t.(*types.Pointer); ok {
		t = types.Unalias(ptr.Elem())
	}
	named, ok := t.(*types.Named)
	return ok && named.Obj().Pkg() != nil && named.Obj().Pkg().Path() == queuePath &&
		slices.Contains(capabilities, named.Obj().Name())
}

// A literal can use capabilities declared inside it. A reference to an outer
// variable is a capture. Only immediate calls and queue.Scope.Subject's
// synchronous callback have a lifetime we can establish from the call site.
func capabilityEscapes(file *ast.File, fset *token.FileSet, info *types.Info, queuePath string) []string {
	var problems []string
	report := func(n ast.Node) {
		problems = append(problems, fmt.Sprintf("%s: queue capability may outlive its guard", fset.Position(n.Pos())))
	}
	ast.PreorderStack(file, nil, func(n ast.Node, stack []ast.Node) bool {
		if node, ok := n.(*ast.GoStmt); ok {
			if asyncCapability(node.Call, info, queuePath) {
				report(node)
			}
		}
		if node, ok := n.(*ast.FuncLit); ok {
			if synchronousLiteral(node, stack, info, queuePath) {
				return true
			}
			for child := range ast.Preorder(node.Body) {
				id, ok := child.(*ast.Ident)
				if !ok {
					continue
				}
				v, ok := info.Uses[id].(*types.Var)
				if ok && !v.IsField() && (v.Pos() < node.Pos() || v.Pos() > node.End()) && typedCapability(v.Type(), queuePath) {
					report(node)
					break
				}
			}
		}
		return true
	})
	return problems
}

// Arguments to a go call are evaluated synchronously. Passing g.Tenant()
// passes a string; passing g or its bound method hands the goroutine the guard.
func asyncCapability(call *ast.CallExpr, info *types.Info, queuePath string) bool {
	for _, arg := range call.Args {
		if transfersCapability(arg, info, queuePath) {
			return true
		}
	}
	return transfersCapability(call.Fun, info, queuePath)
}

func transfersCapability(expr ast.Expr, info *types.Info, queuePath string) bool {
	if typedCapability(info.TypeOf(expr), queuePath) {
		return true
	}
	expr = ast.Unparen(expr)
	if conversion, ok := expr.(*ast.CallExpr); ok && info.Types[conversion.Fun].IsType() && len(conversion.Args) == 1 {
		return transfersCapability(conversion.Args[0], info, queuePath)
	}
	sel, ok := expr.(*ast.SelectorExpr)
	return ok && !info.Types[sel.X].IsType() && typedCapability(info.TypeOf(sel.X), queuePath)
}

func synchronousLiteral(lit *ast.FuncLit, stack []ast.Node, info *types.Info, queuePath string) bool {
	i := len(stack) - 1
	for i >= 0 {
		if _, parens := stack[i].(*ast.ParenExpr); !parens {
			break
		}
		i--
	}
	if i < 1 {
		return false
	}
	call, ok := stack[i].(*ast.CallExpr)
	if !ok {
		return false
	}
	if _, async := stack[i-1].(*ast.GoStmt); async {
		return false
	}
	if ast.Unparen(call.Fun) == lit {
		return true
	}
	sel, ok := ast.Unparen(call.Fun).(*ast.SelectorExpr)
	if !ok {
		return false
	}
	method, ok := info.Uses[sel.Sel].(*types.Func)
	return ok && method.FullName() == "(*"+queuePath+".Scope).Subject"
}
