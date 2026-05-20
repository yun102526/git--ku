"""批量生成 3.2 和 4.2 的 .int / .doc 文件。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from task32 import process_32
from task42 import process_42_from_quads, process_42

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST32_DIR = os.path.join(BASE_DIR, 'test_cases_32')
TEST42_DIR = os.path.join(BASE_DIR, 'test_cases_42')
OUT32_DIR = os.path.join(BASE_DIR, 'test_output_32')
OUT42_DIR = os.path.join(BASE_DIR, 'test_output_42')
RESULT_FILE = os.path.join(BASE_DIR, 'test_results.txt')


def read_test_file(filepath):
    for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def parse_42_meta(content):
    """Parse 4.2 test file: extract quads, inputs, func_table from === markers."""
    lines = content.split('\n')
    quad_lines = []
    inputs = []
    func_table_text = ''
    section = 'title'
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):
            section = 'input'
            parts = s.replace('=== 输入:', '').replace('===', '').strip()
            if parts and parts != '(无)':
                try:
                    ss = parts.replace(',', ' ')
                    inputs = [int(x) for x in ss.split() if x]
                except ValueError:
                    pass
        elif s.startswith('=== 函数表:'):
            section = 'func'
            func_table_text = s.replace('=== 函数表:', '').replace('===', '').strip()
        elif s.startswith('=== 预期'):
            section = 'skip'
        elif s.startswith('===') and section == 'title':
            section = 'quads'
        elif s.startswith('==='):
            section = 'skip'
        elif section == 'quads' or section == 'title':
            section = 'quads'
            quad_lines.append(line)
        elif section == 'func':
            func_table_text += ' ' + s.strip()
    return '\n'.join(quad_lines).strip(), inputs, func_table_text.strip()


def parse_32_meta(content):
    lines = content.split('\n')
    source_lines = []
    inputs = []
    in_source = True
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):
            in_source = False
            parts = s.replace('=== 输入:', '').replace('===', '').strip()
            if parts and parts != '(无)':
                try:
                    ss = parts.replace(',', ' ')
                    inputs = [int(x) for x in ss.split() if x]
                except ValueError:
                    pass
        elif s.startswith('===') and not in_source:
            continue
        elif s.startswith('==='):
            continue
        elif in_source:
            source_lines.append(line)
    return '\n'.join(source_lines), inputs


def generate_32(name, source_code, inputs):
    res = process_32(source_code, inputs)
    int_path = os.path.join(OUT32_DIR, f'{name}.int')
    doc_path = os.path.join(OUT32_DIR, f'{name}.doc')

    if 'error' in res:
        with open(int_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 源文件: {name}.txt ---\n--- 源代码 ---\n{source_code}\n\n--- 错误信息 ---\n{res['error']}\n")
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 错误信息 ---\n{res['error']}\n")
        return False, res['error']

    with open(int_path, 'w', encoding='utf-8') as f:
        f.write(f"--- 成功加载外部源文件: 测试用例/3.2/{name}.txt ---\n")
        f.write(f"--- [3.2测试运行] 已进入测试执行流程 ---\n")
        f.write(f"测试文件: {name}.txt\n")
        if inputs:
            f.write(f"默认输入: {inputs}\n")
        f.write("\n--- [编译前端] Token序列 (Tokens) ---\n")
        f.write(res['tokens'])
        f.write("\n\n--- [编译前端] 抽象语法树 (AST) ---\n")
        f.write(res['ast'])
        f.write("\n\n--- [编译前端] 符号表 (Symbol Table) ---\n")
        f.write(res['symbol_table'])
        f.write("\n")

    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(f"--- [编译中端] 生成的四元式流 (Quadruples) ---\n")
        f.write(res['quadruples'])
        f.write(f"\n\n--- [编译后端] 解释器执行过程 ---\n")
        f.write(f"Program output: {res['output']}\n")
        if 'retval' in res:
            f.write(f"Return value: {res['retval']}\n")
    return True, None


def generate_42(name, quad_text, inputs, func_table_text):
    res = process_42_from_quads(quad_text, inputs, func_table_text)
    int_path = os.path.join(OUT42_DIR, f'{name}.int')
    doc_path = os.path.join(OUT42_DIR, f'{name}.doc')

    if 'error' in res:
        with open(int_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 源文件: {name}.txt ---\n--- 四元式 ---\n{quad_text}\n\n--- 错误信息 ---\n{res['error']}\n")
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 错误信息 ---\n{res['error']}\n--- 对比结果 ---\n因错误无法对比\n")
        return False, res['error']

    with open(int_path, 'w', encoding='utf-8') as f:
        f.write(f"--- 成功加载: 测试用例/4.2/{name}.txt ---\n")
        f.write(f"--- [4.2] 四元式 → LLVM IR → 编译执行 ---\n")
        f.write(f"测试文件: {name}.txt\n")
        if inputs:
            f.write(f"输入: {inputs}\n")
        f.write("\n--- [输入] 四元式流 ---\n")
        f.write(res['quadruples'])
        f.write("\n\n--- [4.2 输出] LLVM IR 代码 ---\n")
        f.write(res['llvm_ir'])
        f.write("\n")

    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(f"--- [解释器] 四元式解释器执行结果 ---\n")
        f.write(f"输出: {res['interp_output']}\n返回值: {res['interp_retval']}\n\n")
        f.write(f"--- [4.2 LLVM] LLVM编译执行结果 ---\n")
        f.write(f"编译方式: {res.get('llvm_method', 'unknown')}\n")
        f.write(f"输出: {res['llvm_output']}\n返回值: {res['llvm_retcode']}\n\n")
        f.write(f"--- [对比] 四元式解释器 vs LLVM编译执行 ---\n")
        match = res.get('match', False)
        f.write(f"结果: {'✅ 一致' if match else '❌ 不一致'}\n")
    return True, None


def process_directory(test_dir, out_dir, generate_fn, label, meta_parser):
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(os.listdir(test_dir))
    test_files = [f for f in files if f.endswith('.txt')]

    results = []
    for tf in test_files:
        filepath = os.path.join(test_dir, tf)
        name = tf.replace('.txt', '')
        content = read_test_file(filepath)
        if content is None:
            results.append((tf, False, '无法解码'))
            continue

        try:
            if meta_parser == '32':
                a, b = parse_32_meta(content)
                ok, err = generate_fn(name, a, b)
            else:
                a, b, c = parse_42_meta(content)
                ok, err = generate_fn(name, a, b, c)
        except Exception as e:
            ok, err = False, str(e)

        status = 'OK' if ok else 'FAIL'
        err_clean = str(err).split('\n')[0][:120] if err else ''
        results.append((tf, ok, err_clean))

    ok_count = sum(1 for r in results if r[1])
    print(f'  [{label}] {ok_count}/{len(results)} 通过')
    return results


def main():
    all_results = []

    print('3.2 .int/.doc ...')
    r32 = process_directory(TEST32_DIR, OUT32_DIR, generate_32, '3.2', '32')
    all_results.append(('任务 3.2 测试用例', r32))

    print('4.2 .int/.doc ...')
    r42 = process_directory(TEST42_DIR, OUT42_DIR, generate_42, '4.2', '42')
    all_results.append(('任务 4.2 测试用例', r42))

    with open(RESULT_FILE, 'w', encoding='utf-8') as f:
        f.write('=' * 70 + '\n')
        f.write('编译原理课程设计 - 测试结果汇总\n')
        f.write('=' * 70 + '\n\n')
        for section_name, results in all_results:
            ok = sum(1 for r in results if r[1])
            total = len(results)
            f.write(f'--- {section_name} ({ok}/{total} 通过) ---\n')
            for tf, success, err in results:
                mark = '✅' if success else '❌'
                line = f'  {mark} {tf}'
                if not success and err:
                    line += f'  ({err})'
                f.write(line + '\n')
            f.write('\n')
        total_ok = sum(sum(1 for r in res if r[1]) for _, res in all_results)
        total_all = sum(len(res) for _, res in all_results)
        f.write(f'总计: {total_ok}/{total_all} 通过\n')

    print(f'\n结果已写入: {RESULT_FILE}')


if __name__ == '__main__':
    main()
