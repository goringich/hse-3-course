cmake_minimum_required(VERSION 3.20)
project(ClangAstPluginLab1 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(LLVM REQUIRED CONFIG)
find_package(Clang REQUIRED CONFIG)

message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")
message(STATUS "Using ClangConfig.cmake in: ${Clang_DIR}")

add_library(FunctionInfoPlugin MODULE
  src/FunctionInfoPlugin.cpp
)

target_include_directories(FunctionInfoPlugin PRIVATE
  ${LLVM_INCLUDE_DIRS}
  ${CLANG_INCLUDE_DIRS}
)

target_compile_definitions(FunctionInfoPlugin PRIVATE
  ${LLVM_DEFINITIONS}
)

if(TARGET clang-cpp)
  target_link_libraries(FunctionInfoPlugin PRIVATE clang-cpp)
else()
  message(FATAL_ERROR "Target clang-cpp is required but was not found.")
endif()

set_target_properties(FunctionInfoPlugin PROPERTIES
  PREFIX ""
  OUTPUT_NAME "FunctionInfoPlugin"
)
