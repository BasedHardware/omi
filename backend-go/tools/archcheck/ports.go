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

// contextAlias returns the name the file uses for the context package, or "".
func contextAlias(s source) string {
	for _, spec := range s.file.Imports {
		if strings.Trim(spec.Path.Value, `"`) != "context" {
			continue
		}
		if spec.Name != nil {
			return spec.Name.Name
		}
		return "context"
	}
	return ""
}

// portMethods reports every way a family can declare "a call someone else implements" that
// takes a context and no capability: an interface method, a named function type, and a
// function-typed struct field or parameter. Function declarations and literals are the
// family's own code, which cannot do I/O, so they are not ports.
func portMethods(s source, alias string) []string {
	ctx := contextAlias(s)
	if ctx == "" {
		return nil
	}
	if ctx == "." || ctx == "_" {
		return []string{s.at(s.file.Pos(), "import context under its own name, so its uses can be checked")}
	}
	const need = "takes a context but no queue.Guarded or queue.Admitting: a call that can leave " +
		"the process must be handed the proof that it runs inside Run.Guard or Store.Tenant"
	var problems []string
	unguarded := func(t ast.Expr) bool {
		fn, ok := t.(*ast.FuncType)
		return ok && takesContext(fn, ctx) && !mentionsCapability(fn.Params, alias)
	}
	ast.Inspect(s.file, func(n ast.Node) bool {
		if spec, ok := n.(*ast.TypeSpec); ok {
			if isContextType(spec.Type, ctx) {
				problems = append(problems, s.at(spec.Pos(),
					"type %s renames context.Context: spell it out, so port checks can see it", spec.Name.Name))
			}
			if unguarded(spec.Type) {
				problems = append(problems, s.at(spec.Pos(), "function type %s %s", spec.Name.Name, need))
			}
			if iface, ok := spec.Type.(*ast.InterfaceType); ok {
				for _, method := range iface.Methods.List {
					if len(method.Names) != 0 && unguarded(method.Type) {
						problems = append(problems, s.at(method.Pos(), "port method %s.%s %s",
							spec.Name.Name, method.Names[0].Name, need))
					}
				}
				return false
			}
			return true
		}
		if field, ok := n.(*ast.Field); ok && unguarded(field.Type) {
			problems = append(problems, s.at(field.Pos(), "a function-typed field or parameter %s", need))
		}
		return true
	})
	return problems
}

func isContextType(t ast.Expr, ctx string) bool {
	sel, ok := t.(*ast.SelectorExpr)
	if !ok {
		return false
	}
	pkg, ok := sel.X.(*ast.Ident)
	return ok && pkg.Name == ctx && sel.Sel.Name == "Context"
}

// takesContext reports whether any parameter is a context.
func takesContext(fn *ast.FuncType, ctx string) bool {
	if fn.Params == nil {
		return false
	}
	for _, param := range fn.Params.List {
		if isContextType(param.Type, ctx) {
			return true
		}
	}
	return false
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
