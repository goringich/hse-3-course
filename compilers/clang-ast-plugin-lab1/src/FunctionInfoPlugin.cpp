#include "clang/AST/ASTConsumer.h"
#include "clang/AST/Decl.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendPluginRegistry.h"
#include "clang/Lex/Preprocessor.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/Support/raw_ostream.h"
#include <memory>
#include <string>
#include <vector>

using namespace clang;

namespace {

class FunctionInfoVisitor : public RecursiveASTVisitor<FunctionInfoVisitor> {
public:
  explicit FunctionInfoVisitor(ASTContext &Context, bool IncludeDeclarations)
      : Context(Context), IncludeDeclarations(IncludeDeclarations) {}

  bool VisitFunctionDecl(FunctionDecl *FD) {
    if (!FD->getLocation().isValid()) {
      return true;
    }

    const SourceManager &SM = Context.getSourceManager();
    if (!SM.isWrittenInMainFile(SM.getSpellingLoc(FD->getLocation()))) {
      return true;
    }

    if (!IncludeDeclarations && !FD->isThisDeclarationADefinition()) {
      return true;
    }

    llvm::outs() << "function: " << FD->getQualifiedNameAsString() << "\n";
    llvm::outs() << "  return type: " << FD->getReturnType().getAsString()
                 << "\n";
    llvm::outs() << "  parameters: " << FD->getNumParams() << "\n";

    for (unsigned Index = 0; Index < FD->getNumParams(); ++Index) {
      const ParmVarDecl *Param = FD->getParamDecl(Index);
      const std::string ParamName =
          Param->getName().empty() ? "<anonymous>" : Param->getNameAsString();
      llvm::outs() << "    [" << Index << "] " << ParamName << ": "
                   << Param->getType().getAsString() << "\n";
    }

    PresumedLoc Loc = SM.getPresumedLoc(FD->getLocation());
    llvm::outs() << "  location: " << Loc.getFilename() << ":" << Loc.getLine()
                 << ":" << Loc.getColumn() << "\n";
    llvm::outs() << "  kind: "
                 << (FD->isThisDeclarationADefinition() ? "definition"
                                                        : "declaration")
                 << "\n\n";
    return true;
  }

private:
  ASTContext &Context;
  bool IncludeDeclarations;
};

class FunctionInfoConsumer : public ASTConsumer {
public:
  explicit FunctionInfoConsumer(ASTContext &Context, bool IncludeDeclarations)
      : Visitor(Context, IncludeDeclarations) {}

  void HandleTranslationUnit(ASTContext &Context) override {
    Visitor.TraverseDecl(Context.getTranslationUnitDecl());
  }

private:
  FunctionInfoVisitor Visitor;
};

class FunctionInfoPluginAction : public PluginASTAction {
public:
  FunctionInfoPluginAction() = default;

protected:
  std::unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &CI,
                                                 llvm::StringRef) override {
    return std::make_unique<FunctionInfoConsumer>(CI.getASTContext(),
                                                  IncludeDeclarations);
  }

  bool ParseArgs(const CompilerInstance &CI,
                 const std::vector<std::string> &Args) override {
    for (llvm::StringRef Arg : Args) {
      if (Arg == "help" || Arg == "--help") {
        PrintHelp(llvm::errs());
      } else if (Arg == "--include-decls") {
        IncludeDeclarations = true;
      } else {
        DiagnosticsEngine &D = CI.getDiagnostics();
        unsigned DiagID =
            D.getCustomDiagID(DiagnosticsEngine::Error,
                              "unknown FunctionInfoPlugin argument '%0'");
        D.Report(DiagID) << Arg;
        return false;
      }
    }

    return true;
  }

private:
  static void PrintHelp(llvm::raw_ostream &OS) {
    OS << "FunctionInfoPlugin options:\n"
       << "  --include-decls  print forward declarations too\n"
       << "  help, --help     show this message\n";
  }

  bool IncludeDeclarations = false;
};

} // namespace

static FrontendPluginRegistry::Add<FunctionInfoPluginAction>
    X("function-info", "print function signatures from the AST");
