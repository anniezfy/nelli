from typing import Any, List
from typing import Union

from ..loopy_mlir.dialects import arith as arith_dialect
from ..loopy_mlir.dialects import math, arith
from ..loopy_mlir.dialects._ods_common import (
    get_op_result_or_value,
    get_default_loc_context,
)
from ..loopy_mlir.dialects.linalg.opdsl.lang.emitter import (
    _is_integer_type,
    _is_floating_point_type,
    _is_index_type,
    _get_floating_point_width,
    _is_complex_type,
)
from ..loopy_mlir.ir import (
    Type,
    Value,
    IntegerType,
    IndexType,
    BF16Type,
    F16Type,
    F32Type,
    F64Type,
    IntegerAttr,
    Operation,
    OpView,
    StringAttr,
)
from ..loopy_mlir._mlir_libs._loopy_mlir import ArithValue


def _isa(obj: Any, cls: type):
    try:
        cls(obj)
    except ValueError:
        return False
    return True


def _is_any_of(obj: Any, classes: List[type]):
    return any(_isa(obj, cls) for cls in classes)


def _is_integer_like_type(type: Type):
    return _is_any_of(type, [IntegerType, IndexType])


def _is_float_type(type: Type):
    return _is_any_of(type, [BF16Type, F16Type, F32Type, F64Type])


class CmpFOp(arith_dialect.CmpFOp):
    def __init__(
        self,
        predicate: str,
        lhs: Union[Operation, OpView, Value],
        rhs: Union[Operation, OpView, Value],
        *,
        loc=None,
        ip=None,
    ):
        predicates = {
            "false": 0,
            "oeq": 1,
            "ogt": 2,
            "oge": 3,
            "olt": 4,
            "ole": 5,
            "one": 6,
            "ord": 7,
            "ueq": 8,
            "ugt": 9,
            "uge": 10,
            "ult": 11,
            "ule": 12,
            "une": 13,
            "uno": 14,
            "true": 15,
        }
        assert predicate in predicates, f"predicate {predicate} not in predicates"
        context = get_default_loc_context(loc)
        lhs = get_op_result_or_value(lhs)
        rhs = get_op_result_or_value(rhs)
        predicate = IntegerAttr.get(IntegerType.get_signless(64), predicates[predicate])
        result_type = IntegerType.get_signless(1, context=context)
        super().__init__(result_type, predicate, lhs, rhs, loc=loc, ip=ip)


class CmpIOp(arith_dialect.CmpIOp):
    def __init__(
        self,
        predicate: str,
        lhs: Union[Operation, OpView, Value],
        rhs: Union[Operation, OpView, Value],
        *,
        loc=None,
        ip=None,
    ):
        assert predicate in {
            "eq",
            "ne",
            "slt",
            "sle",
            "sgt",
            "sge",
            "ult",
            "ule",
            "ugt",
            "uge",
        }

        context = get_default_loc_context(loc)
        lhs = get_op_result_or_value(lhs)
        rhs = get_op_result_or_value(rhs)
        predicate = StringAttr.get(predicate, context=context)
        result_type = IntegerType.get_signless(1, context=context)
        super().__init__(result_type, predicate, lhs, rhs, loc=loc, ip=ip)


def cast_to_integer(to_type: Type, operand: OpView, is_unsigned_cast: bool) -> OpView:
    operand: Value = get_op_result_or_value(operand)
    to_width = IntegerType(to_type).width
    operand_type = operand.type
    if _is_floating_point_type(operand_type):
        if is_unsigned_cast:
            return arith.FPToUIOp(to_type, operand)
        return arith.FPToSIOp(to_type, operand)
    if _is_index_type(operand_type):
        return arith.IndexCastOp(to_type, operand)
    # Assume integer.
    from_width = IntegerType(operand_type).width
    if to_width > from_width:
        if is_unsigned_cast:
            return arith.ExtUIOp(to_type, operand)
        return arith.ExtSIOp(to_type, operand)
    elif to_width < from_width:
        return arith.TruncIOp(to_type, operand)
    raise ValueError(
        f"Unable to cast body expression from {operand_type} to " f"{to_type}"
    )


def cast_to_floating_point(
    to_type: Type, operand: OpView, is_unsigned_cast: bool
) -> OpView:
    operand: Value = get_op_result_or_value(operand)
    operand_type: Type = operand.type
    if _is_integer_type(operand_type):
        if is_unsigned_cast:
            return arith.UIToFPOp(to_type, operand)
        return arith.SIToFPOp(to_type, operand)
    # Assume FloatType.
    to_width = _get_floating_point_width(to_type)
    from_width = _get_floating_point_width(operand_type)
    if to_width > from_width:
        return arith.ExtFOp(to_type, operand)
    elif to_width < from_width:
        return arith.TruncFOp(to_type, operand)
    raise ValueError(
        f"Unable to cast body expression from {operand_type} to " f"{to_type}"
    )


def abs(x) -> OpView:
    x = get_op_result_or_value(x)
    if _is_floating_point_type(x.type):
        return math.AbsFOp(x)
    raise NotImplementedError("Unsupported 'abs' operand: {x}")


def ceil(x) -> OpView:
    x = get_op_result_or_value(x)
    if _is_floating_point_type(x.type):
        return math.CeilOp(x)
    raise NotImplementedError("Unsupported 'ceil' operand: {x}")


def floor(x) -> OpView:
    x = get_op_result_or_value(x)
    if _is_floating_point_type(x.type):
        return math.FloorOp(x)
    raise NotImplementedError("Unsupported 'floor' operand: {x}")


def neg(x) -> OpView:
    x = get_op_result_or_value(x)
    if _is_floating_point_type(x.type):
        return arith.NegFOp(x)
    if _is_complex_type(x.type):
        return complex.NegOp(x)
    raise NotImplementedError("Unsupported 'negf' operand: {x}")


def add(lhs, rhs) -> OpView:
    lhs = get_op_result_or_value(lhs)
    rhs = get_op_result_or_value(rhs)

    if _is_floating_point_type(lhs.type):
        return arith.AddFOp(lhs, rhs)
    # TODO(max): type promotion isn't right
    if _is_integer_type(lhs.type) or _is_index_type(lhs.type):
        if _is_index_type(lhs.type):
            lhs = cast_to_integer(
                IntegerType.get_signed(64), lhs, is_unsigned_cast=True
            )
        if _is_index_type(rhs.type):
            rhs = cast_to_integer(
                IntegerType.get_signed(64), rhs, is_unsigned_cast=True
            )
        return arith.AddIOp(lhs, rhs)
    if _is_complex_type(lhs.type):
        return complex.AddOp(lhs, rhs)
    raise NotImplementedError("Unsupported 'add' operands: {lhs}, {rhs}")


def sub(lhs, rhs) -> OpView:
    lhs = get_op_result_or_value(lhs)
    rhs = get_op_result_or_value(rhs)

    if _is_floating_point_type(lhs.type):
        return arith.SubFOp(lhs, rhs)
    if _is_integer_type(lhs.type) or _is_index_type(lhs.type):
        return arith.SubIOp(lhs, rhs)
    if _is_complex_type(lhs.type):
        return complex.SubOp(lhs, rhs)
    raise NotImplementedError("Unsupported 'sub' operands: {lhs}, {rhs}")


def mul(lhs, rhs) -> OpView:
    lhs = get_op_result_or_value(lhs)
    rhs = get_op_result_or_value(rhs)

    if _is_floating_point_type(lhs.type):
        return arith.MulFOp(lhs, rhs)
    if _is_integer_type(lhs.type) or _is_index_type(lhs.type):
        return arith.MulIOp(lhs, rhs)
    if _is_complex_type(lhs.type):
        return complex.MulOp(lhs, rhs)
    raise NotImplementedError("Unsupported 'mul' operands: {lhs}, {rhs}")


def gt(lhs, rhs) -> OpView:
    lhs = get_op_result_or_value(lhs)
    rhs = get_op_result_or_value(rhs)

    if _is_floating_point_type(lhs.type):
        if _is_integer_type(rhs.type) or _is_index_type(rhs.type):
            rhs = cast_to_floating_point(F64Type.get(), rhs, is_unsigned_cast=True)
        return CmpFOp("ogt", lhs, rhs)
    if _is_integer_type(lhs.type):
        return CmpIOp("sgt", lhs, rhs)
    if _is_index_type(lhs.type):
        return CmpIOp("ugt", lhs, rhs)
    raise NotImplementedError("Unsupported 'mul' operands: {lhs}, {rhs}")


def lt(lhs, rhs) -> OpView:
    lhs = get_op_result_or_value(lhs)
    rhs = get_op_result_or_value(rhs)

    if _is_floating_point_type(lhs.type):
        return CmpFOp("olt", lhs, rhs)
    if _is_integer_type(lhs.type):
        return CmpIOp("slt", lhs, rhs)
    if _is_index_type(lhs.type):
        return CmpIOp("ult", lhs, rhs)
    raise NotImplementedError("Unsupported 'mul' operands: {lhs}, {rhs}")


def ge(lhs, rhs) -> OpView:
    lhs = get_op_result_or_value(lhs)
    rhs = get_op_result_or_value(rhs)

    if _is_floating_point_type(lhs.type):
        return CmpFOp("oge", lhs, rhs)
    if _is_integer_type(lhs.type):
        return CmpIOp("sge", lhs, rhs)
    if _is_index_type(lhs.type):
        return CmpIOp("uge", lhs, rhs)
    raise NotImplementedError("Unsupported 'mul' operands: {lhs}, {rhs}")


def le(lhs, rhs) -> OpView:
    lhs = get_op_result_or_value(lhs)
    rhs = get_op_result_or_value(rhs)

    if _is_floating_point_type(lhs.type):
        return CmpFOp("ole", lhs, rhs)
    if _is_integer_type(lhs.type):
        return CmpIOp("sle", lhs, rhs)
    if _is_index_type(lhs.type):
        return CmpIOp("ule", lhs, rhs)
    raise NotImplementedError("Unsupported 'mul' operands: {lhs}, {rhs}")


class ArithValue(ArithValue):
    def __abs__(self):
        return ArithValue(abs(self).result)

    def __ceil__(self):
        return ArithValue(ceil(self).result)

    def __floor__(self):
        return ArithValue(floor(self).result)

    def __neg__(self):
        return ArithValue(neg(self).result)

    def __add__(self, other):
        return ArithValue(add(self, other).result)

    def __radd__(self, lhs):
        return self + lhs

    def __sub__(self, other):
        return ArithValue(sub(self, other).result)

    def __rsub__(self, lhs):
        return self - lhs

    def __mul__(self, other):
        return ArithValue(mul(self, other).result)

    def __rmul__(self, lhs):
        return self + lhs

    def __gt__(self, other):
        return ArithValue(gt(self, other).result)

    def __lt__(self, other):
        return ArithValue(lt(self, other).result)

    def __ge__(self, other):
        return ArithValue(ge(self, other).result)

    def __le__(self, other):
        return ArithValue(le(self, other).result)


def infer_mlir_type(py_val) -> Type:
    if isinstance(py_val, int):
        return IntegerType.get_signed(64)
    elif isinstance(py_val, float):
        return F64Type.get()
    else:
        raise Exception(f"unsupported val type {type(py_val)} {py_val}")


def constant(
    py_cst: Union[int, float, bool],
    index_type: bool = False,
):
    if index_type:
        constant = arith.ConstantOp.create_index(py_cst).result
    else:
        constant = arith.ConstantOp(infer_mlir_type(py_cst), py_cst).result

    return ArithValue(constant)
