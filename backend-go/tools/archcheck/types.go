// Type-sensitive checks use the active build's files and compiler export data.
// Let go list resolve modules and build constraints, just as go vet does.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"go/ast"
	"go/importer"
	"go/parser"
	"go/token"
	"go/types"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

type buildPackage struct {
	ImportPath string   `json:"ImportPath"`
	Dir        string   `json:"Dir"`
	Export     string   `json:"Export"`
	GoFiles    []string `json:"GoFiles"`
	DepOnly    bool     `json:"DepOnly"`
}

func checkTypes(ctx context.Context, root, module string) ([]string, error) {
	cmd := exec.CommandContext(ctx, "go", "list", "-deps", "-export", "-json=ImportPath,Dir,Export,GoFiles,DepOnly", "./...")
	cmd.Dir = root
	cmd.Stderr = os.Stderr
	data, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("list package export data: %w", err)
	}
	archives := make(map[string]string)
	var local []buildPackage
	dec := json.NewDecoder(bytes.NewReader(data))
	for {
		var pkg buildPackage
		err = dec.Decode(&pkg)
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, err
		}
		archives[pkg.ImportPath] = pkg.Export
		if !pkg.DepOnly {
			local = append(local, pkg)
		}
	}
	fset := token.NewFileSet()
	cfg := types.Config{Importer: importer.ForCompiler(fset, "gc", func(path string) (io.ReadCloser, error) {
		return os.Open(archives[path])
	})}
	var problems []string
	for _, pkg := range local {
		dir := strings.TrimPrefix(pkg.ImportPath, module+"/")
		switch roleOf(dir) {
		case roleQueue, roleRoot, roleFamily, roleAdapter, roleConformance:
			found, err := checkPackage(pkg, fset, &cfg, module+"/"+queuePackage)
			if err != nil {
				return nil, err
			}
			problems = append(problems, found...)
		case roleNone, roleRules, rolePlatform, roleTool:
		}
	}
	return problems, nil
}

func checkPackage(build buildPackage, fset *token.FileSet, cfg *types.Config, queuePath string) ([]string, error) {
	var files []*ast.File
	for _, name := range build.GoFiles {
		file, err := parser.ParseFile(fset, filepath.Join(build.Dir, name), nil, parser.SkipObjectResolution)
		if err != nil {
			return nil, err
		}
		files = append(files, file)
	}
	info := &types.Info{Uses: make(map[*ast.Ident]types.Object), Types: make(map[ast.Expr]types.TypeAndValue)}
	pkg, err := cfg.Check(build.ImportPath, fset, files, info)
	if err != nil {
		return nil, err
	}
	var problems []string
	for _, file := range files {
		problems = append(problems, capabilityEscapes(file, fset, info, queuePath)...)
		if pkg.Path() == queuePath {
			problems = append(problems, closedLists(file, pkg, info)...)
		}
	}
	return problems, nil
}
