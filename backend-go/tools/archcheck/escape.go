package main

import (
	"fmt"
	"go/ast"
	"go/token"
	"go/types"
	"slices"
)

func typedCapability(t types.Type, queuePath string) bool {
	seen := make(map[types.Type]bool)
	for t != nil {
		t = types.Unalias(t)
		if named, ok := t.(*types.Named); ok && named.Obj().Pkg() != nil &&
			named.Obj().Pkg().Path() == queuePath && slices.Contains(capabilities, named.Obj().Name()) {
			return true
		}
		ptr, ok := t.Underlying().(*types.Pointer)
		if !ok || seen[t] { // A named pointer type can refer back to itself.
			return false
		}
		seen[t] = true
		t = ptr.Elem()
	}
	return false
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
		if sel, ok := n.(*ast.SelectorExpr); ok && boundCapabilityMethod(sel, info, queuePath) {
			call, _ := enclosingCall(stack)
			if call == nil || ast.Unparen(call.Fun) != sel {
				report(sel)
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
	sel, ok := ast.Unparen(call.Fun).(*ast.SelectorExpr)
	return ok && boundCapabilityMethod(sel, info, queuePath)
}

func transfersCapability(expr ast.Expr, info *types.Info, queuePath string) bool {
	if typedCapability(info.TypeOf(expr), queuePath) {
		return true
	}
	expr = ast.Unparen(expr)
	if conversion, ok := expr.(*ast.CallExpr); ok && info.Types[conversion.Fun].IsType() && len(conversion.Args) == 1 {
		return transfersCapability(conversion.Args[0], info, queuePath)
	}
	return false
}

// A bound method keeps the receiver even after assignment erases its type from
// the call site. Check at the selection, before a function value can travel.
func boundCapabilityMethod(sel *ast.SelectorExpr, info *types.Info, queuePath string) bool {
	_, method := info.Uses[sel.Sel].(*types.Func)
	return method && !info.Types[sel.X].IsType() && typedCapability(info.TypeOf(sel.X), queuePath)
}

// enclosingCall ignores parentheses and reports whether go starts the call.
func enclosingCall(stack []ast.Node) (*ast.CallExpr, bool) {
	i := len(stack) - 1
	for i >= 0 {
		if _, parens := stack[i].(*ast.ParenExpr); !parens {
			break
		}
		i--
	}
	if i < 1 {
		return nil, false
	}
	call, ok := stack[i].(*ast.CallExpr)
	if !ok {
		return nil, false
	}
	_, async := stack[i-1].(*ast.GoStmt)
	return call, async
}

func synchronousLiteral(lit *ast.FuncLit, stack []ast.Node, info *types.Info, queuePath string) bool {
	call, async := enclosingCall(stack)
	if call == nil || async {
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
