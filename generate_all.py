"""批量生成 3.2 和 4.2 的 .int / .doc 文件。
本脚本遍历 test_cases_32 和 test_cases_42 目录中的所有测试用例，
对每个测试用例执行编译/解释流程，将详细结果写入 .int（中间过程）和
.doc（最终结果/对比）文件，并生成汇总测试报告 test_results.txt。
"""
# 导入os模块用于路径操作，sys模块用于修改模块搜索路径
import os, sys
# 将当前脚本所在目录添加到sys.path，确保可以导入同目录下的task32和task42模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 从task32模块导入3.2任务处理函数
from task32 import process_32
# 从task42模块导入4.2任务处理函数（四元式版本和源代码版本）
from task42 import process_42_from_quads, process_42

# 获取项目根目录路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 3.2测试用例输入目录
TEST32_DIR = os.path.join(BASE_DIR, 'test_cases_32')
# 4.2测试用例输入目录
TEST42_DIR = os.path.join(BASE_DIR, 'test_cases_42')
# 3.2输出目录：存放生成的.int和.doc文件
OUT32_DIR = os.path.join(BASE_DIR, 'test_output_32')
# 4.2输出目录：存放生成的.int和.doc文件
OUT42_DIR = os.path.join(BASE_DIR, 'test_output_42')
# 测试结果汇总报告文件路径
RESULT_FILE = os.path.join(BASE_DIR, 'test_results.txt')


# 通用文件读取函数：尝试多种编码方式读取文件内容
# 参数 filepath: 文件完整路径
# 返回值: 文件文本内容，所有编码都无法解码时返回None
def read_test_file(filepath):
    # 按优先级尝试常见编码：UTF-8 > GBK系列中文编码 > latin-1兜底
    for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue  # 当前编码失败，尝试下一种
    return None


# 解析4.2测试文件（与app.py中的parse_42_from_content逻辑相同）
# 从测试文件内容中提取四元式文本、输入数据和函数表文本
# 参数 content: 测试文件原始内容
# 返回值: (四元式文本字符串, 输入整数列表, 函数表文本)
def parse_42_meta(content):
    """Parse 4.2 test file: extract quads, inputs, func_table from === markers."""
    lines = content.split('\n')
    quad_lines = []       # 收集四元式行
    inputs = []           # 存储输入数据
    func_table_text = ''  # 存储函数表
    section = 'title'     # 当前解析状态：title/input/func/quads/skip
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):        # 输入区域标记
            section = 'input'
            parts = s.replace('=== 输入:', '').replace('===', '').strip()
            if parts and parts != '(无)':
                try:
                    ss = parts.replace(',', ' ')
                    inputs = [int(x) for x in ss.split() if x]
                except ValueError:
                    pass
        elif s.startswith('=== 函数表:'):    # 函数表区域标记
            section = 'func'
            func_table_text = s.replace('=== 函数表:', '').replace('===', '').strip()
        elif s.startswith('=== 预期'):       # 预期结果区域，跳过
            section = 'skip'
        elif s.startswith('===') and section == 'title':
            section = 'quads'                 # 第一个===后进入四元式区域
        elif s.startswith('==='):
            section = 'skip'
        elif section == 'quads' or section == 'title':
            section = 'quads'
            quad_lines.append(line)
        elif section == 'func':
            func_table_text += ' ' + s.strip()  # 函数表可能跨行
    return '\n'.join(quad_lines).strip(), inputs, func_table_text.strip()


# 解析3.2测试文件：提取源代码和输入数据
# 参数 content: 测试文件原始内容
# 返回值: (源代码文本, 输入整数列表)
def parse_32_meta(content):
    lines = content.split('\n')
    source_lines = []  # 收集源代码行
    inputs = []        # 存储输入数据
    in_source = True   # 是否处于源代码区域
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):        # 输入区域标记，切换状态
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
        elif in_source:                       # 收集源代码行
            source_lines.append(line)
    return '\n'.join(source_lines), inputs


# 生成3.2任务的输出文件（.int和.doc）
# .int文件：包含源代码、Token序列、AST、符号表（编译前端全流程）
# .doc文件：包含四元式流和解释器执行结果（编译中端和后端）
# 参数 name: 测试用例名称（不含.txt后缀）
# 参数 source_code: 源代码文本
# 参数 inputs: 输入整数列表
# 返回值: (是否成功, 错误信息)
def generate_32(name, source_code, inputs):
    # 调用task32的核心处理函数，进行词法分析→语法分析→语义分析→四元式生成→解释执行
    res = process_32(source_code, inputs)
    # 构造输出文件路径
    int_path = os.path.join(OUT32_DIR, f'{name}.int')
    doc_path = os.path.join(OUT32_DIR, f'{name}.doc')

    if 'error' in res:
        # 处理过程中出现错误，写入错误信息到两个输出文件
        with open(int_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 源文件: {name}.txt ---\n--- 源代码 ---\n{source_code}\n\n--- 错误信息 ---\n{res['error']}\n")
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 错误信息 ---\n{res['error']}\n")
        return False, res['error']

    # 成功处理：写入完整的前端分析结果到.int文件
    with open(int_path, 'w', encoding='utf-8') as f:
        f.write(f"--- 成功加载外部源文件: 测试用例/3.2/{name}.txt ---\n")
        f.write(f"--- [3.2测试运行] 已进入测试执行流程 ---\n")
        f.write(f"测试文件: {name}.txt\n")
        if inputs:
            f.write(f"默认输入: {inputs}\n")
        f.write("\n--- [编译前端] Token序列 (Tokens) ---\n")
        f.write(res['tokens'])              # Token列表（词法分析结果）
        f.write("\n\n--- [编译前端] 抽象语法树 (AST) ---\n")
        f.write(res['ast'])                 # 语法树（语法分析结果）
        f.write("\n\n--- [编译前端] 符号表 (Symbol Table) ---\n")
        f.write(res['symbol_table'])        # 符号表（语义分析结果）
        f.write("\n")

    # 成功处理：写入中后端结果到.doc文件
    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(f"--- [编译中端] 生成的四元式流 (Quadruples) ---\n")
        f.write(res['quadruples'])          # 四元式序列（中间代码）
        f.write(f"\n\n--- [编译后端] 解释器执行过程 ---\n")
        f.write(f"Program output: {res['output']}\n")  # 程序输出
        if 'retval' in res:
            f.write(f"Return value: {res['retval']}\n")  # 返回值
    return True, None


# 生成4.2任务的输出文件（.int和.doc）
# .int文件：包含四元式输入和LLVM IR代码
# .doc文件：包含解释器执行结果、LLVM编译执行结果及两者对比
# 参数 name: 测试用例名称
# 参数 quad_text: 四元式文本
# 参数 inputs: 输入整数列表
# 参数 func_table_text: 函数表文本
# 返回值: (是否成功, 错误信息)
def generate_42(name, quad_text, inputs, func_table_text):
    # 调用task42的四元式处理函数：解析四元式→生成LLVM IR→编译执行→对比结果
    res = process_42_from_quads(quad_text, inputs, func_table_text)
    int_path = os.path.join(OUT42_DIR, f'{name}.int')
    doc_path = os.path.join(OUT42_DIR, f'{name}.doc')

    if 'error' in res:
        # 处理错误：写入错误信息
        with open(int_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 源文件: {name}.txt ---\n--- 四元式 ---\n{quad_text}\n\n--- 错误信息 ---\n{res['error']}\n")
        with open(doc_path, 'w', encoding='utf-8') as f:
            f.write(f"--- 错误信息 ---\n{res['error']}\n--- 对比结果 ---\n因错误无法对比\n")
        return False, res['error']

    # 成功处理：写入LLVM IR到.int文件
    with open(int_path, 'w', encoding='utf-8') as f:
        f.write(f"--- 成功加载: 测试用例/4.2/{name}.txt ---\n")
        f.write(f"--- [4.2] 四元式 → LLVM IR → 编译执行 ---\n")
        f.write(f"测试文件: {name}.txt\n")
        if inputs:
            f.write(f"输入: {inputs}\n")
        f.write("\n--- [输入] 四元式流 ---\n")
        f.write(res['quadruples'])
        f.write("\n\n--- [4.2 输出] LLVM IR 代码 ---\n")
        f.write(res['llvm_ir'])             # 生成的LLVM IR代码
        f.write("\n")

    # 成功处理：写入解释器结果、LLVM结果及对比到.doc文件
    with open(doc_path, 'w', encoding='utf-8') as f:
        f.write(f"--- [解释器] 四元式解释器执行结果 ---\n")
        f.write(f"输出: {res['interp_output']}\n返回值: {res['interp_retval']}\n\n")
        f.write(f"--- [4.2 LLVM] LLVM编译执行结果 ---\n")
        f.write(f"编译方式: {res.get('llvm_method', 'unknown')}\n")
        f.write(f"输出: {res['llvm_output']}\n返回值: {res['llvm_retcode']}\n\n")
        f.write(f"--- [对比] 四元式解释器 vs LLVM编译执行 ---\n")
        match = res.get('match', False)
        f.write(f"结果: {'✅ 一致' if match else '❌ 不一致'}\n")  # 对比结果
    return True, None


# 批量处理指定测试目录中的所有测试文件
# 对每个.txt测试文件调用生成函数，收集处理结果
# 参数 test_dir: 测试用例输入目录
# 参数 out_dir: 输出文件目录
# 参数 generate_fn: 生成函数（generate_32或generate_42）
# 参数 label: 任务标签（如'3.2'或'4.2'），用于控制台输出
# 参数 meta_parser: 元数据解析器类型（'32'或'42'）
# 返回值: 处理结果列表 [(文件名, 是否成功, 错误信息), ...]
def process_directory(test_dir, out_dir, generate_fn, label, meta_parser):
    # 确保输出目录存在
    os.makedirs(out_dir, exist_ok=True)
    # 获取目录下所有文件并按名称排序
    files = sorted(os.listdir(test_dir))
    # 筛选出.txt文件
    test_files = [f for f in files if f.endswith('.txt')]

    results = []
    for tf in test_files:
        # 构造完整文件路径
        filepath = os.path.join(test_dir, tf)
        # 去掉.txt后缀作为测试名
        name = tf.replace('.txt', '')
        # 读取文件内容（自动尝试多种编码）
        content = read_test_file(filepath)
        if content is None:
            results.append((tf, False, '无法解码'))
            continue

        try:
            # 根据任务类型调用不同的解析器和生成函数
            if meta_parser == '32':
                # 3.2任务：解析源代码和输入 → 调用generate_32
                a, b = parse_32_meta(content)
                ok, err = generate_fn(name, a, b)
            else:
                # 4.2任务：解析四元式、输入和函数表 → 调用generate_42
                a, b, c = parse_42_meta(content)
                ok, err = generate_fn(name, a, b, c)
        except Exception as e:
            # 捕获所有异常，记录为失败
            ok, err = False, str(e)

        # 格式化结果状态和错误摘要
        status = 'OK' if ok else 'FAIL'
        err_clean = str(err).split('\n')[0][:120] if err else ''  # 只取第一行前120字符
        results.append((tf, ok, err_clean))

    # 输出统计信息
    ok_count = sum(1 for r in results if r[1])
    print(f'  [{label}] {ok_count}/{len(results)} 通过')
    return results


# 主函数：遍历所有3.2和4.2测试用例，生成输出文件并汇总测试报告
def main():
    all_results = []

    # 处理3.2任务测试用例
    print('3.2 .int/.doc ...')
    r32 = process_directory(TEST32_DIR, OUT32_DIR, generate_32, '3.2', '32')
    all_results.append(('任务 3.2 测试用例', r32))

    # 处理4.2任务测试用例
    print('4.2 .int/.doc ...')
    r42 = process_directory(TEST42_DIR, OUT42_DIR, generate_42, '4.2', '42')
    all_results.append(('任务 4.2 测试用例', r42))

    # 写入汇总测试报告到test_results.txt
    with open(RESULT_FILE, 'w', encoding='utf-8') as f:
        f.write('=' * 70 + '\n')
        f.write('编译原理课程设计 - 测试结果汇总\n')
        f.write('=' * 70 + '\n\n')
        for section_name, results in all_results:
            ok = sum(1 for r in results if r[1])    # 统计通过数量
            total = len(results)                     # 总数
            f.write(f'--- {section_name} ({ok}/{total} 通过) ---\n')
            for tf, success, err in results:
                mark = '✅' if success else '❌'     # 通过/失败标记
                line = f'  {mark} {tf}'
                if not success and err:
                    line += f'  ({err})'            # 附加错误信息
                f.write(line + '\n')
            f.write('\n')
        # 计算总计通过率
        total_ok = sum(sum(1 for r in res if r[1]) for _, res in all_results)
        total_all = sum(len(res) for _, res in all_results)
        f.write(f'总计: {total_ok}/{total_all} 通过\n')

    print(f'\n结果已写入: {RESULT_FILE}')


if __name__ == '__main__':
    main()
