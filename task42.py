# ========== 任务4.2：四元式 → LLVM IR → 编译执行 ==========
# 将3.2生成的四元式序列转换为LLVM IR，通过clang/lli编译执行，
# 并与四元式解释器的执行结果进行对比验证

# 导入正则表达式模块，用于解析四元式文本格式
import re
# subprocess模块用于调用外部LLVM工具（clang编译、lli执行）
import subprocess
# os模块用于文件路径操作和系统命令
import os
# tempfile模块用于创建临时文件（LLVM IR文件）
import tempfile
# shutil模块用于查找可执行文件路径
import shutil

# ========== parse_quadruples函数：解析四元式文本 ==========
# 将文本格式的四元式转换为元组列表
# 输入格式示例:
#   0: (=, 10, _, a)
#   1: (+, a, b, t1)
# 输出: [('=', '10', '_', 'a'), ('+', 'a', 'b', 't1'), ...]
def parse_quadruples(text):
    quads = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue                             # 跳过空行
        # 如果包含冒号，去掉行号和冒号前缀（如"0: "）
        if ':' in line:
            line = line.split(':', 1)[1].strip()
        # 正则匹配四元式格式: (op, arg1, arg2, result)
        m = re.match(r'\(([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)', line)
        if m:
            op, a1, a2, a3 = m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
            quads.append((op, a1, a2, a3))
    return quads


# ========== parse_func_table函数：解析函数表文本 ==========
# 将函数表文本解析为字典
# 输入格式: 'main=0; swap=5,a,b; factorial=10,n'
# 输出: {'main': {'params': [], 'entry': 0}, 'swap': {'params': ['a', 'b'], 'entry': 5}, ...}
def parse_func_table(text):
    """Parse 'func=entry,param1,param2; func2=entry2,p1' format."""
    table = {}
    if not text:
        return table
    # 按分号分隔多个函数
    for part in text.split(';'):
        part = part.strip()
        if '=' not in part:
            continue
        name, rest = part.split('=', 1)     # 分离函数名和后续信息
        name = name.strip()
        parts = rest.split(',')             # 按逗号分隔入口行号和参数
        entry = int(parts[0].strip())       # 第一个是入口行号
        params = [p.strip() for p in parts[1:]] if len(parts) > 1 else []  # 后续是参数名列表
        table[name] = {'params': params, 'entry': entry}
    return table


# ========== build_func_table_from_quads函数：从四元式推断函数表 ==========
# 当用户未提供显式函数表时，通过分析四元式序列自动推断函数边界和参数
# 策略：通过return指令识别函数边界，通过call指令识别被调函数名
# 通过分析函数入口与首个使用变量之间的依赖关系推断参数
def build_func_table_from_quads(quads):
    """Try to infer function table from quads when none provided."""
    func_names = set()
    # 收集所有被call指令调用的函数名
    for op, a1, a2, res in quads:
        if op == 'call':
            func_names.add(a1)

    if len(func_names) == 0:
        return {'main': {'params': [], 'entry': 0}}

    # Find all returns and group consecutive ones
    # 找出所有return指令的位置，连续return属于同一函数的控制流
    return_positions = [i for i, (op, _, _, _) in enumerate(quads) if op == 'return']
    if not return_positions:
        return {'main': {'params': [], 'entry': 0}}

    # Group consecutive returns (they belong to the same function's control flow)
    # 分组连续return（同一函数内可能有多个return路径）
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
    # 每组最后一个return的下一条指令标记下一个函数的开始
    boundaries = [0]                     # 第一个函数从0开始
    for g in groups:
        boundaries.append(g[-1] + 1)
    boundaries = [b for b in boundaries if b < len(quads)]  # 过滤越界

    # Assign function names: main is always first, then called functions
    # 分配函数名：main始终是第一个，其余按函数名字典序排列
    func_names_list = sorted(func_names)
    table = {}
    max_funcs = len(func_names_list) + 1  # +1 for main
    if len(boundaries) > max_funcs:
        boundaries = boundaries[:max_funcs]  # 多余的边界可能是内联return

    # 遍历每个函数边界，推断函数参数
    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(quads)
        used_vars = set()      # 先使用后赋值的变量（疑似参数）
        assigned_vars = set()  # 先赋值后使用的变量
        params = []
        for qi in range(start, end):
            op, a1, a2, res = quads[qi]
            if op == '=':
                # 赋值指令：记录被赋值的变量
                if res and res != '_' and not res.isdigit() and not (res.startswith('t') and res[1:].isdigit()):
                    assigned_vars.add(res)
            else:
                # 其他指令：检查a1和a2是否引用了尚未赋值的变量（可能是参数）
                for arg in [a1, a2]:
                    if arg and arg != '_' and not arg.isdigit():
                        if not (arg.startswith('t') and arg[1:].isdigit()):  # 过滤临时变量
                            if arg not in assigned_vars and arg not in used_vars:
                                used_vars.add(arg)
                                params.append(arg)  # 首次出现且非赋值→参数

        # 命名函数
        if idx == 0:
            name = 'main'                           # 第一个函数是main
        elif idx <= len(func_names_list):
            name = func_names_list[idx - 1]         # 使用已知的函数名
        else:
            name = f'_func{idx}'                    # 未知函数名自动命名

        table[name] = {'params': params, 'entry': start}

    # 确保'main'在表中
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

# ---- LLVM IR Generation ----
# ========== generate_llvm_for_function函数：为单个函数生成LLVM IR ==========
# 将四元式序列划分为基本块，生成SSA形式（静态单赋值）的LLVM IR代码
# 支持：变量alloca/store/load、算术运算、比较运算、printf调用、数组操作、函数调用、控制流
# 参数 quads: 该函数的四元式子序列（已重映射地址）
# 参数 func_name: 函数名
# 参数 params: 参数名列表
# 参数 inputs: 全局输入数据（用于read()指令）
# 参数 global_input_size: 全局输入数组大小
# 返回值: LLVM IR文本（单个函数的define体）
def generate_llvm_for_function(quads, func_name, params, inputs, global_input_size):
    # 确定基本块入口（leaders）：J跳转的目标 + J的下一条
    leaders = {0}
    for i, (op, a1, a2, res) in enumerate(quads):
        if op == 'J' or (op.startswith('J') and len(op) > 1):
            try:
                t = int(res)
                if 0 <= t < len(quads):
                    leaders.add(t)           # 跳转目标是基本块入口
            except ValueError:
                pass
            if i + 1 < len(quads):
                leaders.add(i + 1)           # 跳转的下一条也是基本块入口
    leaders = sorted(leaders)

    # 为每个基本块分配名称 {行号: 'blockN'}
    block_of = {}
    for idx, l in enumerate(leaders):
        block_of[l] = f"block{idx}"

    # 收集所有非临时变量
    all_vars = set()   # 所有用户定义变量
    arr_vars = set()   # 数组变量
    for op, a1, a2, res in quads:
        for a in [a1, a2, res]:
            if a and a != '_' and not a.isdigit():
                if not (a.startswith('t') and a[1:].isdigit()):  # 排除临时变量t1,t2,...
                    all_vars.add(a)
    for op, a1, a2, res in quads:
        if op == '[]=':
            arr_vars.add(res)                # 记录数组写操作的目标
        elif op == '=[]':
            arr_vars.add(a1)                 # 记录数组读操作的源

    # 生成函数头：define i32 @func(i32 %param1, i32 %param2, ...) {
    param_str = ', '.join(f'i32 %{p}' for p in params)
    header = []
    header.append(f'define i32 @{func_name}({param_str}) {{')
    header.append('entry:')

    # 为所有变量分配栈空间（alloca）
    # 数组分配为 [100 x i32] 类型（固定大小100），普通变量分配为 i32
    for v in sorted(all_vars):
        if v in arr_vars:
            header.append(f'  %{v}_ptr = alloca [100 x i32]')
        else:
            header.append(f'  %{v}_ptr = alloca i32')

    # 将函数参数值存储到栈变量中
    for p in params:
        header.append(f'  store i32 %{p}, ptr %{p}_ptr')

    # 跳转到第一个基本块
    first_block = block_of[0]
    header.append(f'  br label %{first_block}')
    header.append('')

    tmp_cnt = 0  # LLVM临时变量计数器（%rt0, %rt1, ...）

    # 创建新的LLVM临时变量
    def new_tmp():
        nonlocal tmp_cnt
        v = f"%rt{tmp_cnt}"
        tmp_cnt += 1
        return v

    # 获取操作数的LLVM表示
    # 数字直接返回，变量返回其加载后的值（生成load指令）
    # 数组变量返回指向数组的指针（转换为i32）
    # 返回值: LLVM操作数字符串
    def get_val(arg, blk):
        nonlocal tmp_cnt
        arg = arg.strip()
        if arg == '_':
            return None
        # 数字字面量直接返回
        if arg.isdigit() or (arg.startswith('-') and arg[1:].isdigit()):
            return arg
        # 临时变量（t1,t2,...）直接使用%t1,%t2,...
        if arg.startswith('t') and arg[1:].isdigit():
            return f'%{arg}'
        # 数组变量：返回指针（转为i32存储）
        if arg in arr_vars:
            t = new_tmp()
            blk.append(f'  {t} = ptrtoint ptr %{arg}_ptr to i32')
            return t
        # 普通变量：生成load指令加载值
        t = new_tmp()
        blk.append(f'  {t} = load i32, ptr %{arg}_ptr')
        return t

    param_stack = []   # 函数调用参数栈
    blocks_dict = {}   # 基本块字典：{块名: [指令列表]}

    # 遍历每个基本块区间，生成LLVM IR指令
    for li in range(len(leaders)):
        bs = leaders[li]                                      # 块起始行号
        be = leaders[li + 1] if li + 1 < len(leaders) else len(quads)  # 块结束行号（下一块起始）
        bname = block_of[bs]                                  # 块名称
        blk = [f'{bname}:']                                   # 块指令列表
        has_br = False

        # 遍历块内的每条四元式
        for qi in range(bs, be):
            op, a1, a2, res = quads[qi]

            # 赋值指令：store
            if op == '=':
                v = get_val(a1, blk)
                blk.append(f'  store i32 {v}, ptr %{res}_ptr')

            # 算术运算：add, sub, mul, sdiv, srem
            elif op in ('+', '-', '*', '/', '%'):
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_op = {'+': 'add', '-': 'sub', '*': 'mul', '/': 'sdiv', '%': 'srem'}[op]
                blk.append(f'  %{res} = {ll_op} i32 {v1}, {v2}')

            # 关系比较：icmp slt/sgt/sle/sge/eq/ne → zext到i32
            elif op in ('<', '>', '<=', '>=', '==', '!='):
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_c = {'<': 'slt', '>': 'sgt', '<=': 'sle', '>=': 'sge', '==': 'eq', '!=': 'ne'}[op]
                blk.append(f'  %{res}_i1 = icmp {ll_c} i32 {v1}, {v2}')  # icmp返回i1
                blk.append(f'  %{res} = zext i1 %{res}_i1 to i32')        # 扩展到i32匹配预期

            # 逻辑与：&& → icmp ne 0 + and + zext
            elif op == '&&':
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                blk.append(f'  %{res}_c1 = icmp ne i32 {v1}, 0')
                blk.append(f'  %{res}_c2 = icmp ne i32 {v2}, 0')
                blk.append(f'  %{res}_b = and i1 %{res}_c1, %{res}_c2')
                blk.append(f'  %{res} = zext i1 %{res}_b to i32')

            # 逻辑或：|| → icmp ne 0 + or + zext
            elif op == '||':
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                blk.append(f'  %{res}_c1 = icmp ne i32 {v1}, 0')
                blk.append(f'  %{res}_c2 = icmp ne i32 {v2}, 0')
                blk.append(f'  %{res}_b = or i1 %{res}_c1, %{res}_c2')
                blk.append(f'  %{res} = zext i1 %{res}_b to i32')

            # read指令：从全局输入数组读取下一个值
            elif op == 'read':
                if inputs:
                    # 通过全局索引@input_idx和全局数组@input_data读取
                    blk.append(f'  %ld_{qi} = load i32, ptr @input_idx')
                    blk.append(f'  %gp_{qi} = getelementptr [{global_input_size} x i32], ptr @input_data, i32 0, i32 %ld_{qi}')
                    blk.append(f'  %{res} = load i32, ptr %gp_{qi}')
                    blk.append(f'  %ni_{qi} = add i32 %ld_{qi}, 1')        # idx++
                    blk.append(f'  store i32 %ni_{qi}, ptr @input_idx')
                else:
                    blk.append(f'  %{res} = add i32 0, 0')                  # 无输入时返回0

            # write指令：输出整数（通过printf）
            elif op == 'write':
                v = get_val(a1, blk)
                blk.append(f'  call i32 (ptr, ...) @printf(ptr @.fmt_num, i32 {v})')

            # writec指令：输出字符（通过printf的%c格式）
            elif op == 'writec':
                v = get_val(a1, blk)
                blk.append(f'  call i32 (ptr, ...) @printf(ptr @.fmt_chr, i32 {v})')

            # 读数组元素：=[] arr, idx, res → res = arr[idx]
            elif op == '=[]':
                idx = get_val(a2, blk)
                blk.append(f'  %gp_{res} = getelementptr [100 x i32], ptr %{a1}_ptr, i32 0, i32 {idx}')
                blk.append(f'  %{res} = load i32, ptr %gp_{res}')

            # 写数组元素：[]= val, idx, arr → arr[idx] = val
            # 注意：a1是值，a2是索引，res是数组名
            elif op == '[]=':
                v = get_val(a1, blk)                            # 要写入的值
                idx = get_val(a2, blk)                          # 索引
                blk.append(f'  %gp_{qi} = getelementptr [100 x i32], ptr %{res}_ptr, i32 0, i32 {idx}')
                blk.append(f'  store i32 {v}, ptr %gp_{qi}')

            # param指令：将参数值压栈（用于后续call指令）
            elif op == 'param':
                v = get_val(a1, blk)
                param_stack.append(v)

            # call指令：调用函数
            elif op == 'call':
                func_name = a1
                num_args = int(a2)
                # 从param_stack中取出最后num_args个参数
                call_args = param_stack[-num_args:] if num_args > 0 else []
                param_stack = param_stack[:-num_args] if num_args > 0 else param_stack
                blk.append(f'  %{res} = call i32 @{func_name}({", ".join(f"i32 {a}" for a in call_args)})')

            # return指令：函数返回
            elif op == 'return':
                v = get_val(a1, blk)
                blk.append(f'  ret i32 {v if v else "0"}')

            # 无条件跳转：J _, _, target
            elif op == 'J':
                target_rel = int(res)
                blk.append(f'  br label %{block_of.get(target_rel, block_of[0])}')

            # 条件跳转：J<op> a1, a2, target_rel
            # 生成icmp比较 + br条件跳转
            elif op.startswith('J') and len(op) > 1:
                rop = op[1:]                                     # 提取关系操作符
                v1 = get_val(a1, blk)
                v2 = get_val(a2, blk)
                ll_c = {'<': 'slt', '>': 'sgt', '<=': 'sle', '>=': 'sge', '==': 'eq', '!=': 'ne'}[rop]
                target_rel = int(res)
                # 计算next块名（跳转失败的目标）和target块名（跳转成功的目标）
                next_qi = qi + 1
                next_name = block_of.get(next_qi, block_of.get(0, 'block0'))
                target_name = block_of.get(target_rel)
                if target_name is None:
                    target_name = block_of.get(0, next_name)
                elif target_rel in leaders:
                    # 处理目标块是纯跳转块的情况：跟随跳转链找到最终目标
                    ti = leaders.index(target_rel)
                    tbe = leaders[ti + 1] if ti + 1 < len(leaders) else len(quads)
                    if tbe - target_rel == 1 and quads[target_rel][0] == 'J':
                        # 目标块只有一条无条件跳转，跟随跳转到真正目标
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

        # 块末尾：如果没有终止指令（br或ret），添加跳转到下个基本块的br
        if not any(blk[-1].strip().startswith(s) for s in ['br ', 'ret ']):
            next_qi = be
            if next_qi in block_of:
                blk.append(f'  br label %{block_of[next_qi]}')
            else:
                blk.append('  ret i32 0')        # 函数末尾如果没有终止，返回0

        blocks_dict[bname] = blk

    # Resolve pass-through blocks (blocks containing only label + unconditional br)
    # 消除穿透基本块：如果某个基本块只有标签+一条无条件br，将其从blocks_dict中移除，
    # 并将所有引用该块的br指令直接指向目标块
    import re as _re
    br_pattern = _re.compile(r'^\s*br label %(\w+)')
    changed = True
    while changed:
        changed = False
        for bname in list(blocks_dict.keys()):
            blk = blocks_dict[bname]
            # 只有标签和一条无条件跳转的基本块
            if len(blk) == 2:
                m = br_pattern.match(blk[1].strip())
                if m:
                    target = m.group(1)
                    if target != bname:
                        blocks_dict.pop(bname, None)        # 移除穿透块
                        for other_name in blocks_dict:
                            other_blk = blocks_dict[other_name]
                            for j in range(len(other_blk)):
                                # 将所有对穿透块的引用替换为穿透目标
                                other_blk[j] = other_blk[j].replace(f'%{bname}', f'%{target}')
                        changed = True
                        break

    # Build final output
    # 组装最终的LLVM IR输出：函数头 + 各基本块（按编号排序）
    lines = list(header)
    for bname in sorted(blocks_dict.keys(), key=lambda x: int(x.replace('block', ''))):
        lines.extend(blocks_dict[bname])
        lines.append('')

    lines.append('}')
    return '\n'.join(lines)


# ========== generate_llvm函数：生成完整LLVM IR模块 ==========
# 为整个程序（可能包含多个函数）生成LLVM IR模块
# 包括：printf声明、格式字符串、全局输入数据、各函数定义
# 参数 quads: 完整四元式列表
# 参数 func_table: 函数表（含入口和参数信息）
# 参数 inputs: 输入数据列表
# 返回值: 完整LLVM IR文本
def generate_llvm(quads, func_table, inputs=None):
    mod = []
    # 声明printf外部函数（可变参数）
    mod.append('declare i32 @printf(ptr, ...)')
    mod.append('')
    # 定义格式化字符串常量
    mod.append('@.fmt_num = private constant [3 x i8] c"%d\\00"')   # %d格式
    mod.append('@.fmt_chr = private constant [3 x i8] c"%c\\00"')   # %c格式
    mod.append('')

    # 如果有输入数据，定义全局输入数组和索引
    if inputs:
        n = len(inputs)
        vals = ', '.join(f'i32 {v}' for v in inputs)
        mod.append(f'@input_data = global [{n} x i32] [{vals}]')    # 输入数据数组
        mod.append('@input_idx = global i32 0')                      # 当前读取索引
        global_input_size = n
    else:
        global_input_size = 0
    mod.append('')

    # 处理函数表
    if not func_table:
        func_table = {'main': {'params': [], 'entry': 0}}

    # 按入口地址排序函数
    entries = [(name, info['entry']) for name, info in func_table.items() if info.get('entry') is not None]
    entries.sort(key=lambda x: x[1])

    # 为每个函数切分四元式范围并重映射地址（相对地址）
    func_ranges = {}
    for idx in range(len(entries)):
        name, start = entries[idx]
        if idx == 0:
            start = 0  # include global inits before first function
        if idx + 1 < len(entries):
            end = max(entries[idx + 1][1], start)
        else:
            end = len(quads)
        # 截取该函数的四元式子序列
        fquads = []
        for q in quads[start:end]:
            op, a1, a2, res = q
            # 重映射跳转目标：绝对地址→相对于函数起始的偏移
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

    # 为每个函数生成LLVM IR
    for name in [e[0] for e in entries]:
        finfo = func_ranges[name]
        fn_ll = generate_llvm_for_function(finfo['quads'], name, finfo['params'], inputs, global_input_size)
        mod.append(fn_ll)
        mod.append('')

    return '\n'.join(mod)


# ---- Interpreter for quads ----

# ---- Interpreter for quads ----
# ========== QuadInterpreter类：四元式解释器（用于4.2对比验证） ==========
# 与task32中的Interpreter功能相同，但有细微的实现差异（如使用字典实现switch）
# 用于对四元式进行解释执行，生成结果与LLVM编译执行进行对比
class QuadInterpreter:
    def __init__(self, quads, func_table, inputs=None):
        self.quads = quads              # 四元式列表
        self.func_table = func_table    # 函数表
        self.mem = {}                   # 变量内存
        self.arrays = {}                # 数组内存（稀疏存储）
        self.inputs = list(inputs) if inputs else []  # 输入数据列表
        self.input_idx = 0              # 输入读取索引
        self.output = []                # 输出字符串列表
        self.pc = 0                     # 程序计数器
        self.param_stack = []           # 函数调用参数栈
        self.return_stack = []          # 返回地址栈
        self.retval = 0                 # 返回值

    # 获取操作数的实际值
    def val(self, x):
        if x == '_':
            return None
        try:
            return int(x)
        except ValueError:
            return self.mem.get(x, 0)

    # 运行函数：获取入口地址，绑定参数
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

    # 执行单条四元式（与task32.Interpreter._execute_quad逻辑相同，使用字典优化条件）
    def _execute_quad(self, op, a1, a2, res):
        # 赋值
        if op == '=':
            v = self.val(a1)
            self.mem[res] = v
            return True, None

        # 算术运算（+ - * / %）
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

        # 关系运算（通过字典分派提高效率）
        elif op in ('<', '>', '<=', '>=', '==', '!='):
            v1 = self.val(a1); v2 = self.val(a2)
            r = 1 if {
                '<': v1 < v2, '>': v1 > v2, '<=': v1 <= v2,
                '>=': v1 >= v2, '==': v1 == v2, '!=': v1 != v2
            }[op] else 0
            self.mem[res] = r
            return True, None

        # 逻辑运算
        elif op in ('&&', '||'):
            v1 = self.val(a1); v2 = self.val(a2)
            if op == '&&':
                r = 1 if (v1 and v2) else 0
            else:
                r = 1 if (v1 or v2) else 0
            self.mem[res] = r
            return True, None

        # 输入读取
        elif op == 'read':
            if self.input_idx < len(self.inputs):
                v = self.inputs[self.input_idx]; self.input_idx += 1
            else:
                v = 0
            self.mem[res] = v
            return True, None

        # 整数输出
        elif op == 'write':
            self.output.append(str(self.val(a1)))
            return True, None

        # 字符输出
        elif op == 'writec':
            self.output.append(chr(self.val(a1)))
            return True, None

        # 读数组元素
        elif op == '=[]':
            arr = self.arrays.get(a1, {})
            self.mem[res] = arr.get(self.val(a2), 0)
            return True, None

        # 写数组元素
        elif op == '[]=':
            v = self.val(a1); idx = self.val(a2)
            if res not in self.arrays: self.arrays[res] = {}
            self.arrays[res][idx] = v
            return True, None

        # 参数压栈
        elif op == 'param':
            self.param_stack.append(self.val(a1))
            return True, None

        # 函数调用
        elif op == 'call':
            func_name = a1; num_args = int(a2)
            # 保存调用者上下文
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

        # 函数返回
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

        # 无条件跳转
        elif op == 'J':
            self.pc = int(res)
            return True, 'jumped'

        # 条件跳转
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

    # 在范围内依次执行四元式（用于全局初始化）
    def _execute_range(self, start, end):
        self.pc = start
        while self.pc < end:
            op, a1, a2, res = self.quads[self.pc]
            cont, jumped = self._execute_quad(op, a1, a2, res)
            if not cont: break
            if jumped != 'jumped': self.pc += 1

    # 运行程序入口
    def run(self, func_name='main'):
        self.retval = 0
        # 获取入口地址
        if func_name in self.func_table and self.func_table[func_name].get('entry') is not None:
            main_entry = self.func_table[func_name]['entry']
        else:
            main_entry = 0

        # 执行全局初始化
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

# ---- Public API ----
# ========== find_llvm_tool函数：查找LLVM工具链路径 ==========
# 在系统PATH和常见安装目录中搜索clang/lli等LLVM工具
# 参数 name: 工具名（如'clang', 'lli'）
# 返回值: 完整路径字符串，未找到返回None
def find_llvm_tool(name):
    # 首先尝试在PATH中查找
    path = shutil.which(name)
    if path:
        return path
    # Windows平台：尝试.exe后缀和常见安装路径
    if os.name == 'nt':
        exe_name = name + '.exe'
        path = shutil.which(exe_name)
        if path:
            return path
        for base in [
            r'C:\Program Files\LLVM\bin',          # 64位默认安装路径
            r'C:\Program Files (x86)\LLVM\bin',    # 32位默认安装路径
            r'C:\LLVM\bin',                        # 自定义安装路径
        ]:
            full = os.path.join(base, exe_name)
            if os.path.isfile(full):
                return full
        # 尝试使用where命令查找
        try:
            result = subprocess.run(['where', exe_name], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')[0].strip()  # 返回第一个匹配
        except Exception:
            pass
    return None


# ========== compile_and_run函数：编译并执行LLVM IR ==========
# 优先使用clang编译为可执行文件再运行，若失败则回退到lli直接解释执行
# 参数 llvm_ir: LLVM IR文本
# 返回值: (输出字符串, 返回码, 编译方式)
def compile_and_run(llvm_ir):
    import uuid  # 用于生成唯一临时文件名
    clang_err = None
    # 方式1：clang编译为可执行文件
    clang = find_llvm_tool('clang')
    if clang:
        try:
            # 创建唯一临时文件路径
            base = os.path.join(tempfile.gettempdir(), f'llvm_{uuid.uuid4().hex[:8]}')
            ll_path = base + '.ll'                     # LLVM IR源文件
            exe_path = base + ('.exe' if os.name == 'nt' else '')  # 编译产物
            with open(ll_path, 'w') as f:
                f.write(llvm_ir)                       # 写入IR文件
            try:
                # 调用clang编译IR为可执行文件
                compile_res = subprocess.run(
                    [clang, '-x', 'ir', ll_path, '-o', exe_path, '-Wno-override-module'],
                    capture_output=True, text=True, timeout=20
                )
                if compile_res.returncode != 0:
                    clang_err = f'clang编译失败: {compile_res.stderr[:300]}'
                    raise Exception(clang_err)
                # 执行编译产物
                run_res = subprocess.run(
                    [exe_path],
                    capture_output=True, text=True, timeout=10
                )
                return run_res.stdout.strip(), run_res.returncode, 'clang'
            finally:
                # 清理临时文件
                for f in [ll_path, exe_path]:
                    try: os.unlink(f)
                    except OSError: pass
        except subprocess.TimeoutExpired:
            clang_err = 'clang编译超时'
        except Exception as e:
            clang_err = str(e)

    # 方式2：clang失败时使用lli解释执行
    lli = find_llvm_tool('lli')
    if lli:
        try:
            # 写入临时IR文件
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
                os.unlink(temp_path)                   # 清理临时文件
        except FileNotFoundError:
            raise Exception('未找到lli或clang。请安装LLVM: sudo apt install llvm-clang (Linux) 或 https://llvm.org (Windows)')
        except subprocess.TimeoutExpired:
            raise Exception(f'LLVM执行超时 (clang错误: {clang_err})' if clang_err else 'LLVM执行超时')
        except Exception as e:
            raise Exception(f'LLVM执行失败: {str(e)[:200]}')
    if clang_err:
        raise Exception(clang_err)
    # 两种工具都找不到
    raise Exception('未找到LLVM工具链(clang/lli)。请安装LLVM。')


# ========== process_42_from_quads函数：从四元式文本执行4.2完整流程 ==========
# 解析四元式 → (可选)解析函数表 → 解释器执行 → 生成LLVM IR → 编译执行 → 对比结果
# 参数 quad_text: 四元式格式文本
# 参数 inputs: 输入整数列表
# 参数 func_table_text: 函数表文本（可选，未提供时自动推断）
# 返回值: 字典，包含解释器结果、LLVM结果和对比信息
def process_42_from_quads(quad_text, inputs=None, func_table_text=None):
    """Load 4.2 from quadruple text. Parse quads, run interpreter, generate LLVM, compare.

    Args:
        quad_text: Quadruple format text, one per line: '0: (=, 10, _, a)'
        inputs: List of integer input values for read()
        func_table_text: Optional function table text: 'func=entry,param1,param2; ...'
    """
    try:
        # 解析四元式文本
        quads = parse_quadruples(quad_text)
        if not quads:
            return {'error': '未找到有效的四元式'}

        # 解析或推断函数表
        if func_table_text:
            func_table = parse_func_table(func_table_text)        # 使用提供的函数表
        else:
            func_table = build_func_table_from_quads(quads)       # 自动推断函数表

        # 四元式解释器执行（作为对比基准）
        interp = QuadInterpreter(quads, func_table, inputs)
        interp_output = interp.run().strip()                      # 解释器输出
        retval = interp.retval                                    # 解释器返回值

        # 生成LLVM IR
        llvm_ir = generate_llvm(quads, func_table, inputs)

        # 编译并执行LLVM IR
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

        # 对比解释器结果与LLVM结果
        match = (interp_output == llvm_output and retval == llvm_ret)

        return {
            'quadruples': quad_text.strip(),          # 原始四元式文本
            'quads_list': quads,                      # 解析后的四元式列表
            'llvm_ir': llvm_ir,                       # 生成的LLVM IR
            'llvm_output': llvm_output,               # LLVM执行输出
            'llvm_retcode': llvm_ret,                 # LLVM执行返回码
            'llvm_method': method,                    # 编译方式（clang/lli/none）
            'interp_output': interp_output,           # 解释器输出
            'interp_retval': retval,                  # 解释器返回值
            'match': match,                           # 结果是否一致
        }
    except Exception as e:
        import traceback
        return {'error': str(e) + '\n' + traceback.format_exc()}


# ========== process_42函数：从源代码执行4.2端到端流程 ==========
# 先调用task32的process_32生成四元式，再将四元式传递给process_42_from_quads
# 用于通过Web界面从源代码直达LLVM对比
def process_42(source_code, inputs=None):
    """Convenience: run 3.2 first to get quads, then 4.2. For end-to-end testing."""
    from task32 import process_32 as run_32

    # Strip === markers from test file annotations
    # 去除测试文件中的===标记行，提取纯源代码
    clean_lines = []
    parsed_inputs = inputs
    import re as _re
    for line in source_code.split('\n'):
        s = line.strip()
        if s.startswith('=== 输入:'):
            # 提取输入数据
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

    # 运行3.2流程获取四元式
    result_32 = run_32(clean_code, parsed_inputs)
    if 'error' in result_32:
        return {'error': result_32['error']}

    quad_text = result_32['quadruples']
    func_table = result_32['func_table']

    # Serialize func_table for QuadInterpreter
    # 序列化函数表为文本格式
    ft_parts = []
    for name, info in func_table.items():
        if info.get('entry') is not None:
            params_str = ','.join(info.get('params', []))
            ft_parts.append(f'{name}={info["entry"]},{params_str}' if params_str else f'{name}={info["entry"]}')
    func_table_text = '; '.join(ft_parts)

    # 运行4.2流程
    res = process_42_from_quads(quad_text, parsed_inputs if parsed_inputs is not None else inputs, func_table_text)
    if 'error' in res:
        return res
    # 附加3.2的前端分析结果
    res['tokens'] = result_32['tokens']
    res['ast'] = result_32['ast']
    res['symbol_table'] = result_32['symbol_table']
    return res
