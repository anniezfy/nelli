from textwrap import dedent
import difflib

from loopy.mlir import f64_t
from loopy.mlir.arith import constant
from loopy.mlir.func import mlir_func
from loopy.mlir.memref import aff_alloc
from loopy.mlir.scf import scf_if, scf_endif_branch, scf_else, scf_endif
from loopy.utils import mlir_mod_ctx


class TestIfs:
    def check_correct(self, correct, module):
        diff = list(
            difflib.unified_diff(
                str(module).splitlines(),
                str(correct).splitlines(),
                lineterm="",
            )
        )
        assert len(diff) == 0, "\n".join(diff)

    def test_without_rewriting_ast1(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=False)
            def ifs(M: f64_t, N: f64_t):
                one = constant(1.0)
                if scf_if(M < N):
                    one = constant(1.0)
                    mem = aff_alloc([10, 10], f64_t)
                    scf_endif_branch()
                else:
                    scf_else()
                    two = constant(2.0)
                    mem = aff_alloc([20, 20], f64_t)
                    scf_endif_branch()
                    scf_endif()

                return None

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 1.000000e+00 : f64
              %1 = memref.alloca() : memref<10x10xf64>
            } else {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<20x20xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)

    def test_without_rewriting_ast2(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=False)
            def ifs(M: f64_t, N: f64_t, K: f64_t, J: f64_t):
                one = constant(1.0)
                if scf_if(M < N):
                    two = constant(2.0)
                    mem = aff_alloc([3, 3], f64_t)
                    if scf_if(K < J):
                        four = constant(4.0)
                        mem = aff_alloc([5, 5], f64_t)

                        scf_endif_branch()
                        scf_endif()

                    if scf_if(K < J):
                        four = constant(4.0)
                        mem = aff_alloc([5, 5], f64_t)
                        scf_endif_branch()
                        scf_endif()

                    scf_endif_branch()
                else:
                    scf_else()
                    six = constant(6.0)
                    mem = aff_alloc([7, 7], f64_t)
                    scf_endif_branch()
                    scf_endif()

                # TODO(max): have to have this here
                return None

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64, %arg2: f64, %arg3: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<3x3xf64>
              %2 = arith.cmpf olt, %arg2, %arg3 : f64
              scf.if %2 {
                %cst_1 = arith.constant 4.000000e+00 : f64
                %4 = memref.alloca() : memref<5x5xf64>
              }
              %3 = arith.cmpf olt, %arg2, %arg3 : f64
              scf.if %3 {
                %cst_1 = arith.constant 4.000000e+00 : f64
                %4 = memref.alloca() : memref<5x5xf64>
              }
            } else {
              %cst_0 = arith.constant 6.000000e+00 : f64
              %1 = memref.alloca() : memref<7x7xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)

    def test_with_rewriting_ast1(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=True)
            def ifs(M: f64_t, N: f64_t):
                one = constant(1.0)
                if M < N:
                    two = constant(2.0)
                    mem = aff_alloc([3, 3], f64_t)

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<3x3xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)

    def test_with_rewriting_ast2(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=True)
            def ifs(M: f64_t, N: f64_t):
                one = constant(1.0)
                if M < N:
                    two = constant(2.0)
                    mem = aff_alloc([3, 3], f64_t)
                else:
                    six = constant(6.0)
                    mem = aff_alloc([7, 7], f64_t)

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<3x3xf64>
            } else {
              %cst_0 = arith.constant 6.000000e+00 : f64
              %1 = memref.alloca() : memref<7x7xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)

    def test_with_rewriting_ast3(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=True)
            def ifs(M: f64_t, N: f64_t):
                one = constant(1.0)
                if M < N:
                    two = constant(2.0)
                    mem = aff_alloc([3, 3], f64_t)
                else:
                    six = constant(6.0)
                    mem = aff_alloc([7, 7], f64_t)

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<3x3xf64>
            } else {
              %cst_0 = arith.constant 6.000000e+00 : f64
              %1 = memref.alloca() : memref<7x7xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)

    def test_with_rewriting_ast4(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=True)
            def ifs(M: f64_t, N: f64_t, K: f64_t, J: f64_t):
                one = constant(1.0)
                if M < N:
                    two = constant(2.0)
                    mem = aff_alloc([3, 3], f64_t)
                    if K < J:
                        four = constant(4.0)
                        mem = aff_alloc([5, 5], f64_t)
                else:
                    six = constant(6.0)
                    mem = aff_alloc([7, 7], f64_t)

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64, %arg2: f64, %arg3: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<3x3xf64>
              %2 = arith.cmpf olt, %arg2, %arg3 : f64
              scf.if %2 {
                %cst_1 = arith.constant 4.000000e+00 : f64
                %3 = memref.alloca() : memref<5x5xf64>
              }
            } else {
              %cst_0 = arith.constant 6.000000e+00 : f64
              %1 = memref.alloca() : memref<7x7xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)

    def test_with_rewriting_ast5(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=True)
            def ifs(M: f64_t, N: f64_t, K: f64_t, J: f64_t):
                one = constant(1.0)
                if M < N:
                    two = constant(2.0)
                    mem = aff_alloc([3, 3], f64_t)
                    if K < J:
                        four = constant(4.0)
                        mem = aff_alloc([5, 5], f64_t)
                    else:
                        four = constant(6.0)
                        mem = aff_alloc([7, 7], f64_t)
                else:
                    six = constant(8.0)
                    mem = aff_alloc([9, 9], f64_t)

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64, %arg2: f64, %arg3: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<3x3xf64>
              %2 = arith.cmpf olt, %arg2, %arg3 : f64
              scf.if %2 {
                %cst_1 = arith.constant 4.000000e+00 : f64
                %3 = memref.alloca() : memref<5x5xf64>
              } else {
                %cst_1 = arith.constant 6.000000e+00 : f64
                %3 = memref.alloca() : memref<7x7xf64>
              }
            } else {
              %cst_0 = arith.constant 8.000000e+00 : f64
              %1 = memref.alloca() : memref<9x9xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)

    def test_with_rewriting_ast6(self):
        with mlir_mod_ctx() as module:

            @mlir_func(rewrite_ast_=True)
            def ifs(M: f64_t, N: f64_t, K: f64_t, J: f64_t):
                one = constant(1.0)
                if M < N:
                    two = constant(2.0)
                    mem = aff_alloc([3, 3], f64_t)
                    if K < J:
                        four = constant(4.0)
                        mem = aff_alloc([5, 5], f64_t)
                    else:
                        four = constant(6.0)
                        mem = aff_alloc([7, 7], f64_t)

                    if K < J:
                        four = constant(8.0)
                        mem = aff_alloc([9, 9], f64_t)
                else:
                    six = constant(10.0)
                    mem = aff_alloc([11, 11], f64_t)

        correct = dedent(
            """\
        module {
          func.func @ifs(%arg0: f64, %arg1: f64, %arg2: f64, %arg3: f64) {
            %cst = arith.constant 1.000000e+00 : f64
            %0 = arith.cmpf olt, %arg0, %arg1 : f64
            scf.if %0 {
              %cst_0 = arith.constant 2.000000e+00 : f64
              %1 = memref.alloca() : memref<3x3xf64>
              %2 = arith.cmpf olt, %arg2, %arg3 : f64
              scf.if %2 {
                %cst_1 = arith.constant 4.000000e+00 : f64
                %4 = memref.alloca() : memref<5x5xf64>
              } else {
                %cst_1 = arith.constant 6.000000e+00 : f64
                %4 = memref.alloca() : memref<7x7xf64>
              }
              %3 = arith.cmpf olt, %arg2, %arg3 : f64
              scf.if %3 {
                %cst_1 = arith.constant 8.000000e+00 : f64
                %4 = memref.alloca() : memref<9x9xf64>
              }
            } else {
              %cst_0 = arith.constant 1.000000e+01 : f64
              %1 = memref.alloca() : memref<11x11xf64>
            }
            return
          }
        }
        """
        )
        self.check_correct(correct, module)