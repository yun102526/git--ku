# 编译原理课程设计 — 任务 3.2 (中间代码) & 4.2 (四元式→LLVM)

## 项目简介

| 任务 | 功能 |
|------|------|
| **3.2 中间代码** | 源码 → 词法分析 → 语法分析(AST) → 语义分析(符号表) → 生成四元式 → 解释执行 |
| **4.2 四元式→LLVM** | 四元式 → LLVM IR → clang编译执行 → 与解释器对比 |

**关键区别**：任务3.2输入是**C-like源代码**，任务4.2输入是**四元式序列**。

Web 界面可查看整个中间过程：Token序列、AST、符号表、四元式、LLVM IR。

---

## 环境配置

### Python (必须)
```bash
pip install flask
```

### LLVM (任务 4.2 需要)

**Linux (Ubuntu/Debian):**
```bash
sudo apt install llvm clang
```

**Windows:**
1. 下载 LLVM：https://github.com/llvm/llvm-project/releases
   - 选 `LLVM-19.1.0-win64.exe` 或最新版
2. 安装时勾选 "Add LLVM to the system PATH"
3. 重启终端，验证：`clang --version`

**macOS:**
```bash
brew install llvm
```

---

## 快速开始

### 1. 启动 Web 界面
```bash
cd compiler_web
python app.py
```
打开浏览器访问 **http://127.0.0.1:5000**

- 左侧栏列出所有 3.2 和 4.2 测试用例，点击加载
- 3.2：点击「任务 3.2」查看 Token序列/AST/符号表/四元式/输出
- 4.2：点击「任务 4.2」查看 LLVM IR/编译输出/对比结果

### 2. 命令行运行

**任务 3.2 (源码输入)：**
```bash
python -c "
from task32 import process_32
res = process_32('int main(void) { int a=10; write(a); return a; }')
print(res['output'])
print(res['quadruples'])
"
```

**任务 4.2 (四元式输入)：**
```bash
python -c "
from task42 import process_42_from_quads
quads = '''0: (=, 10, _, a)
1: (=, 20, _, b)
2: (+, a, b, t1)
3: (=, t1, _, c)
4: (write, c, _, _)
5: (return, c, _, _)'''
res = process_42_from_quads(quads, inputs=[], func_table_text='main=0')
print('解释器:', res['interp_output'])
print('LLVM:', res['llvm_output'])
print('一致:', res['match'])
"
```

### 3. 手动编译 LLVM IR
```bash
# 先生成 LLVM IR 文件
python -c "
from task42 import process_42_from_quads
quads = open('test_cases_42/test1.txt').read()
# ... (见上方示例)
open('output.ll','w').write(res['llvm_ir'])
"
# 编译
clang -x ir output.ll -o output
# 运行
./output          # Linux/macOS
output.exe        # Windows
```

### 4. 批量生成 .int/.doc
```bash
python generate_all.py
# 结果汇总: test_results.txt
```

---

## 文件结构

```
compiler_web/
├── app.py              ← Flask Web 服务器
├── task32.py           ← 任务 3.2 (词法→语法→语义→四元式→解释器)
├── task42.py           ← 任务 4.2 (四元式→LLVM→编译→对比)
├── generate_all.py     ← 批量生成 .int/.doc
├── test_results.txt    ← 测试通过/失败汇总
├── README.md
├── templates/index.html
├── test_cases_32/      ← 3.2 测试用例 (42个, C-like源码)
├── test_cases_42/      ← 4.2 测试用例 (13个, 四元式格式)
├── test_output_32/     ← 3.2 输出 (.int + .doc)
└── test_output_42/     ← 4.2 输出 (.int + .doc)
```

---

## 四元式格式

```
(运算符, 操作数1, 操作数2, 结果)

(J>=, i, 5, 11)     条件跳转: 如果 i>=5 跳到第11行
(J, _, _, 5)         无条件跳转到第5行
(=, t0, _, n)        赋值: n = t0
(=[], arr, i, t1)    数组读取: t1 = arr[i]
([]=, t2, i, arr)    数组写入: arr[i] = t2
(read, _, _, t0)     读取输入
(write, x, _, _)     输出 x
(+, a, b, t0)        加法
(<, >, <=, >=, ==, !=) 比较
(&&, a, b, t0)       逻辑与
(||, a, b, t0)       逻辑或
(param, x, _, _)     函数参数压栈
(call, func, 2, t3)  调用函数, 2个参数, 结果→t3
(return, r, _, _)    返回 r
```

---

## 测试用例格式

### 3.2 测试文件 (test_cases_32/)
```c
int main(void) {
    int a = 10;
    write(a);
    return a;
}
=== 输入: (无) ===
```

### 4.2 测试文件 (test_cases_42/)
```
0: (=, 10, _, a)
1: (write, a, _, _)
2: (return, a, _, _)
=== 输入: (无) ===
=== 函数表: main=0 ===
```

`函数表` 格式: `funcName=entryQuad,param1,param2`，多个函数用 `;` 分隔。
