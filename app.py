from flask import Flask, render_template, request, jsonify
import os, glob
from task32 import process_32
from task42 import process_42_from_quads, find_llvm_tool

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST32_DIR = os.path.join(BASE_DIR, 'test_cases_32')
TEST42_DIR = os.path.join(BASE_DIR, 'test_cases_42')


def get_test_list(test_dir):
    files = sorted(glob.glob(os.path.join(test_dir, '*.txt')))
    result = []
    for fp in files:
        name = os.path.basename(fp).replace('.txt', '')
        content = ''
        for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030', 'latin-1']:
            try:
                with open(fp, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeError:
                continue
        result.append({'name': name, 'content': content})
    return result


def parse_42_from_content(content):
    """Extract quad text, inputs, func_table from test file content."""
    lines = content.split('\n')
    quad_lines = []
    inputs = []
    func_table = ''
    section = 'title'
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):
            section = 'input'
            parts = s.replace('=== 输入:', '').replace('===', '').strip()
            if parts and parts != '(无)':
                try:
                    inputs = [int(x.strip()) for x in parts.split(',') if x.strip()]
                except ValueError:
                    pass
        elif s.startswith('=== 函数表:'):
            section = 'func'
            func_table = s.replace('=== 函数表:', '').replace('===', '').strip()
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
            func_table += ' ' + s.strip()
    return '\n'.join(quad_lines).strip(), inputs, func_table.strip()


def parse_32_from_content(content):
    lines = content.split('\n')
    src_lines = []
    inputs = []
    in_src = True
    for line in lines:
        s = line.strip()
        if s.startswith('=== 输入:'):
            in_src = False
            parts = s.replace('=== 输入:', '').replace('===', '').strip()
            if parts and parts != '(无)':
                try:
                    inputs = [int(x.strip()) for x in parts.split(',') if x.strip()]
                except ValueError:
                    pass
        elif s.startswith('===') and not in_src:
            continue
        elif s.startswith('==='):
            continue
        elif in_src:
            src_lines.append(line)
    return '\n'.join(src_lines), inputs


@app.route('/', methods=['GET'])
def index():
    tests32 = get_test_list(TEST32_DIR)
    tests42 = get_test_list(TEST42_DIR)
    return render_template('index.html', tests32=tests32, tests42=tests42)


@app.route('/run32', methods=['POST'])
def run_32():
    code = request.form.get('code', '')
    inputs_str = request.form.get('inputs', '')
    inputs = []
    if inputs_str.strip():
        try:
            s = inputs_str.strip().replace(',', ' ')
            inputs = [int(x) for x in s.split() if x]
        except ValueError:
            pass
    res = process_32(code, inputs)
    return jsonify(res)


@app.route('/run42', methods=['POST'])
def run_42():
    code = request.form.get('code', '')
    inputs_str = request.form.get('inputs', '')
    func_table_text = request.form.get('func_table', '')
    
    # Strip === 函数表: prefix if present
    if func_table_text.startswith('=== 函数表:'):
        func_table_text = func_table_text.replace('=== 函数表:', '').replace('===', '').strip()
    
    inputs = []
    if inputs_str.strip():
        try:
            s = inputs_str.strip().replace(',', ' ')
            inputs = [int(x) for x in s.split() if x]
        except ValueError:
            pass
    
    # Extract func_table from === markers in code if not already provided
    clean_lines = []
    for line in code.split('\n'):
        s = line.strip()
        if s.startswith('=== 函数表:') and not func_table_text:
            func_table_text = s.replace('=== 函数表:', '').replace('===', '').strip()
        elif s.startswith('==='):
            continue
        else:
            clean_lines.append(line)
    clean_code = '\n'.join(clean_lines)

    if '(' in clean_code:
        res = process_42_from_quads(clean_code, inputs, func_table_text if func_table_text else None)
    else:
        from task42 import process_42 as p42
        res = p42(clean_code, inputs)
    return jsonify(res)


@app.route('/llvm_status', methods=['GET'])
def llvm_status():
    clang = find_llvm_tool('clang')
    lli = find_llvm_tool('lli')
    return jsonify({
        'clang': clang or '未找到',
        'lli': lli or '未找到',
        'os': os.name,
    })


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
