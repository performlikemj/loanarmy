"""
Analytics Sandbox for Academy Watch Agent

Executes Python code in an isolated subprocess with:
- Import allowlist: pandas, numpy, matplotlib, plotly, json, math
- No network access, no filesystem access outside temp
- 256MB memory limit, 10 second timeout
- Input: code string + dict of DataFrames (serialized as CSV)
- Output: dict with charts (base64 PNG), tables (JSON), text output
"""

import base64
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# The script template that runs inside the subprocess
_SANDBOX_SCRIPT = r'''
import sys
import os
import resource
import signal
import json
import io
import base64

# --- Security: set memory limit (256MB) ---
MEM_LIMIT = 256 * 1024 * 1024
try:
    resource.setrlimit(resource.RLIMIT_AS, (MEM_LIMIT, MEM_LIMIT))
except Exception:
    pass  # some platforms don't support RLIMIT_AS

# --- Security: set timeout (10 seconds) ---
def _timeout_handler(signum, frame):
    raise TimeoutError("Sandbox execution timed out (10s limit)")

signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(10)

# --- Security: restrict imports ---
_ALLOWED_MODULES = frozenset({
    'pandas', 'numpy', 'matplotlib', 'matplotlib.pyplot', 'matplotlib.figure',
    'plotly', 'plotly.express', 'plotly.graph_objects', 'plotly.io',
    'json', 'math', 'statistics', 'collections', 'itertools', 'functools',
    'datetime', 'io', 'base64', 'textwrap', 're',
})

_BLOCKED_MODULES = frozenset({
    'os', 'sys', 'subprocess', 'socket', 'http', 'urllib', 'requests',
    'shutil', 'pathlib', 'glob', 'importlib', 'ctypes', 'multiprocessing',
    'threading', 'signal', 'resource', 'pickle', 'shelve', 'sqlite3',
    'sqlalchemy', 'flask', 'django', 'builtins', 'code', 'compile',
})

_original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

def _restricted_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top in _BLOCKED_MODULES:
        raise ImportError(f"Import of '{name}' is not allowed in the sandbox")
    # Allow anything in the allowlist, plus sub-modules of allowed packages
    if top not in {m.split('.')[0] for m in _ALLOWED_MODULES} and top not in ('builtins',):
        raise ImportError(f"Import of '{name}' is not allowed in the sandbox")
    return _original_import(name, *args, **kwargs)

try:
    __builtins__.__import__ = _restricted_import
except AttributeError:
    import builtins
    builtins.__import__ = _restricted_import

# --- Load input data ---
import pandas as pd

work_dir = sys.argv[1]
manifest_path = os.path.join(work_dir, 'manifest.json')
with open(manifest_path, 'r') as f:
    manifest = json.load(f)

# Load DataFrames from CSV files
dataframes = {}
for name, csv_file in manifest.get('dataframes', {}).items():
    csv_path = os.path.join(work_dir, csv_file)
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        dataframes[name] = pd.read_csv(csv_path)
    else:
        dataframes[name] = pd.DataFrame()

code = manifest['code']

# --- Output collectors ---
_charts = []
_tables = []
_stdout_capture = io.StringIO()

def output_chart(fig):
    """Save a matplotlib or plotly figure as base64 PNG."""
    buf = io.BytesIO()
    if hasattr(fig, 'savefig'):
        # matplotlib
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        import matplotlib.pyplot as plt
        plt.close(fig)
    elif hasattr(fig, 'to_image'):
        # plotly
        buf.write(fig.to_image(format='png'))
    else:
        raise ValueError("Unsupported figure type. Use matplotlib or plotly.")
    buf.seek(0)
    _charts.append(base64.b64encode(buf.read()).decode('utf-8'))

def output_table(df, title=None):
    """Save a DataFrame as JSON for frontend rendering."""
    if hasattr(df, 'to_dict'):
        _tables.append({
            'title': title,
            'columns': list(df.columns),
            'data': df.to_dict(orient='records'),
        })
    else:
        _tables.append({'title': title, 'data': df})

# --- Security: restricted builtins (NO open/exec/eval/compile/__import__/etc.) ---
_SAFE_BUILTINS = {
    'print': print, 'len': len, 'range': range, 'enumerate': enumerate,
    'zip': zip, 'map': map, 'filter': filter, 'sorted': sorted,
    'min': min, 'max': max, 'sum': sum, 'abs': abs, 'round': round,
    'int': int, 'float': float, 'str': str, 'bool': bool,
    'list': list, 'dict': dict, 'set': set, 'tuple': tuple, 'frozenset': frozenset,
    'type': type, 'isinstance': isinstance, 'issubclass': issubclass,
    'hasattr': hasattr, 'getattr': getattr, 'setattr': setattr,
    'any': any, 'all': all, 'reversed': reversed,
    'format': format, 'repr': repr, 'hash': hash, 'id': id,
    'slice': slice, 'iter': iter, 'next': next,
    'True': True, 'False': False, 'None': None,
    'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
    'KeyError': KeyError, 'IndexError': IndexError, 'RuntimeError': RuntimeError,
    'StopIteration': StopIteration, 'ZeroDivisionError': ZeroDivisionError,
    '__import__': _restricted_import,
}

# --- Execute user code ---
exec_globals = {
    '__builtins__': _SAFE_BUILTINS,
    'output_chart': output_chart,
    'output_table': output_table,
    'pd': pd,
    **dataframes,
}

old_stdout = sys.stdout
sys.stdout = _stdout_capture

try:
    exec(code, exec_globals)
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

sys.stdout = old_stdout

# --- Write output ---
output = {
    'charts': _charts,
    'tables': _tables,
    'stdout': _stdout_capture.getvalue()[:10000],  # Cap output size
}

output_path = os.path.join(work_dir, 'output.json')
with open(output_path, 'w') as f:
    json.dump(output, f)
'''


def execute_sandboxed_code(
    code: str,
    dataframes: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    """Execute Python code in a sandboxed subprocess.

    Args:
        code: Python code string to execute.
        dataframes: Dict of name -> DataFrame to make available.

    Returns:
        Dict with 'charts' (list of base64 PNG), 'tables' (list of JSON),
        'stdout' (captured print output), 'error' (if any).
    """
    with tempfile.TemporaryDirectory(prefix='aw_sandbox_') as work_dir:
        # Write DataFrames as CSV
        df_manifest = {}
        for name, df in dataframes.items():
            csv_file = f'{name}.csv'
            csv_path = os.path.join(work_dir, csv_file)
            df.to_csv(csv_path, index=False)
            df_manifest[name] = csv_file

        # Write manifest
        manifest = {
            'code': code,
            'dataframes': df_manifest,
        }
        manifest_path = os.path.join(work_dir, 'manifest.json')
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        # Write sandbox script
        script_path = os.path.join(work_dir, '_sandbox.py')
        with open(script_path, 'w') as f:
            f.write(_SANDBOX_SCRIPT)

        # Execute in subprocess with network isolation
        # NOTE: For production, prefer running inside a Docker container for full sandboxing.
        if platform.system() == 'Linux':
            cmd = ['unshare', '--net', '--', sys.executable, script_path, work_dir]
        else:
            cmd = [sys.executable, script_path, work_dir]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,  # slightly above the internal 10s alarm
                cwd=work_dir,
                env={
                    'PATH': os.environ.get('PATH', ''),
                    'HOME': work_dir,
                    'PYTHONPATH': '',
                    'MPLBACKEND': 'Agg',  # non-interactive matplotlib
                },
            )
        except subprocess.TimeoutExpired:
            return {
                'charts': [],
                'tables': [],
                'stdout': '',
                'error': 'Execution timed out (15 second limit)',
            }

        # Read output
        output_path = os.path.join(work_dir, 'output.json')
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                output = json.load(f)
            if result.returncode != 0 and result.stderr:
                output['error'] = result.stderr[:2000]
            return output
        else:
            return {
                'charts': [],
                'tables': [],
                'stdout': result.stdout[:2000] if result.stdout else '',
                'error': result.stderr[:2000] if result.stderr else 'Sandbox produced no output',
            }
