# Copyright (c) 2024, Sebastian Zaha <sebastian.zaha@gmail.com>
#
# SPDX-License-Identifier: BSD-2-Clause
#
# API reference and examples for the summary and synthetic children providers:
# https://lldb.llvm.org/use/variable.html
#
# More elaborate examples of synthetic providers for libstdcpp types:
# https://github.com/llvm/llvm-project/blob/main/lldb/examples/synthetic/gnu_libstdcpp.py

import lldb


def _utf8_summary(value, byte_ptr_name, length_name):
    pointer = value.GetChildMemberWithName(byte_ptr_name).GetValueAsUnsigned(0)
    length = value.GetChildMemberWithName(length_name).GetValueAsUnsigned(0)
    if pointer == 0:
        return False
    if length == 0:
        return '""'

    error = lldb.SBError()
    string_data = value.process.ReadMemory(pointer, length, error)
    ret = '"%s"' % (string_data)

    if not error.Success():
        return f"Error reading byte array: {error.GetCString()}"

    return ret


def _frame(sbvalue_obj):
    return sbvalue_obj.GetTarget().GetProcess().GetSelectedThread().GetSelectedFrame()


def string_summary(valobj, dict):
    # Using the internal structure directly is quite convoluted here because of the packing optimizations
    # of AK::String (can be a short string, a substring or a normal string). Hence, we are calling
    # the bytes() method directly.
    expression = f"(AK::ReadonlyBytes)(({valobj.GetType().GetName()}*){valobj.GetAddress()}).bytes()"
    sv = _frame(valobj).EvaluateExpression(expression)
    if sv.GetError().Fail():
        return f"Error evaluating expression: {sv.GetError().GetCString()}"

    return _utf8_summary(sv, "m_values", "m_size")


def string_impl_summary(valobj, dict):
    return _utf8_summary(valobj, "m_inline_buffer", "m_length")


def string_view_summary(valobj, dict):
    return _utf8_summary(valobj, "m_characters", "m_length")


def variant_summary(valobj, dict):
    raw_obj = valobj.GetNonSyntheticValue()
    index_obj = raw_obj.GetChildMemberWithName("m_index")
    data_obj = raw_obj.GetChildMemberWithName("m_data")

    if not (index_obj and index_obj.IsValid() and data_obj and data_obj.IsValid()):
        return "<Missing or Invalid m_index / m_data>"

    index = index_obj.GetValueAsUnsigned(0)
    # Invalid index can happen when the variant is not initialized yet.
    template_arg_count = valobj.GetType().GetNumberOfTemplateArguments()
    if index >= template_arg_count:
        return "<Invalid: index >= template_arg_count>"

    active_type = valobj.GetType().GetTemplateArgumentType(index)
    return f"Variant (Active Type = {active_type.GetDisplayTypeName()})"


class VariantSyntheticProvider:
    def __init__(self, val_obj, dict):
        self.val_obj = val_obj
        self.is_valid = False

    def update(self):
        self.index = self.val_obj.GetChildMemberWithName("m_index").GetValueAsUnsigned(0)
        self.data_obj = self.val_obj.GetChildMemberWithName("m_data")
        self.is_valid = True
        return False

    def has_children(self):
        return True

    def num_children(self):
        return 1 if self.is_valid else 0

    def get_child_index(self, name):
        return 0

    def get_child_at_index(self, index):
        if not self.is_valid:
            return None

        value = self.data_obj
        template_type = self.val_obj.GetType().GetTemplateArgumentType(self.index)
        value = value.Cast(template_type)

        if value.IsValid():
            return value.Clone("Value")
        return None
