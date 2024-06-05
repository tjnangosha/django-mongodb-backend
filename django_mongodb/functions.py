from django.db import NotSupportedError
from django.db.models.expressions import Func
from django.db.models.functions.comparison import Cast, Coalesce, Greatest, Least, NullIf
from django.db.models.functions.datetime import (
    Extract,
    ExtractDay,
    ExtractHour,
    ExtractIsoWeekDay,
    ExtractIsoYear,
    ExtractMinute,
    ExtractMonth,
    ExtractSecond,
    ExtractWeek,
    ExtractWeekDay,
    ExtractYear,
    TruncBase,
)
from django.db.models.functions.math import Ceil, Cot, Degrees, Log, Power, Radians, Random, Round
from django.db.models.functions.text import Upper

from .query_utils import process_lhs

MONGO_OPERATORS = {
    Ceil: "ceil",
    Coalesce: "ifNull",
    Degrees: "radiansToDegrees",
    Greatest: "max",
    Least: "min",
    Power: "pow",
    Radians: "degreesToRadians",
    Random: "rand",
    Upper: "toUpper",
}
EXTRACT_OPERATORS = {
    ExtractDay.lookup_name: "dayOfMonth",
    ExtractHour.lookup_name: "hour",
    ExtractIsoWeekDay.lookup_name: "isoDayOfWeek",
    ExtractIsoYear.lookup_name: "isoWeekYear",
    ExtractMinute.lookup_name: "minute",
    ExtractMonth.lookup_name: "month",
    ExtractSecond.lookup_name: "second",
    ExtractWeek.lookup_name: "isoWeek",
    ExtractWeekDay.lookup_name: "dayOfWeek",
    ExtractYear.lookup_name: "year",
}


def cast(self, compiler, connection):
    output_type = connection.data_types[self.output_field.get_internal_type()]
    lhs_mql = process_lhs(self, compiler, connection)[0]
    if max_length := self.output_field.max_length:
        lhs_mql = {"$substrCP": [lhs_mql, 0, max_length]}
    lhs_mql = {"$convert": {"input": lhs_mql, "to": output_type}}
    if decimal_places := getattr(self.output_field, "decimal_places", None):
        lhs_mql = {"$trunc": [lhs_mql, decimal_places]}
    return lhs_mql


def cot(self, compiler, connection):
    lhs_mql = process_lhs(self, compiler, connection)
    return {"$divide": [1, {"$tan": lhs_mql}]}


def extract(self, compiler, connection):
    lhs_mql = process_lhs(self, compiler, connection)
    operator = EXTRACT_OPERATORS.get(self.lookup_name)
    if operator is None:
        raise NotSupportedError("%s is not supported." % self.__class__.__name__)
    if timezone := self.get_tzname():
        lhs_mql = {"date": lhs_mql, "timezone": timezone}
    return {f"${operator}": lhs_mql}


def func(self, compiler, connection):
    lhs_mql = process_lhs(self, compiler, connection)
    operator = MONGO_OPERATORS.get(self.__class__, self.function.lower())
    return {f"${operator}": lhs_mql}


def log(self, compiler, connection):
    # This function is usually log(base, num) but on MongoDB it's log(num, base).
    clone = self.copy()
    clone.set_source_expressions(self.get_source_expressions()[::-1])
    return func(clone, compiler, connection)


def null_if(self, compiler, connection):
    """Return None if expr1==expr2 else expr1."""
    expr1, expr2 = (expr.as_mql(compiler, connection) for expr in self.get_source_expressions())
    return {"$cond": {"if": {"$eq": [expr1, expr2]}, "then": None, "else": expr1}}


def round_(self, compiler, connection):
    # Round needs its own function because it's a special case that inherits
    # from Transform but has two arguments.
    return {"$round": [expr.as_mql(compiler, connection) for expr in self.get_source_expressions()]}


def trunc(self, compiler, connection):
    lhs_mql = process_lhs(self, compiler, connection)
    lhs_mql = {"date": lhs_mql, "unit": self.kind, "startOfWeek": "mon"}
    if timezone := self.get_tzname():
        lhs_mql["timezone"] = timezone
    return {"$dateTrunc": lhs_mql}


def register_functions():
    Cast.as_mql = cast
    Cot.as_mql = cot
    Extract.as_mql = extract
    Func.as_mql = func
    Log.as_mql = log
    NullIf.as_mql = null_if
    Round.as_mql = round_
    TruncBase.as_mql = trunc
