# 导入Flask框架核心组件：Flask应用对象、模板渲染、请求处理、JSON响应
from flask import Flask, render_template, request, jsonify
# 导入os模块用于文件路径操作，glob模块用于文件通配符匹配
import os, glob
# 从task32模块导入3.2任务处理函数（词法分析、语法分析、四元式生成、解释执行）
from task32 import process_32
# 从task42模块导入4.2任务处理函数（四元式转LLVM IR并编译执行）及LLVM工具查找函数
from task42 import process_42_from_quads, find_llvm_tool

# 创建Flask应用实例，__name__用于定位资源路径
app = Flask(__name__)

# 获取项目根目录的绝对路径，所有其他路径都基于此目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 任务3.2测试用例目录：存放源码级别的测试用例文件（.txt格式）
TEST32_DIR = os.path.join(BASE_DIR, 'test_cases_32')
# 任务4.2测试用例目录：存放四元式级别的测试用例文件（.txt格式）
TEST42_DIR = os.path.join(BASE_DIR, 'test_cases_42')


# 获取指定目录下所有测试用例文件的名称和内容列表
# 参数 test_dir: 测试用例目录路径
# 返回值: 包含每个文件名称和内容的字典列表 [{'name': '文件名', 'content': '文件内容'}, ...]
def get_test_list(test_dir):
    # 使用glob通配符匹配目录下所有.txt文件，并按名称排序
    files = sorted(glob.glob(os.path.join(test_dir, '*.txt')))
    result = []
    for fp in files:
        # 去掉.txt后缀，得到测试用例名称
        name = os.path.basename(fp).replace('.txt', '')
        content = ''
        # 尝试多种编码方式读取文件（UTF-8优先，然后是中文编码，最后是latin-1兜底）
        for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
            try:
                # 以指定编码打开并读取文件内容
                with open(fp, 'r', encoding=enc) as f:
                    content = f.read()
                break  # 读取成功则跳出编码尝试循环
            except UnicodeError:
                continue  # 编码不匹配则尝试下一种
        result.append({'name': name, 'content': content})
    return result


# 从4.2测试文件内容中解析出四元式文本、输入数据和函数表信息
# 测试文件通过 === 标记分隔不同区域：源代码、(可选)输入、(可选)函数表、(可选)预期结果
# 参数 content: 测试文件的原始文本内容
# 返回值: (四元式文本, 输入整数列表, 函数表文本)
def parse_42_from_content(content):
    """Extract quad text, inputs, func_table from test file content."""
    lines = content.split('\n')
    quad_lines = []   # 存储四元式行
    inputs = []       # 存储read()需要的输入值
    func_table = ''   # 存储函数表信息
    section = 'title' # 当前解析区域：title/input/func/skip/quads
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):      # 遇到输入区域标记
            section = 'input'
            # 去除===标记，提取输入数据部分
            parts = s.replace('=== 输入:', '').replace('===', '').strip()
            if parts and parts != '(无)':  # 无输入则跳过
                try:
                    # 按逗号分隔，解析为整数列表
                    inputs = [int(x.strip()) for x in parts.split(',') if x.strip()]
                except ValueError:
                    pass
        elif s.startswith('=== 函数表:'):  # 遇到函数表区域标记
            section = 'func'
            # 提取函数表内容（格式: 函数名=入口行号,参数1,参数2;...）
            func_table = s.replace('=== 函数表:', '').replace('===', '').strip()
        elif s.startswith('=== 预期'):     # 遇到预期结果区域标记，跳过
            section = 'skip'
        elif s.startswith('===') and section == 'title':
            section = 'quads'              # 第一个===标记之后开始是四元式内容
        elif s.startswith('==='):          # 其他===标记跳过
            section = 'skip'
        elif section == 'quads' or section == 'title':
            section = 'quads'              # 进入四元式区域后收集所有行
            quad_lines.append(line)
        elif section == 'func':            # 函数表可能跨多行，追加后续行
            func_table += ' ' + s.strip()
    # 将收集的四元式行用换行符连接并去除首尾空白
    return '\n'.join(quad_lines).strip(), inputs, func_table.strip()


# 从3.2测试文件内容中解析出源代码和输入数据
# 3.2测试文件格式：源代码区域 + 可选的===输入===区域
# 参数 content: 测试文件的原始文本内容
# 返回值: (源代码文本, 输入整数列表)
def parse_32_from_content(content):
    lines = content.split('\n')
    src_lines = []    # 收集源代码行
    inputs = []       # 存储read()需要的输入值
    in_src = True     # 初始处于源代码区域
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):      # 遇到输入区域标记，切换到输入解析模式
            in_src = False
            # 提取输入数据
            parts = s.replace('=== 输入:', '').replace('===', '').strip()
            if parts and parts != '(无)':
                try:
                    inputs = [int(x.strip()) for x in parts.split(',') if x.strip()]
                except ValueError:
                    pass
        elif s.startswith('===') and not in_src:  # 输入区域后的===标记跳过
            continue
        elif s.startswith('==='):          # 其他===标记跳过
            continue
        elif in_src:                       # 收集源代码行（保留原始格式）
            src_lines.append(line)
    return '\n'.join(src_lines), inputs


# 首页路由：显示测试用例列表和主界面
# 处理GET请求，从两个测试目录加载所有测试用例并渲染到模板
@app.route('/', methods=['GET'])
def index():
    # 获取3.2和4.2两个任务的所有测试用例
    tests32 = get_test_list(TEST32_DIR)
    tests42 = get_test_list(TEST42_DIR)
    # 渲染index.html模板，传入两组测试用例数据
    return render_template('index.html', tests32=tests32, tests42=tests42)


# 任务3.2执行路由：接收源代码和输入数据，进行词法/语法/语义分析并返回完整中间结果
# 处理POST请求，返回JSON格式结果（包含Token序列、AST、符号表、四元式、输出等）
@app.route('/run32', methods=['POST'])
def run_32():
    # 从表单获取用户输入的源代码
    code = request.form.get('code', '')
    # 从表单获取用户自定义的输入数据（空格或逗号分隔）
    inputs_str = request.form.get('inputs', '')
    inputs = []
    if inputs_str.strip():
        try:
            # 将逗号替换为空格以便统一解析
            s = inputs_str.strip().replace(',', ' ')
            # 按空格拆分并转为整数列表
            inputs = [int(x) for x in s.split() if x]
        except ValueError:
            pass  # 非数字输入忽略
    # 调用task32模块的核心处理函数，执行完整的编译/解释流程
    res = process_32(code, inputs)
    return jsonify(res)


# 任务4.2执行路由：接收四元式文本或源代码，将其转换为LLVM IR并编译执行
# 支持两种模式：1)直接输入四元式运行  2)从3.2的源代码自动生成四元式再运行
@app.route('/run42', methods=['POST'])
def run_42():
    # 获取表单数据：四元式代码（或源代码）、输入数据、函数表
    code = request.form.get('code', '')
    inputs_str = request.form.get('inputs', '')
    func_table_text = request.form.get('func_table', '')
    
    # Strip === 函数表: prefix if present
    # 如果函数表文本包含===标记前缀，去除该前缀
    if func_table_text.startswith('=== 函数表:'):
        func_table_text = func_table_text.replace('=== 函数表:', '').replace('===', '').strip()
    
    # 解析输入数据（与run_32中处理方式相同）
    inputs = []
    if inputs_str.strip():
        try:
            s = inputs_str.strip().replace(',', ' ')
            inputs = [int(x) for x in s.split() if x]
        except ValueError:
            pass
    
    # Extract func_table from === markers in code if not already provided
    # 清理代码：去除===标记行，同时从标记行中提取函数表信息
    clean_lines = []
    for line in code.split('\n'):
        s = line.strip()
        if s.startswith('=== 函数表:') and not func_table_text:
            # 如果之前没有函数表文本，则从此标记行提取
            func_table_text = s.replace('=== 函数表:', '').replace('===', '').strip()
        elif s.startswith('==='):
            continue  # 跳过所有其他===标记行
        else:
            clean_lines.append(line)  # 保留有效代码行
    clean_code = '\n'.join(clean_lines)

    # 判断输入类型：如果清理后的代码包含括号'('，则视为四元式格式，直接处理
    if '(' in clean_code:
        # 四元式格式输入：直接使用parse_quadruples解析并生成LLVM IR
        res = process_42_from_quads(clean_code, inputs, func_table_text if func_table_text else None)
    else:
        # 源代码格式输入：先通过3.2处理生成四元式，再执行4.2流程
        from task42 import process_42 as p42
        res = p42(clean_code, inputs)
    return jsonify(res)


# LLVM工具链状态检测路由：返回clang和lli的安装路径，供前端显示
@app.route('/llvm_status', methods=['GET'])
def llvm_status():
    # 查找clang编译器的路径
    clang = find_llvm_tool('clang')
    # 查找lli（LLVM解释器）的路径
    lli = find_llvm_tool('lli')
    return jsonify({
        'clang': clang or '未找到',  # 未找到则返回'未找到'
        'lli': lli or '未找到',
        'os': os.name,               # 操作系统标识（nt=Windows, posix=Linux/Mac）
    })


# 程序入口：启动Flask开发服务器
# debug=True启用调试模式和自动重载，host='0.0.0.0'允许局域网访问，port=5000监听端口
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
