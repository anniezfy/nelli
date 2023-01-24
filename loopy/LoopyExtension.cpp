#include "IRModule.h"
#include "affine_analysis.h"
#include "dylib.hpp"
#include "mlir-c/AffineExpr.h"
#include "mlir-c/Bindings/Python/Interop.h"
#include "mlir-c/RegisterEverything.h"
#include "mlir/Analysis/Presburger/MPInt.h"
#include "mlir/Bindings/Python/PybindAdaptors.h"
#include "mlir/CAPI/IR.h"
#include "mlir/CAPI/Registration.h"
#include "mlir/Dialect/Affine/Analysis/AffineAnalysis.h"
#include "mlir/Dialect/Affine/Analysis/AffineStructures.h"
#include "mlir/Dialect/Affine/Analysis/Utils.h"
#include "mlir/Dialect/Affine/IR/AffineOps.h"
#include "mlir/Dialect/Affine/IR/AffineValueMap.h"
#include "mlir/Dialect/Func/IR/FuncOps.h"
#include "mlir/IR/AffineExprVisitor.h"
#include "mlir/IR/AsmState.h"
#include "mlir/IR/Operation.h"
#include "tabulate.hpp"
#include <iostream>
#include <pybind11/functional.h>

namespace py = pybind11;
using namespace mlir::python;
using namespace mlir;
using namespace presburger;
using namespace tabulate;

// no clue why but without this i get a missing symbol error
namespace llvm {
int DisableABIBreakingChecks = 1;
int EnableABIBreakingChecks = 0;
} // namespace llvm

namespace pybind11::detail {
/// Casts object <-> MlirAffineExpr.
template <> struct type_caster<MlirAffineExpr> {
  PYBIND11_TYPE_CASTER(MlirAffineExpr, _("MlirAffineExpr"));

  bool load(handle src, bool) {
    py::object capsule = mlirApiObjectToCapsule(src);
    value = mlirPythonCapsuleToAffineExpr(capsule.ptr());
    if (mlirAffineExprIsNull(value)) {
      return false;
    }
    return !mlirAffineExprIsNull(value);
  }

#define FOR_ALL_EXPR_TYPES(_)                                                  \
  _(Dim)                                                                       \
  _(Symbol)                                                                    \
  _(Constant)                                                                  \
  _(Add)                                                                       \
  _(Mul)                                                                       \
  _(Mod)                                                                       \
  _(FloorDiv)                                                                  \
  _(CeilDiv)                                                                   \
  _(Binary)

  static handle cast(MlirAffineExpr v, return_value_policy, handle) {
    auto capsule =
        py::reinterpret_steal<py::object>(mlirPythonAffineExprToCapsule(v));
    auto mlir_ir = py::module::import(MAKE_MLIR_PYTHON_QUALNAME("ir"));
    auto expr = mlir_ir.attr("AffineExpr")
                    .attr(MLIR_PYTHON_CAPI_FACTORY_ATTR)(capsule)
                    .release();

#define DEFINE_SUB_EXPR(TTT)                                                   \
  if (mlirAffineExprIsA##TTT(v)) {                                             \
    return py::module::import(MAKE_MLIR_PYTHON_QUALNAME("ir"))                 \
        .attr("Affine" #TTT "Expr")(expr.cast<py::object>())                   \
        .release();                                                            \
  }
    FOR_ALL_EXPR_TYPES(DEFINE_SUB_EXPR)
#undef DEFINE_SUB_EXPR

    throw py::cast_error("Invalid AffineExpr type when attempting to "
                         "create an AffineExpr");
  }
};

/// Casts object <-> MlirAffineMap.
template <> struct type_caster<MlirValue> {
  PYBIND11_TYPE_CASTER(MlirValue, _("MlirValue"));

  bool load(handle src, bool) {
    py::object capsule = mlirApiObjectToCapsule(src);
    value = mlirPythonCapsuleToValue(capsule.ptr());
    if (mlirValueIsNull(value)) {
      return false;
    }
    return !mlirValueIsNull(value);
  }

  static handle cast(MlirValue v, return_value_policy, handle) {
    auto capsule =
        py::reinterpret_steal<py::object>(mlirPythonValueToCapsule(v));
    return py::module::import(MAKE_MLIR_PYTHON_QUALNAME("ir"))
        .attr("Value")
        .attr(MLIR_PYTHON_CAPI_FACTORY_ATTR)(capsule)
        .release();
  }
};

} // namespace pybind11::detail

static mlir::LogicalResult
getOpIndexSet(mlir::Operation *op, mlir::FlatAffineValueConstraints *indexSet) {
  llvm::SmallVector<mlir::Operation *, 4> ops;
  mlir::getEnclosingAffineForAndIfOps(*op, &ops);
  return getIndexSet(ops, indexSet);
}


PYBIND11_MODULE(_loopyMlir, m) {
  auto mod = py::module_::import(MAKE_MLIR_PYTHON_QUALNAME("ir"));
  py::object affineMap_ = (py::object)mod.attr("AffineMap");
  py::object affineMapAttr_ = (py::object)mod.attr("AffineMapAttr");
  py::object affineExpr_ = (py::object)mod.attr("AffineExpr");
  py::class_<PyAffineMap>(m, "LoopyAffineMap", affineMap_)
      .def(py::init<>([](const py::handle apiObject) {
        auto capsule = pybind11::detail::mlirApiObjectToCapsule(apiObject);
        return PyAffineMap::createFromCapsule(capsule);
      }))
      .def(
          "walkExprs",
          [](PyAffineMap &self,
             std::function<void(size_t resIdx, MlirAffineExpr expr)> callback) {
            for (const auto &idx_expr :
                 llvm::enumerate(unwrap(self.affineMap).getResults())) {
              auto idx = idx_expr.index();
              auto expr = idx_expr.value();
              expr.walk([&callback, &idx](mlir::AffineExpr expr) {
                callback(idx, wrap(expr));
              });
            }
          });

  py::class_<PyAffineMapAttribute>(m, "LoopyAffineMapAttr", affineMapAttr_)
      .def(py::init<>([](const py::handle apiObject) {
        auto capsule = pybind11::detail::mlirApiObjectToCapsule(apiObject);
        return PyAffineMapAttribute::createFromCapsule(capsule);
      }))
      .def_property_readonly("map", [](PyAffineMapAttribute &self) {
        return PyAffineMap(self.getContext(),
                           mlirAffineMapAttrGetValue(self.get()));
      });

  py::object Value_ = (py::object)mod.attr("Value");
  m.def("print_value_as_operand", [](const py::handle valueApiObject) {
    auto capsule = pybind11::detail::mlirApiObjectToCapsule(valueApiObject);
    MlirValue mlirValue = mlirPythonCapsuleToValue(capsule.ptr());
    return printValueAsOperand(unwrap(mlirValue));
  });
  m.def("get_affine_value_map", [](const py::handle affineOpApiObject) {
    auto capsule = pybind11::detail::mlirApiObjectToCapsule(affineOpApiObject);
    MlirOperation mlirAffineOp = mlirPythonCapsuleToOperation(capsule.ptr());
    if (mlirOperationIsNull(mlirAffineOp)) {
      throw py::value_error("not an operation");
    }
    mlir::Operation *mlirOp = unwrap(mlirAffineOp);
    mlir::AffineValueMap valueMap;
    if (llvm::isa<mlir::AffineApplyOp>(mlirOp)) {
      AffineApplyOp affineApplyOp = llvm::cast<mlir::AffineApplyOp>(mlirOp);
      valueMap = affineApplyOp.getAffineValueMap();
    } else
      throw py::value_error("has to be affine apply op");
    py::list dims;
    py::list syms;
    for (unsigned int i = 0; i < valueMap.getNumDims(); ++i) {
      auto v = valueMap.getOperand(i);
      dims.append(printValueAsOperand(v));
    }
    for (unsigned int i = valueMap.getNumDims();
         i < valueMap.getNumDims() + valueMap.getNumSymbols(); ++i) {
      auto v = valueMap.getOperand(i);
      syms.append(printValueAsOperand(v));
    }
    return py::make_tuple(dims, syms);
  });
  m.def("get_access_relation", [&Value_](const py::handle affineOpApiObject) {
    auto capsule = pybind11::detail::mlirApiObjectToCapsule(affineOpApiObject);
    MlirOperation mlirAffineOp = mlirPythonCapsuleToOperation(capsule.ptr());
    if (mlirOperationIsNull(mlirAffineOp))
      throw py::value_error("not an operation");
    mlir::Operation *mlirOp = unwrap(mlirAffineOp);
    if (!mlirOp)
      throw py::value_error("didn't unwrap affineOp");
    if (llvm::isa<mlir::AffineStoreOp>(mlirOp)) {
      mlirOp = llvm::dyn_cast<mlir::AffineStoreOp>(mlirOp);
    } else if (llvm::isa<mlir::AffineLoadOp>(mlirOp)) {
      mlirOp = llvm::dyn_cast<mlir::AffineLoadOp>(mlirOp);
    } else
      throw py::value_error(
          "has to be either affine load op or affine store op");

    mlir::MemRefAccess *access;
    access = new mlir::MemRefAccess(mlirOp);
    py::dict indices;
    for (const auto &pos_idx : llvm::enumerate(access->indices)) {
      indices[py::cast<>(pos_idx.index())] =
          printValueAsOperand(pos_idx.value());
    }

    mlir::FlatAffineValueConstraints domain;
    getOpIndexSet(mlirOp, &domain);
    mlir::FlatAffineRelation domainRel(domain.getNumDimVars(),
                                       /*numRangeDims=*/0, domain);
    py::dict bounds;
    for (unsigned i = 0; i < domainRel.getNumDimAndSymbolVars(); ++i) {
      py::dict bound;
      if (domainRel.hasValue(i)) {
        bound["LB"] = domainRel.getConstantBound(
            mlir::presburger::IntegerRelation::LB, i);
        bound["UB"] = domainRel.getConstantBound(
            mlir::presburger::IntegerRelation::UB, i);
        bound["EQ"] = domainRel.getConstantBound(
            mlir::presburger::IntegerRelation::EQ, i);
        bounds[py::cast<>(wrap(domainRel.getValue(i)))] = bound;
      }
    }
    return py::make_tuple(bounds, indices);
  });

  m.def("show_access_relation", [](const py::handle moduleApiObject) {
    auto capsule = pybind11::detail::mlirApiObjectToCapsule(moduleApiObject);
    MlirModule mlirModule = mlirPythonCapsuleToModule(capsule.ptr());
    auto module = unwrap(mlirModule);
    showAccessRelations(module.getOperation(), *module->getContext());
  });
}
