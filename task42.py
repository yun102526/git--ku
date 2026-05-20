import re
import subprocess
import os
import tempfile
import shutil

def parse_quadruples(text):
    quads = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            line = line.split(':', 1)[1].strip()
        m = re.match(r'\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)', line)
        if m:
            op, a1, a2, a3 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
            quads.append((op, a1, a2, a3))
    return quads


def parse_func_table(text):
    """Parse 'func=entry,param1,param2; func2=entry2,p1' format."""
    table = {}
    if not text:
        return table
    for part in text.split(';'):
        part = part.strip()
        if '=' not in part:
            continue
        name, rest = part.split('=', 1)
        name = name.strip()
        parts = rest.split(',')
        entry = int(parts[0].strip())
        params = [p.strip() for p in parts[1:]] if len(parts) > 1 else []
        table[name] = {'params': params, 'entry': entry}
    return table


def build_func_table_from_quads(quads):
    """Try to infer function table from quads when none provided."""
    func_names = set()
    for op, a1, a2, res in quads:
        if op == 'call':
            func_names.add(a1)

    if len(func_names) == 0:
        return {'main': {'params': [], 'entry': 0}}

    # Find all returns and group consecutive ones
    return_positions = [i for i, (op, _, _, _) in enumerate(quads) if op == 'return']
    if not return_positions:
        return {'main': {'params': [], 'entry': 0}}

    # Group consecutive returns (they belong to the same function's control flow)
    groups = []
    current_group = [return_positions[0]]
    for rp in return_positions[1:]:
        if rp == current_group[-1] + 1:
            current_group.append(rp)
        else:
            groups.append(current_group)
            current_group = [rp]
    groups.append(current_group)

    # Each group's last return marks the end of a function; the next function starts at group[-1]+1
    boundaries = [0]
    for g in groups:
        boundaries.append(g[-1] + 1)
    boundaries = [b for b in boundaries if b < len(quads)]

    # Assign function names: main is always first, then called functions
    func_names_list = sorted(func_names)
    table = {}
    max_funcs = len(func_names_list) + 1
    if len(boundaries) > max_funcs:
        boundaries = boundaries[:max_funcs]

    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(quads)
        used_vars = set()
        assigned_vars = set()
        params = []
        for qi in range(start, end):
            op, a1, a2, res = quads[qi]
            if op == '=':
                if res and res != '_' and not res.isdigit() and not (res.startswith('t') and res[1:].isdigit()):
                    assigned_vars.add(res)
            else:
                for arg in [a1, a2]:
                    if arg and arg != '_' and not arg.isdigit():
                        if not (arg.startswith('t') and arg[1:].isdigit()):
                            if arg not in assigned_vars and arg not in used_vars:
                                used_vars.add(arg)
                                params.append(arg)

        if idx == 0:
            name = 'main'
        elif idx <= len(func_names_list):
            name = func_names_list[idx - 1]
        else:
            name = f'_func{idx}'

        table[name] = {'params': params, 'entry': start}

    if 'main' not in table:
        first_start = boundaries[0]
        for name, info in table.items():
            if info['entry'] == first_start:
                table['main'] = info
                del table[name]
                break
        if 'main' not in table:
            table['main'] = {'params': [], 'entry': boundaries[0]}

    return table


# ---- LLVM IR Generation ----

def generate_llvm_for_function(quads, func_name, params, inputs, global_input_size):
    leaders = {0}
    for i, (op, a1, a2, res) in enumerate(quads):
        if op == 'J' or (op.startswith('J') and len(op) > 1):
            try:
                t = int(res)
                if 0 <= t < len(quads):
                    leaders.add(t)
            except ValueError:
                pass
            if i + 1 < len(quads):
                leaders.add(i + 1)
    leaders = sorted(leaders)

    block_of = {}
    for idx, l in enumerate(leaders):
        block_of[l] = f"block{idx}"

    all_vars = set()
    arr_vars = set()
    for op, a1, a2, res in quads:
        for a in [a1, a2, res]:
            if a and a != '_' and not a.isdigit():
                if not (a.startswith('t') and a[1:].isdigit()):
                    all_vars.add(a)
    for op, a1, a2, res in quads:
        if op == '[]=':
            arr_vars.add(res)
        elif op == '=[]':
            arr_vars.add(a1)

    param_str = ', '.join(f'i32 %{p}' for p in params)
    header = []
    header.append(f'define i32 @{func_name}({param_str}) {{')
    header.append('entry:')

    for v in sorted(all_vars):
        if v in arr_vars:
            header.append(f'  %{v}_ptr = alloca [100 x i32]')
        else:
            header.append(f'  %{v}_ptr = alloca i32')

    for p in params:
        header.append(f'  store i32 %{p}, ptr %{p}_ptr')

    first_block = block_of[0]
    header.append(f'  br label %{first_block}')
    header.append('')

    tmp_cnt = 0

    def new_tmp():
        nonlocal tmp_cnt
        v = f"%rt{tmp_cnt}"
        tmp_cnt += 1
        return v

    def get_val(arg, blk):
        nonlocal tmp_cnt
        arg = arg.strip()
        if arg == '_':
            return None
        if arg.isdigit() or (arg.startswith('-') and arg[1:].isdigit()):
            return arg
        if arg.startswith('t') and arg[1:].isdigit():
            return f'%{arg}'
        if arg in arr_vars:
            t = new_tmp()
            blk.append(f'  {t} = ptrtoint ptr %{arg}_ptr to i32')
            return t
        t = new_tmp()
        blk.append(f'  {t} = load i32, ptr %{arg}_ptr')
        return t

    param_stack = []
    blocks_dict = {}

    for li in range(len(leaders)):
        bs = leaders[li]
        be = leaders[li + 1] if li + 1 < len(leaders) else len(quads)
        bname = block_of[bs]
        blk = [f'{bname}:']
        has_br = False

        for qi in range(bs, be):
            op, a1, a2, res = quads[qi]

            if op == '=':
                v = get_val(a1, blk)
                blk.append(f'  store i32 {v}, ptr %{res}_ptr')

            elif op in ('+', '-', '*', '/', '%'):
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_op = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'sdiv', '%': 'srem'}[op]
                blk.append(f'  %{res} = {ll_op} i32 {v1}, {v2}')

            elif op in ('<', '>', '<=', '>=', '==', '!='):
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_c = {'<': 'slt', '>': 'sgt', '<=': 'sle', '>=': 'sge', '==': 'eq', '!=': 'ne'}[op]
                blk.append(f'  %{res}_i1 = icmp {ll_c} i32 {v1}, {v2}')
                blk.append(f'  %{res} = zext i1 %{res}_i1 to i32')

            elif op == '&&':
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                blk.append(f'  %{res}_c1 = icmp ne i32 {v1}, 0')
                blk.append(f'  %{res}_c2 = icmp ne i32 {v2}, 0')
                blk.append(f'  %{res}_b = and i1 %{res}_c1, %{res}_c2')
                blk.append(f'  %{res} = zext i1 %{res}_b to i32')

            elif op == '||':
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                blk.append(f'  %{res}_c1 = icmp ne i32 {v1}, 0')
                blk.append(f'  %{res}_c2 = icmp ne i32 {v2}, 0')
                blk.append(f'  %{res}_b = or i1 %{res}_c1, %{res}_c2')
                blk.append(f'  %{res} = zext i1 %{res}_b to i32')

            elif op == 'read':
                if inputs:
                    blk.append(f'  %ld_{qi} = load i32, ptr @input_idx')
                    blk.append(f'  %gp_{qi} = getelementptr [{global_input_size} x i32], ptr @input_data, i32 0, i32 %ld_{qi}')
                    blk.append(f'  %{res} = load i32, ptr %gp_{qi}')
                    blk.append(f'  %ni_{qi} = add i32 %ld_{qi}, 1')
                    blk.append(f'  store i32 %ni_{qi}, ptr @input_idx')
                else:
                    blk.append(f'  %{res} = add i32 0, 0')

            elif op == 'write':
                v = get_val(a1, blk)
                blk.append(f'  call i32 (ptr, ...) @printf(ptr @.fmt_num, i32 {v})')

            elif op == 'writec':
                v = get_val(a1, blk)
                blk.append(f'  call i32 (ptr, ...) @printf(ptr @.fmt_chr, i32 {v})')

            elif op == '=[]':
                idx = get_val(a2, blk)
                blk.append(f'  %gp_{res} = getelementptr [100 x i32], ptr %{a1}_ptr, i32 0, i32 {idx}')
                blk.append(f'  %{res} = load i32, ptr %gp_{res}')

            elif op == '[]=':
                v = get_val(a1, blk)
                idx = get_val(a2, blk)
                blk.append(f'  %gp_{qi} = getelementptr [100 x i32], ptr %{res}_ptr, i32 0, i32 {idx}')
                blk.append(f'  store i32 {v}, ptr %gp_{qi}')

            elif op == 'param':
                v = get_val(a1, blk)
                param_stack.append(v)

            elif op == 'call':
                func_name = a1
                num_args = int(a2)
                call_args = param_stack[-num_args:] if num_args > 0 else []
                param_stack = param_stack[:-num_args] if num_args > 0 else param_stack
                blk.append(f'  %{res} = call i32 @{func_name}({", ".join(f"i32 {a}" for a in call_args)})')

            elif op == 'return':
                v = get_val(a1, blk)
                blk.append(f'  ret i32 {v if v else "0"}')

            elif op == 'J':
                target_rel = int(res)
                blk.append(f'  br label %{block_of.get(target_rel, block_of[0])}')

            elif op.startswith('J') and len(op) > 1:
                rop = op[1:]
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_c = {'<': 'slt', '>': 'sgt', '<=': 'sle', '>=': 'sge', '==': 'eq', '!=': 'ne'}[rop]
                target_rel = int(res)
                next_qi = qi + 1
                next_name = block_of.get(next_qi, block_of.get(0, 'block0'))
                target_name = block_of.get(target_rel)
                if target_name is None:
                    target_name = block_of.get(0, next_name)
                elif target_rel in leaders:
                    ti = leaders.index(target_rel)
                    tbe = leaders[ti + 1] if ti + 1 < len(leaders) else len(quads)
                    if tbe - target_rel == 1 and quads[target_rel][0] == 'J':
                        resolved_target = int(quads[target_rel][3])
                        visited = {target_rel}
                        while resolved_target in leaders:
                            ri = leaders.index(resolved_target)
                            rbe = leaders[ri + 1] if ri + 1 < len(leaders) else len(quads)
                            if rbe - resolved_target != 1 or quads[resolved_target][0] != 'J':
                                break
                            if resolved_target in visited:
                                break
                            visited.add(resolved_target)
                            resolved_target = int(quads[resolved_target][3])
                        target_name = block_of.get(resolved_target, target_name)
                blk.append(f'  %brc_{qi} = icmp {ll_c} i32 {v1}, {v2}')
                blk.append(f'  br i1 %brc_{qi}, label %{target_name}, label %{next_name}')

        if not any(blk[-1].strip().startswith(s) for s in ['br ', 'ret ']):
            next_qi = be
            if next_qi in block_of:
                blk.append(f'  br label %{block_of[next_qi]}')
            else:
                blk.append('  ret i32 0')

        blocks_dict[bname] = blk

    # Resolve pass-through blocks (blocks containing only label + unconditional br)
    import re as _re
    br_pattern = _re.compile(r'^\s*br label %(\w+)')
    changed = True
    while changed:
        changed = False
        for bname in list(blocks_dict.keys()):
            blk = blocks_dict[bname]
            if len(blk) == 2:
                m = br_pattern.match(blk[1].strip())
                if m:
                    target = m.group(1)
                    if target != bname:
                        blocks_dict.pop(bname, None)
                        for other_name in blocks_dict:
                            other_blk = blocks_dict[other_name]
                            for j in range(len(other_blk)):
                                other_blk[j] = other_blk[j].replace(f'%{bname}', f'%{target}')
                        changed = True
                        break

    # Build final output
    lines = list(header)
    for bname in sorted(blocks_dict.keys(), key=lambda x: int(x.replace('block', ''))):
        lines.extend(blocks_dict[bname])
        lines.append('')

    lines.append('}')
    return '\n'.join(lines)


def generate_llvm(quads, func_table, inputs=None):
    mod = []
    mod.append('declare i32 @printf(ptr, ...)')
    mod.append('')
    mod.append('@.fmt_num = private constant [3 x i8] c"%d\\00"')
    mod.append('@.fmt_chr = private constant [3 x i8] c"%c\\00"')
    mod.append('')

    if inputs:
        n = len(inputs)
        vals = ', '.join(f'i32 {v}' for v in inputs)
        mod.append(f'@input_data = global [{n} x i32] [{vals}]')
        mod.append('@input_idx = global i32 0')
        global_input_size = n
    else:
        global_input_size = 0
    mod.append('')

    if not func_table:
        func_table = {'main': {'params': [], 'entry': 0}}

    entries = [(name, info['entry']) for name, info in func_table.items() if info.get('entry') is not None]
    entries.sort(key=lambda x: x[1])

    func_ranges = {}
    for idx in range(len(entries)):
        name, start = entries[idx]
        if idx == 0:
            start = 0  # include global inits before first function
        if idx + 1 < len(entries):
            end = max(entries[idx + 1][1], start)
        else:
            end = len(quads)
        fquads = []
        for q in quads[start:end]:
            op, a1, a2, res = q
            if op == 'J' or (op.startswith('J') and len(op) > 1):
                try:
                    target = int(res)
                    if start <= target < end:
                        res = str(target - start)
                except ValueError:
                    pass
            fquads.append((op, a1, a2, res))
        func_ranges[name] = {
            'quads': fquads,
            'params': func_table[name].get('params', [])
        }

    for name in [e[0] for e in entries]:
        finfo = func_ranges[name]
        fn_ll = generate_llvm_for_function(finfo['quads'], name, finfo['params'], inputs, global_input_size)
        mod.append(fn_ll)
        mod.append('')

    return '\n'.join(mod)


# ---- Interpreter for quads ----

class QuadInterpreter:
    def __init__(self, quads, func_table, inputs=None):
        self.quads = quads
        self.func_table = func_table
        self.mem = {}
        self.arrays = {}
        self.inputs = list(inputs) if inputs else []
        self.input_idx = 0
        self.output = []
        self.pc = 0
        self.param_stack = []
        self.return_stack = []
        self.retval = 0

    def val(self, x):
        if x == '_':
            return None
        try:
            return int(x)
        except ValueError:
            return self.mem.get(x, 0)

    def run_function(self, func_name):
        if func_name not in self.func_table:
            return -1, f"Error: 未定义函数 '{func_name}'"
        info = self.func_table[func_name]
        entry = info['entry']
        if entry is None:
            return -1, f"Error: 函数 '{func_name}' 只有声明没有定义"
        params = info['params']
        nparams = len(params)
        for i, pname in enumerate(params):
            if i < len(self.param_stack):
                self.mem[pname] = self.param_stack[-(nparams - i)] if (nparams - i) <= len(self.param_stack) else 0
        if len(self.param_stack) >= nparams:
            self.param_stack = self.param_stack[:-nparams]
        else:
            self.param_stack = []
        return entry, None

    def _execute_quad(self, op, a1, a2, res):
        if op == '=':
            v = self.val(a1)
            self.mem[res] = v
            return True, None

        elif op in ('+', '-', '*', '/', '%'):
            v1 = self.val(a1); v2 = self.val(a2)
            if op == '+': r = v1 + v2
            elif op == '-': r = v1 - v2
            elif op == '*': r = v1 * v2
            elif op == '/':
                if v2 == 0: self.output.append("Error: 除零错误"); return False, None
                r = v1 // v2
            elif op == '%':
                if v2 == 0: self.output.append("Error: 模零错误"); return False, None
                r = v1 % v2
            self.mem[res] = r
            return True, None

        elif op in ('<', '>', '<=', '>=', '==', '!='):
            v1 = self.val(a1); v2 = self.val(a2)
            r = 1 if {
                '<': v1 < v2, '>': v1 > v2, '<=': v1 <= v2,
                '>=': v1 >= v2, '==': v1 == v2, '!=': v1 != v2
            }[op] else 0
            self.mem[res] = r
            return True, None

        elif op in ('&&', '||'):
            v1 = self.val(a1); v2 = self.val(a2)
            if op == '&&':
                r = 1 if (v1 and v2) else 0
            else:
                r = 1 if (v1 or v2) else 0
            self.mem[res] = r
            return True, None

        elif op == 'read':
            if self.input_idx < len(self.inputs):
                v = self.inputs[self.input_idx]; self.input_idx += 1
            else:
                v = 0
            self.mem[res] = v
            return True, None

        elif op == 'write':
            self.output.append(str(self.val(a1)))
            return True, None

        elif op == 'writec':
            self.output.append(chr(self.val(a1)))
            return True, None

        elif op == '=[]':
            arr = self.arrays.get(a1, {})
            self.mem[res] = arr.get(self.val(a2), 0)
            return True, None

        elif op == '[]=':
            v = self.val(a1); idx = self.val(a2)
            if res not in self.arrays: self.arrays[res] = {}
            self.arrays[res][idx] = v
            return True, None

        elif op == 'param':
            self.param_stack.append(self.val(a1))
            return True, None

        elif op == 'call':
            func_name = a1; num_args = int(a2)
            saved_pc = self.pc + 1
            saved_mem = dict(self.mem)
            saved_arrays = {k: dict(v) for k, v in self.arrays.items()}
            entry, err = self.run_function(func_name)
            if entry >= 0:
                self.pc = entry
                self.return_stack.append((saved_pc, res, saved_mem, saved_arrays))
                return True, 'jumped'
            else:
                if err: self.output.append(err)
                return True, None

        elif op == 'return':
            v = self.val(a1)
            if self.return_stack:
                ret_pc, ret_dest, saved_mem, saved_arrays = self.return_stack.pop()
                saved_val = v
                self.mem = saved_mem
                self.arrays = saved_arrays
                if ret_dest != '_' and saved_val is not None:
                    self.mem[ret_dest] = saved_val
                self.pc = ret_pc
                return True, 'jumped'
            else:
                self.retval = v
                return False, None

        elif op == 'J':
            self.pc = int(res)
            return True, 'jumped'

        elif op.startswith('J') and len(op) > 1:
            rop = op[1:]
            v1 = self.val(a1); v2 = self.val(a2)
            cond = {
                '<': v1 < v2, '>': v1 > v2, '<=': v1 <= v2,
                '>=': v1 >= v2, '==': v1 == v2, '!=': v1 != v2
            }[rop]
            if cond:
                self.pc = int(res)
                return True, 'jumped'
            return True, None

        return True, None

    def _execute_range(self, start, end):
        self.pc = start
        while self.pc < end:
            op, a1, a2, res = self.quads[self.pc]
            cont, jumped = self._execute_quad(op, a1, a2, res)
            if not cont: break
            if jumped != 'jumped': self.pc += 1

    def run(self, func_name='main'):
        self.retval = 0
        if func_name in self.func_table and self.func_table[func_name].get('entry') is not None:
            main_entry = self.func_table[func_name]['entry']
        else:
            main_entry = 0

        if main_entry > 0:
            self._execute_range(0, main_entry)

        self.pc = main_entry
        max_steps = 500000
        steps = 0
        while self.pc < len(self.quads):
            steps += 1
            if steps > max_steps:
                self.output.append("Error: 执行步数超限")
                break
            op, a1, a2, res = self.quads[self.pc]
            cont, jumped = self._execute_quad(op, a1, a2, res)
            if not cont: break
            if jumped != 'jumped': self.pc += 1

        return ''.join(self.output)


# ---- Public API ----

def find_llvm_tool(name):
    path = shutil.which(name)
    if path:
        return path
    if os.name == 'nt':
        exe_name = name + '.exe'
        path = shutil.which(exe_name)
        if path:
            return path
        for base in [
            r'C:\Program Files\LLVM\bin',
            r'C:\Program Files (x86)\LLVM\bin',
            r'C:\LLVM\bin',
        ]:
            full = os.path.join(base, exe_name)
            if os.path.isfile(full):
                return full
        try:
            result = subprocess.run(['where', exe_name], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')[0].strip()
        except Exception:
            pass
    return None


def compile_and_run(llvm_ir):
    import uuid
    clang_err = None
    clang = find_llvm_tool('clang')
    if clang:
        try:
            base = os.path.join(tempfile.gettempdir(), f'llvm_{uuid.uuid4().hex[:8]}')
            ll_path = base + '.ll'
            exe_path = base + ('.exe' if os.name == 'nt' else '')
            with open(ll_path, 'w') as f:
                f.write(llvm_ir)
            try:
                compile_res = subprocess.run(
                    [clang, '-x', 'ir', ll_path, '-o', exe_path, '-Wno-override-module'],
                    capture_output=True, text=True, timeout=20
                )
                if compile_res.returncode != 0:
                    clang_err = f'clang编译失败: {compile_res.stderr[:300]}'
                    raise Exception(clang_err)
                run_res = subprocess.run(
                    [exe_path],
                    capture_output=True, text=True, timeout=10
                )
                return run_res.stdout.strip(), run_res.returncode, 'clang'
            finally:
                for f in [ll_path, exe_path]:
                    try: os.unlink(f)
                    except OSError: pass
        except subprocess.TimeoutExpired:
            clang_err = 'clang编译超时'
        except Exception as e:
            clang_err = str(e)

    lli = find_llvm_tool('lli')
    if lli:
        try:
            with tempfile.NamedTemporaryFile(suffix='.ll', mode='w', delete=False) as f:
                f.write(llvm_ir)
                temp_path = f.name
            try:
                run_res = subprocess.run(
                    [lli, temp_path],
                    capture_output=True, text=True, timeout=10
                )
                if run_res.returncode != 0 and not run_res.stdout.strip():
                    raise Exception(f'lli执行失败(返回码{run_res.returncode}): {run_res.stderr[:200]}')
                return run_res.stdout.strip(), run_res.returncode, 'lli'
            finally:
                os.unlink(temp_path)
        except FileNotFoundError:
            raise Exception('未找到lli或clang。请安装LLVM: sudo apt install llvm-clang (Linux) 或 https://llvm.org (Windows)')
        except subprocess.TimeoutExpired:
            raise Exception(f'LLVM执行超时 (clang错误: {clang_err})' if clang_err else 'LLVM执行超时')
        except Exception as e:
            raise Exception(f'LLVM执行失败: {str(e)[:200]}')
    if clang_err:
        raise Exception(clang_err)
    raise Exception('未找到LLVM工具链(clang/lli)。请安装LLVM。')


def process_42_from_quads(quad_text, inputs=None, func_table_text=None):
    """Load 4.2 from quadruple text. Parse quads, run interpreter, generate LLVM, compare.

    Args:
        quad_text: Quadruple format text, one per line: '0: (=, 10, _, a)'
        inputs: List of integer input values for read()
        func_table_text: Optional function table text: 'func=entry,param1,param2; ...'
    """
    try:
        quads = parse_quadruples(quad_text)
        if not quads:
            return {'error': '未找到有效的四元式'}

        if func_table_text:
            func_table = parse_func_table(func_table_text)
        else:
            func_table = build_func_table_from_quads(quads)

        interp = QuadInterpreter(quads, func_table, inputs)
        interp_output = interp.run().strip()
        retval = interp.retval

        llvm_ir = generate_llvm(quads, func_table, inputs)

        try:
            llvm_output, llvm_ret, method = compile_and_run(llvm_ir)
        except FileNotFoundError:
            llvm_output = "错误: 未安装LLVM (clang/lli)"
            llvm_ret = -1
            method = 'none'
        except subprocess.TimeoutExpired:
            llvm_output = "错误: LLVM执行超时"
            llvm_ret = -1
            method = 'none'
        except Exception as e:
            llvm_output = f"错误: {e}"
            llvm_ret = -1
            method = 'none'

        match = (interp_output == llvm_output and retval == llvm_ret)

        return {
            'quadruples': quad_text.strip(),
            'quads_list': quads,
            'llvm_ir': llvm_ir,
            'llvm_output': llvm_output,
            'llvm_retcode': llvm_ret,
            'llvm_method': method,
            'interp_output': interp_output,
            'interp_retval': retval,
            'match': match,
        }
    except Exception as e:
        import traceback
        return {'error': str(e) + '\n' + traceback.format_exc()}


def process_42(source_code, inputs=None):
    """Convenience: run 3.2 first to get quads, then 4.2. For end-to-end testing."""
    from task32 import process_32 as run_32

    # Strip === markers from test file annotations
    clean_lines = []
    parsed_inputs = inputs
    import re as _re
    for line in source_code.split('\n'):
        s = line.strip()
        if s.startswith('=== 输入:'):
            if inputs is None:
                parts = s.replace('=== 输入:', '').replace('===', '').strip()
                if parts and parts != '(无)':
                    nums = _re.findall(r'-?\d+', parts)
                    if nums:
                        parsed_inputs = [int(n) for n in nums]
            continue
        elif s.startswith('==='):
            continue
        clean_lines.append(line)
    clean_code = '\n'.join(clean_lines)

    result_32 = run_32(clean_code, parsed_inputs)
    if 'error' in result_32:
        return {'error': result_32['error']}

    quad_text = result_32['quadruples']
    func_table = result_32['func_table']

    # Serialize func_table for QuadInterpreter
    ft_parts = []
    for name, info in func_table.items():
        if info.get('entry') is not None:
            params_str = ','.join(info.get('params', []))
            ft_parts.append(f'{name}={info["entry"]},{params_str}' if params_str else f'{name}={info["entry"]}')
    func_table_text = '; '.join(ft_parts)

    res = process_42_from_quads(quad_text, parsed_inputs if parsed_inputs is not None else inputs, func_table_text)
    if 'error' in res:
        return res
    res['tokens'] = result_32['tokens']
    res['ast'] = result_32['ast']
    res['symbol_table'] = result_32['symbol_table']
    return res
