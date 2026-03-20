# LLVM Lab 1: Simple Clang AST Plugin

This project contains a standalone Clang AST plugin for the LLVM lab.

The plugin is based on the official example:
- https://clang.llvm.org/docs/ClangPlugins.html
- https://github.com/llvm/llvm-project/tree/main/clang/examples/PrintFunctionNames

## What the plugin does

`FunctionInfoPlugin` walks through the AST of the main translation unit and
prints:

- function name
- return type
- parameter list
- source location
- whether the declaration is a definition or only a declaration

By default it prints only definitions. To include forward declarations too, pass
`--include-decls`.

## Build

```bash
cd /home/goringich/Desktop/hse/compilers/clang-ast-plugin-lab1
cmake -S . -B build -G Ninja
cmake --build build
```

## Run on the example file

```bash
cd /home/goringich/Desktop/hse/compilers/clang-ast-plugin-lab1
clang++ -fsyntax-only \
  -Xclang -load -Xclang ./build/FunctionInfoPlugin.so \
  -Xclang -plugin -Xclang function-info \
  ./test/sample.cpp
```

## Run with declarations included

```bash
cd /home/goringich/Desktop/hse/compilers/clang-ast-plugin-lab1
clang++ -fsyntax-only \
  -Xclang -load -Xclang ./build/FunctionInfoPlugin.so \
  -Xclang -plugin -Xclang function-info \
  -Xclang -plugin-arg-function-info -Xclang --include-decls \
  ./test/sample.cpp
```

This form uses the regular Clang driver and forwards plugin flags through
`-Xclang`, which works reliably with the system LLVM installation.

## Expected output shape

The output contains blocks like:

```text
function: sum
  return type: int
  parameters: 2
  location: .../sample.cpp:6:5
  kind: definition
```
