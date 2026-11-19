package main

import (
	"go/ast"
	"slices"
	"strings"
)

const queuePackage = "internal/queue"

// capabilities are the queue types that prove where a call is running. Guarded is made
// only by Run.Guard, Admitting only inside Store.Tenant, and Scope is the tenant scope
// itself.
var capabilities = []string{"Guarded", "Admitting", "Scope"}

// checkPorts enforces the two halves of "every external call is guarded".
//
// A family cannot do I/O itself (roles.go), so every call that leaves the process goes
// through one of its interfaces. Here: each interface method in a family that takes a
// context, and so can block on the outside world, must also take a capability. And nowhere
// outside the queue may a capability be made from nothing, stored, or minted with the
// test-only constructors, because a kept capability outlives the guard it proves.
func checkPorts(t *tree) []string {
	var problems []string
	for _, s := range t.sources {
		if s.test {
			continue
		}
		alias := queueAlias(t.module, s)
		if roleOf(s.dir) == roleFamily {
			problems = append(problems, portMethods(s, alias)...)
		}
		if roleOf(s.dir) != roleQueue && alias != "" {
			problems = append(problems, capabilityMisuse(s, alias)...)
		}
	}
	return problems
}

// queueAlias returns the name the file uses for the queue package, or "".
func queueAlias(module string, s source) string {
	for _, spec := range s.file.Imports {
		if strings.Trim(spec.Path.Value, `"`) != module+"/"+queuePackage {
			continue
		}
		if spec.Name != nil {
			return spec.Name.Name
		}
		return "queue"
	}
	return ""
}

func portMethods(s source, alias string) []string {
	var problems []string
	ast.Inspect(s.file, func(n ast.Node) bool {
		spec, ok := n.(*ast.TypeSpec)
		if !ok {
			return true
		}
		iface, ok := spec.Type.(*ast.InterfaceType)
		if !ok {
			return true
		}
		for _, method := range iface.Methods.List {
			fn, ok := method.Type.(*ast.FuncType)
			if !ok || len(method.Names) == 0 || !takesContext(fn) || mentionsCapability(fn.Params, alias) {
				continue
			}
			problems = append(problems, s.at(method.Pos(),
				"port method %s.%s takes a context but no queue.Guarded or queue.Admitting: a call that can leave "+
					"the process must be handed the proof that it runs inside Run.Guard or Store.Tenant",
				spec.Name.Name, method.Names[0].Name))
		}
		return true
	})
	return problems
}

func takesContext(fn *ast.FuncType) bool {
	if fn.Params == nil || len(fn.Params.List) == 0 {
		return false
	}
	sel, ok := fn.Params.List[0].Type.(*ast.SelectorExpr)
	if !ok {
		return false
	}
	pkg, ok := sel.X.(*ast.Ident)
	return ok && pkg.Name == "context" && sel.Sel.Name == "Context"
}

func mentionsCapability(node ast.Node, alias string) bool {
	found := false
	ast.Inspect(node, func(n ast.Node) bool {
		if isCapability(n, alias) {
			found = true
		}
		return !found
	})
	return found
}

func isCapability(n ast.Node, alias string) bool {
	sel, ok := n.(*ast.SelectorExpr)
	if !ok || alias == "" {
		return false
	}
	pkg, ok := sel.X.(*ast.Ident)
	if !ok || pkg.Name != alias {
		return false
	}
	return slices.Contains(capabilities, sel.Sel.Name)
}

func capabilityMisuse(s source, alias string) []string {
	var problems []string
	ast.Inspect(s.file, func(n ast.Node) bool {
		if lit, ok := n.(*ast.CompositeLit); ok && isCapability(lit.Type, alias) {
			problems = append(problems, s.at(lit.Pos(),
				"a queue capability is made only by the queue: take the one Run.Guard or Scope.Admitting gives you"))
		}
		if st, ok := n.(*ast.StructType); ok {
			for _, field := range st.Fields.List {
				if mentionsCapability(field.Type, alias) {
					problems = append(problems, s.at(field.Pos(),
						"a queue capability must not be stored in a struct: it is valid only until its guard returns"))
				}
			}
		}
		if sel, ok := n.(*ast.SelectorExpr); ok {
			pkg, isIdent := sel.X.(*ast.Ident)
			if isIdent && pkg.Name == alias && strings.HasSuffix(sel.Sel.Name, "ForTest") {
				problems = append(problems, s.at(sel.Pos(),
					"%s.%s is for tests: production code gets a capability only from the queue", alias, sel.Sel.Name))
			}
		}
		return true
	})
	return problems
}
