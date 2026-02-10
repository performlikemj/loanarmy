"""
GOL Sandbox Executor

Executes LLM-generated pandas code in a RestrictedPython sandbox
with allowlisted builtins, no imports, and a 10-second timeout.
"""

import ctypes
import logging
import threading

import numpy as np
import pandas as pd
from RestrictedPython import compile_restricted
from RestrictedPython.Guards import safe_builtins, safer_getattr

logger = logging.getLogger(__name__)

MAX_ROWS = 100
TIMEOUT_SECONDS = 10

ALLOWED_BUILTINS = {
    **safe_builtins,
    'len': len,
    'sorted': sorted,
    'min': min,
    'max': max,
    'sum': sum,
    'round': round,
    'abs': abs,
    'int': int,
    'float': float,
    'str': str,
    'bool': bool,
    'list': list,
    'dict': dict,
    'tuple': tuple,
    'set': set,
    'zip': zip,
    'enumerate': enumerate,
    'range': range,
    'map': map,
    'filter': filter,
    'any': any,
    'all': all,
    'isinstance': isinstance,
    'type': type,
    'True': True,
    'False': False,
    'None': None,
    'print': lambda *a, **kw: None,  # no-op print
}


def execute_analysis(code: str, dataframes: dict, display: str = 'table', description: str = '') -> dict:
    """
    Execute pandas code in a restricted sandbox.

    Args:
        code: Python code that must assign its result to `result`.
        dataframes: dict of name -> pd.DataFrame.
        display: Display hint from the LLM ('table', 'bar_chart', etc.).
        description: Brief description of the analysis (passed through as metadata).

    Returns:
        Dict with result_type, display, meta, and formatted data.
    """
    if not code or not code.strip():
        return {'result_type': 'error', 'error': 'No code provided', 'display': display}

    # Compile with RestrictedPython
    try:
        byte_code = compile_restricted(code, '<gol-analysis>', 'exec')
    except SyntaxError as e:
        return {'result_type': 'error', 'error': f'Syntax error: {e}', 'display': display}

    if byte_code is None:
        return {'result_type': 'error', 'error': 'Code compilation failed', 'display': display}

    # Build restricted namespace
    restricted_globals = {
        '__builtins__': ALLOWED_BUILTINS,
        '_getattr_': safer_getattr,
        '_getiter_': iter,
        '_getitem_': _guarded_getitem,
        '_write_': _default_write,
        '_inplacevar_': _inplacevar,
        'pd': pd,
        'np': np,
        **dataframes,
    }

    local_ns = {}

    # Execute with thread-based timeout (signal.alarm doesn't work outside main thread)
    exec_result = [None]  # [None] = success, or [exception]

    def _run():
        try:
            exec(byte_code, restricted_globals, local_ns)  # noqa: S102
        except Exception as e:
            exec_result[0] = e

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=TIMEOUT_SECONDS)

    if thread.is_alive():
        # Thread is still running — try to kill it
        _kill_thread(thread)
        return {'result_type': 'error', 'error': 'Analysis timed out (10s limit)', 'display': display}

    if exec_result[0] is not None:
        e = exec_result[0]
        return {
            'result_type': 'error',
            'error': f'{type(e).__name__}: {e}',
            'display': display,
        }

    # Extract result
    result = local_ns.get('result')
    if result is None:
        return {
            'result_type': 'error',
            'error': 'No `result` variable set. Your code must assign to `result`.',
            'display': display,
        }

    formatted = _format_result(result)
    formatted['display'] = display
    if description:
        formatted['meta'] = {'description': description}
    return formatted


def _kill_thread(thread):
    """Best-effort kill of a daemon thread via async exception."""
    try:
        tid = thread.ident
        if tid is not None:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(
                ctypes.c_ulong(tid), ctypes.py_object(SystemExit)
            )
    except Exception:
        pass  # Daemon thread will be cleaned up on process exit


def _guarded_getitem(obj, key):
    return obj[key]


def _default_write(obj):
    """RestrictedPython guard for attribute assignment on containers."""
    return obj


def _inplacevar(op, x, y):
    """Handle in-place operations (+=, -=, etc.) in RestrictedPython."""
    if op == '+=':
        return x + y
    elif op == '-=':
        return x - y
    elif op == '*=':
        return x * y
    elif op == '/=':
        return x / y
    elif op == '//=':
        return x // y
    elif op == '%=':
        return x % y
    elif op == '**=':
        return x ** y
    elif op == '&=':
        return x & y
    elif op == '|=':
        return x | y
    elif op == '^=':
        return x ^ y
    raise ValueError(f"Unsupported in-place operation: {op}")


def _format_result(result) -> dict:
    """Convert the result variable into a JSON-serializable response."""
    if isinstance(result, pd.DataFrame):
        truncated = len(result) > MAX_ROWS
        df = result.head(MAX_ROWS)
        # Convert to native Python types for JSON serialization
        rows = []
        for _, row in df.iterrows():
            rows.append([_safe_value(v) for v in row.values])
        return {
            'result_type': 'table',
            'columns': [str(c) for c in df.columns],
            'rows': rows,
            'total_rows': len(result),
            'truncated': truncated,
        }

    if isinstance(result, pd.Series):
        df = result.reset_index()
        df.columns = [str(c) for c in df.columns]
        return _format_result(df)

    if isinstance(result, (int, float, np.integer, np.floating)):
        return {'result_type': 'scalar', 'value': _safe_value(result)}

    if isinstance(result, str):
        return {'result_type': 'scalar', 'value': result}

    if isinstance(result, (list, tuple)):
        return {'result_type': 'list', 'items': [_safe_value(v) for v in result[:MAX_ROWS]]}

    if isinstance(result, dict):
        return {'result_type': 'dict', 'data': {str(k): _safe_value(v) for k, v in result.items()}}

    return {'result_type': 'scalar', 'value': str(result)}


def _safe_value(v):
    """Convert numpy/pandas types to JSON-safe Python natives."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_safe_value(i) for i in v]
    return v
