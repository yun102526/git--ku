# 导入正则表达式模块，用于词法分析的模式匹配
import re

# 条件取反映射：用于将条件跳转指令反转
# 例如 '<' 取反为 '>='，用于生成条件为假时的跳转目标
INV_COND = {'<': '>=', '>': '<=', '<=': '>', '>=': '<', '==': '!=', '!=': '=='}


# ========== Token类：词法单元 ==========
# 表示词法分析器识别出的一个词法单元
# type:   Token类型（KEYWORD, ID, NUM, OP, PUNCT, STRING等）
# value:  实际的字符串值（如"int", "x", "42", "+", "("等）
# line:   该Token在源代码中的行号（用于错误定位）
class Token:
    def __init__(self, type, value, line):
        self.type = type
        self.value = value
        self.line = line
    # 字符串表示形式，便于调试输出
    def __repr__(self):
        return f"<{self.type}, {self.value}, line {self.line}>"


# ========== Lexer类：词法分析器（分词） ==========
# 将源代码文本分解为Token序列，支持关键字、标识符、运算符等多种类型
# 使用正则表达式匹配模式，按优先级顺序尝试匹配
class Lexer:
    def __init__(self, text):
        self.text = text       # 待分析的源代码文本
        self.pos = 0           # 当前扫描位置（字符索引）
        self.line = 1          # 当前行号
        self.tokens = []       # 生成的Token列表

    def tokenize(self):
        # 定义词法规则列表：每项为(类型名, 正则模式)
        # 规则按优先级排列，先匹配的优先生效
        rules = [
            ('COMMENT', r'//[^\n]*'),                    # 单行注释：//开头到行尾
            ('WHITESPACE', r'[ \t\r]+'),                  # 空白字符：空格、制表符、回车
            ('NEWLINE', r'\n'),                           # 换行符
            ('KEYWORD', r'\b(int|if|else|while|return|void|main|for|do|continue|break|read|write)\b'),  # C语言关键字
            ('OP', r'==|!=|<=|>=|\|\||&&|<|>|\+\+|\-\-|\+|-|\*|/|%|='),  # 运算符（双字符优先于单字符）
            ('PUNCT', r'[(){}\[\];,\uff1b]'),            # 标点符号（含全角分号\uff1b）
            ('STRING', r"'[^']*'"),                       # 单引号字符串
            ('STRING_DQ', r'"[^"]*"'),                    # 双引号字符串
            ('NUM', r'\d+'),                              # 数字（整数）
            ('ID', r'[a-zA-Z_]\w*'),                       # 标识符（字母/下划线开头）
        ]
        # 循环扫描直到文本结束
        while self.pos < len(self.text):
            matched = False
            # 按优先级尝试每条规则
            for name, pattern in rules:
                # 在当前位置尝试正则匹配
                m = re.compile(pattern).match(self.text, self.pos)
                if m:
                    val = m.group(0)    # 获取匹配到的字符串
                    if name == 'NEWLINE':
                        self.line += 1  # 换行符：行号+1，不生成Token
                    elif name not in ('WHITESPACE', 'COMMENT'):
                        # 非空白和注释：需要生成Token
                        ttype = 'ID'
                        if name == 'KEYWORD':
                            ttype = 'KEYWORD'
                        elif name == 'OP':
                            ttype = 'OP'
                        elif name == 'PUNCT':
                            ttype = 'PUNCT'
                            if val == '\uff1b':  # 全角分号转为半角
                                val = ';'
                        elif name == 'NUM':
                            ttype = 'NUM'
                        elif name in ('CHAR', 'STRING', 'STRING_DQ'):
                            ttype = 'STRING'
                        # 创建Token并加入列表
                        self.tokens.append(Token(ttype, val, self.line))
                    self.pos = m.end(0)   # 移动扫描位置
                    matched = True
                    break                 # 匹配成功，跳出规则循环
            if not matched:
                # 没有任何规则匹配：词法错误
                snippet = self.text[self.pos:self.pos+20]
                raise Exception(f"词法错误 第{self.line}行: 无法识别 '{snippet}'")
        return self.tokens


# ========== Parser类：语法分析器（递归下降） ==========
# 使用递归下降方法将Token序列解析为抽象语法树（AST）
# 支持C语言子集：变量声明、赋值、表达式、控制流（if/while/for/do-while）、函数定义等
# AST节点以字典形式表示，每个节点包含'type'字段标识类型
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens  # Token列表
        self.pos = 0          # 当前解析位置

    # 获取当前Token，若已到达末尾则返回None
    def cur(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    # 获取当前Token的行号，用于错误定位
    def _line(self):
        t = self.cur()
        return t.line if t else 0

    # 消费当前Token：验证类型和/或值匹配，然后移动到下一个Token
    # 参数 typ: 期望的Token类型（None表示不验证类型）
    # 参数 val: 期望的Token值（None表示不验证值）
    # 返回值: 被消费的Token对象
    # 不匹配时抛出语法错误异常
    def eat(self, typ=None, val=None):
        t = self.cur()
        if t:
            # 检查类型：如果typ为'ID'，也接受KEYWORD类型（因为KEYWORD也可能是标识符名）
            type_ok = typ is None or t.type == typ or (typ == 'ID' and t.type == 'KEYWORD')
            val_ok = val is None or t.value == val
            if type_ok and val_ok:
                self.pos += 1
                return t
        exp = val if val else (typ or 'token')
        raise Exception(f"语法错误 第{t.line if t else 'EOF'}行: 期望{exp}, 得到{t}")

    # 程序入口：解析整个程序
    # 语法: Program → ExternalDecl*
    # 返回值: {'type': 'Program', 'body': [声明/函数/语句...]}
    def parse(self):
        stmts = []
        while self.cur():
            s = self.parse_external_decl()  # 解析外部声明（函数或语句）
            if s:
                stmts.append(s)
        return {'type': 'Program', 'body': stmts}

    # 解析外部声明：函数定义、函数声明或顶层语句
    def parse_external_decl(self):
        t = self.cur()
        if not t:
            return None
        # 检查是否为函数定义/声明：返回类型 + 名称 + '('
        if t.type == 'KEYWORD' and t.value in ('int', 'void'):
            if self.pos + 2 < len(self.tokens) and self.tokens[self.pos + 2].value == '(':
                return self.parse_func_def()
        # 无返回类型但有函数调用样式：ID + '('，当作无类型函数声明
        if t.type in ('ID', 'KEYWORD') and self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].value == '(':
            return self.parse_func_def_no_type()
        # 否则是普通语句或声明
        return self.parse_statement()

    # 解析带返回类型的函数定义/声明
    # 语法: RetType ID '(' Params ')' (Block | ';')
    # 如果有函数体{...}则为函数定义，仅有';'则为函数声明
    def parse_func_def(self):
        start_line = self._line()
        ret_type = self.eat('KEYWORD').value    # 返回值类型（int/void）
        name = self.eat('ID').value             # 函数名
        self.eat('PUNCT', '(')                  # 左括号
        params = []                             # 参数列表
        if self.cur() and self.cur().value != ')':
            while True:
                if self.cur().value == 'void':  # void参数（无参数）
                    self.eat('KEYWORD', 'void')
                    break
                pline = self._line()
                pt = self.eat('KEYWORD').value  # 参数类型
                # 如果参数名后面紧跟','或')'，说明参数名被省略，自动命名
                if self.cur() and self.cur().value in (',', ')'):
                    pn = f'_p{len(params)}'     # 自动生成参数名_p0, _p1, ...
                else:
                    pn = self.eat('ID').value   # 获取参数名
                params.append({'type': pt, 'name': pn, 'line': pline})
                if self.cur() and self.cur().value == ',':
                    self.eat('PUNCT', ',')      # 多个参数继续
                else:
                    break
        self.eat('PUNCT', ')')                  # 右括号
        if self.cur() and self.cur().value == ';':
            self.eat('PUNCT', ';')              # 函数声明（只有原型，没有函数体）
            return {'type': 'FuncDecl', 'name': name, 'ret': ret_type, 'params': params, 'line': start_line}
        body = self.parse_block()               # 解析函数体
        return {'type': 'FuncDef', 'name': name, 'ret': ret_type, 'params': params, 'body': body, 'line': start_line}

    # 解析无返回类型的函数定义/声明（如main函数简化形式）
    # 自动推断返回类型为'int'
    def parse_func_def_no_type(self):
        start_line = self._line()
        name = self.eat('ID').value             # 函数名
        self.eat('PUNCT', '(')                  # 左括号
        params = []
        if self.cur() and self.cur().value != ')':
            while True:
                if self.cur().value == 'void':
                    self.eat('KEYWORD', 'void')
                    break
                pline = self._line()
                pt = self.eat('KEYWORD').value
                if self.cur() and self.cur().value in (',', ')'):
                    pn = f'_p{len(params)}'
                else:
                    pn = self.eat('ID').value
                params.append({'type': pt, 'name': pn, 'line': pline})
                if self.cur() and self.cur().value == ',':
                    self.eat('PUNCT', ',')
                else:
                    break
        self.eat('PUNCT', ')')
        if self.cur() and self.cur().value == ';':
            self.eat('PUNCT', ';')              # 函数声明
            return {'type': 'FuncDecl', 'name': name, 'ret': 'int', 'params': params, 'line': start_line}
        body = self.parse_block()
        return {'type': 'FuncDef', 'name': name, 'ret': 'int', 'params': params, 'body': body, 'line': start_line}

    # 解析代码块：花括号包围的语句序列
    def parse_block(self):
        stmts = []
        self.eat('PUNCT', '{')
        while self.cur() and self.cur().value != '}':
            s = self.parse_statement()
            if s:
                stmts.append(s)
        self.eat('PUNCT', '}')
        return {'type': 'Block', 'body': stmts}

    # 解析语句：根据当前Token分发到对应的语句解析函数
    def parse_statement(self):
        t = self.cur()
        if not t:
            return None
        if t.value == 'int':        return self.parse_var_decl()     # 变量声明
        if t.value == '{':          return self.parse_block()        # 代码块
        if t.value == 'if':         return self.parse_if()           # if语句
        if t.value == 'while':      return self.parse_while()        # while循环
        if t.value == 'for':        return self.parse_for()          # for循环
        if t.value == 'do':         return self.parse_do_while()     # do-while循环
        if t.value == 'return':     return self.parse_return()       # return语句
        if t.value == 'break':                                      # break语句
            line = t.line
            self.eat('KEYWORD', 'break')
            self.eat('PUNCT', ';')
            return {'type': 'Break', 'line': line}
        if t.value == 'continue':                                   # continue语句
            line = t.line
            self.eat('KEYWORD', 'continue')
            self.eat('PUNCT', ';')
            return {'type': 'Continue', 'line': line}
        if t.value == 'write':      return self.parse_write()       # write语句
        return self.parse_expr_stmt()                                # 表达式语句（默认）

    # 解析变量声明：int a, b, c[10] = 5, ...;
    # 支持普通变量、数组及初始化表达式
    def parse_var_decl(self):
        start_line = self._line()
        self.eat('KEYWORD', 'int')            # int关键字
        decls = []
        while True:
            name_line = self._line()
            name = self.eat('ID').value        # 变量名
            arr_size = None
            if self.cur() and self.cur().value == '[':
                self.eat('PUNCT', '[')
                arr_size = int(self.eat('NUM').value)  # 数组大小常量
                self.eat('PUNCT', ']')
            init = None
            if self.cur() and self.cur().value == '=':
                self.eat('OP', '=')
                init = self.parse_expr()       # 初始化表达式
            decls.append({'name': name, 'arr_size': arr_size, 'init': init, 'line': name_line})
            if self.cur() and self.cur().value == ',':
                self.eat('PUNCT', ',')         # 逗号分隔多个声明
            else:
                break
        self.eat('PUNCT', ';')
        return {'type': 'VarDecl', 'decls': decls, 'line': start_line}

    # 解析if语句：if (条件) 语句 [else 语句]
    def parse_if(self):
        start_line = self._line()
        self.eat('KEYWORD', 'if')
        self.eat('PUNCT', '(')
        cond = self.parse_expr()               # 条件表达式
        self.eat('PUNCT', ')')
        tb = self.parse_block_or_stmt()        # true分支
        fb = None
        if self.cur() and self.cur().value == 'else':
            self.eat('KEYWORD', 'else')
            fb = self.parse_block_or_stmt()    # false分支（可选）
        return {'type': 'If', 'cond': cond, 'true': tb, 'false': fb, 'line': start_line}

    # 解析while循环：while (条件) 语句
    def parse_while(self):
        start_line = self._line()
        self.eat('KEYWORD', 'while')
        self.eat('PUNCT', '(')
        cond = self.parse_expr()
        self.eat('PUNCT', ')')
        body = self.parse_block_or_stmt()
        return {'type': 'While', 'cond': cond, 'body': body, 'line': start_line}

    # 解析for循环：for (初始化; 条件; 步进) 语句
    def parse_for(self):
        start_line = self._line()
        self.eat('KEYWORD', 'for')
        self.eat('PUNCT', '(')
        # 初始化部分（可选，如i=0）
        init = self.parse_expr() if self.cur() and self.cur().value != ';' else None
        self.eat('PUNCT', ';')
        # 条件部分（可选，如i<10）
        cond = self.parse_expr() if self.cur() and self.cur().value != ';' else None
        self.eat('PUNCT', ';')
        # 步进部分（可选，如i++）
        step = self.parse_expr() if self.cur() and self.cur().value != ')' else None
        self.eat('PUNCT', ')')
        body = self.parse_block_or_stmt()
        return {'type': 'For', 'init': init, 'cond': cond, 'step': step, 'body': body, 'line': start_line}

    # 解析do-while循环：do 语句 while (条件);
    def parse_do_while(self):
        start_line = self._line()
        self.eat('KEYWORD', 'do')
        body = self.parse_block_or_stmt()
        self.eat('KEYWORD', 'while')
        self.eat('PUNCT', '(')
        cond = self.parse_expr()
        self.eat('PUNCT', ')')
        self.eat('PUNCT', ';')
        return {'type': 'DoWhile', 'cond': cond, 'body': body, 'line': start_line}

    # 解析return语句：return [表达式];
    def parse_return(self):
        start_line = self._line()
        self.eat('KEYWORD', 'return')
        expr = self.parse_expr() if self.cur() and self.cur().value != ';' else None  # 返回值可选
        self.eat('PUNCT', ';')
        return {'type': 'Return', 'expr': expr, 'line': start_line}

    # 解析write语句：write(表达式列表);
    # 语法: write '(' expr (',' expr)* ')' ';'
    def parse_write(self):
        start_line = self._line()
        self.eat('KEYWORD', 'write')
        self.eat('PUNCT', '(')
        args = []
        while self.cur() and self.cur().value != ')':
            args.append(self.parse_expr())     # 解析每个参数
            if self.cur() and self.cur().value == ',':
                self.eat('PUNCT', ',')         # 逗号分隔多个参数
        self.eat('PUNCT', ')')
        self.eat('PUNCT', ';')
        return {'type': 'Write', 'args': args, 'line': start_line}

    # 解析表达式语句：表达式后跟分号（如赋值语句、函数调用等）
    def parse_expr_stmt(self):
        start_line = self._line()
        expr = self.parse_expr()
        self.eat('PUNCT', ';')
        return {'type': 'ExprStmt', 'expr': expr, 'line': start_line}

    # 解析代码块或单条语句（用于if/while等分支）
    # 如果以'{'开头则解析为代码块，否则解析为单条语句并包装为Block
    def parse_block_or_stmt(self):
        if self.cur() and self.cur().value == '{':
            return self.parse_block()
        else:
            return {'type': 'Block', 'body': [self.parse_statement()]}

    # 表达式解析入口：从最低优先级开始递归下降
    def parse_expr(self):
        return self.parse_assign()

    # ========== 表达式解析链（运算符优先级递归下降） ==========
    # 优先级从低到高：赋值 < 逻辑或 || < 逻辑与 && < 相等 == != < 关系 < > <= >= < 加减 + - < 乘除 * / % < 一元 - < 后缀 [] () ++ --
    # 每个函数处理一个优先级，左递归消除：先解析高优先级左操作数，然后循环处理当前优先级的运算符

    # 解析赋值表达式：target = expr
    # 赋值是右结合的，所以递归调用parse_assign
    def parse_assign(self):
        node = self.parse_or()                # 先解析左操作数
        if self.cur() and self.cur().value == '=':
            op_line = self._line()
            self.eat('OP', '=')
            right = self.parse_assign()       # 递归解析右操作数（右结合）
            return {'type': 'Assign', 'target': node, 'expr': right, 'line': op_line}
        return node

    # 解析逻辑或表达式：expr || expr
    def parse_or(self):
        node = self.parse_and()               # 左操作数
        while self.cur() and self.cur().value == '||':
            op = self.eat('OP')
            right = self.parse_and()          # 右操作数
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    # 解析逻辑与表达式：expr && expr
    def parse_and(self):
        node = self.parse_eq()
        while self.cur() and self.cur().value == '&&':
            op = self.eat('OP')
            right = self.parse_eq()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    # 解析相等性表达式：expr == expr 或 expr != expr
    def parse_eq(self):
        node = self.parse_rel()
        while self.cur() and self.cur().value in ('==', '!='):
            op = self.eat('OP')
            right = self.parse_rel()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    # 解析关系表达式：expr < expr 或 expr > expr 等
    def parse_rel(self):
        node = self.parse_add()
        while self.cur() and self.cur().value in ('<', '>', '<=', '>='):
            op = self.eat('OP')
            right = self.parse_add()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    # 解析加减表达式：expr + expr 或 expr - expr
    def parse_add(self):
        node = self.parse_mul()
        while self.cur() and self.cur().value in ('+', '-'):
            op = self.eat('OP')
            right = self.parse_mul()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    # 解析乘除模表达式：expr * expr 或 expr / expr 等
    def parse_mul(self):
        node = self.parse_unary()
        while self.cur() and self.cur().value in ('*', '/', '%'):
            op = self.eat('OP')
            right = self.parse_unary()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    # 解析一元运算符：-expr（取负）
    def parse_unary(self):
        t = self.cur()
        if t and t.value == '-':
            line = t.line
            self.eat('OP', '-')
            operand = self.parse_unary()       # 递归（支持多重取负如 --x）
            return {'type': 'UnaryOp', 'op': '-', 'operand': operand, 'line': line}
        return self.parse_postfix()

    # 解析后缀表达式：支持数组访问[]、函数调用()、后置++/--
    # 循环处理因为后缀操作符可以连续（如a[i](x)++）
    def parse_postfix(self):
        node = self.parse_primary()            # 先解析主表达式
        while True:
            t = self.cur()
            if t and t.value == '[':
                # 数组访问：arr[index]
                self.eat('PUNCT', '[')
                idx = self.parse_expr()
                self.eat('PUNCT', ']')
                node = {'type': 'ArrayAccess', 'array': node, 'index': idx, 'line': t.line}
            elif t and t.value == '(':
                # 函数调用：func(arg1, arg2, ...)
                self.eat('PUNCT', '(')
                args = []
                while self.cur() and self.cur().value != ')':
                    args.append(self.parse_expr())
                    if self.cur() and self.cur().value == ',':
                        self.eat('PUNCT', ',')
                self.eat('PUNCT', ')')
                node = {'type': 'Call', 'func': node, 'args': args, 'line': t.line}
            elif t and t.value in ('++', '--'):
                # 后置自增/自减：x++ 或 x--
                op = self.eat('OP').value
                node = {'type': 'PostOp', 'op': op, 'operand': node, 'line': t.line}
            else:
                break  # 没有更多后缀操作符
        return node

    # 解析主表达式（原子表达式）：数字、字符串、标识符、括号表达式
    def parse_primary(self):
        t = self.cur()
        if t.type == 'NUM':
            self.eat('NUM')
            return {'type': 'Num', 'value': int(t.value), 'line': t.line}  # 数值字面量
        elif t.type == 'STRING':
            self.eat('STRING')
            val_str = t.value
            quote_char = val_str[0]            # 获取引号类型（单引号或双引号）
            inner = val_str[1:-1]             # 提取引号内部的内容
            if quote_char == '"':
                # 双引号字符串：计算所有字符的ASCII码之和 mod 65536
                val = sum(ord(c) for c in inner) % 65536
                return {'type': 'Num', 'value': val, 'line': t.line}
            if len(inner) == 1:
                val = ord(inner)               # 单个字符直接取ASCII码
            elif inner.startswith('\\') and len(inner) == 2:
                # 转义字符：\n, \t, \0, \\, \'
                ch_map = {'n': '\n', 't': '\t', '0': '\0', '\\': '\\', '\'': '\''}
                ch = ch_map.get(inner[1], inner[1])
                val = ord(ch)
            else:
                val = sum(ord(c) for c in inner) % 256  # 多字符求和 mod 256
            return {'type': 'CharVal', 'value': val, 'line': t.line}
        elif t.type in ('ID', 'KEYWORD'):
            self.eat(t.type)
            return {'type': 'Var', 'name': t.value, 'line': t.line}  # 标识符（变量名）
        elif t.value == '(':
            # 括号表达式：(expr)
            self.eat('PUNCT', '(')
            node = self.parse_expr()
            self.eat('PUNCT', ')')
            return node  # 直接返回内部表达式节点
        raise Exception(f"语法错误 第{t.line}行: 意外的token {t}")


# ========== SymbolEntry类：符号表条目 ==========
# 表示符号表中的一个条目，记录变量/函数/数组等符号的属性
# name:  符号名称
# kind:  符号种类（'var'变量, 'array'数组, 'function'函数, 'param'参数）
# type:  数据类型（如'int', 'void'）
# extra: 附加信息（数组大小、函数参数列表等）
class SymbolEntry:
    def __init__(self, name, kind, typ, extra=None):
        self.name = name
        self.kind = kind
        self.type = typ
        self.extra = extra   # {'arr_size': N} 或 {'params': [p1, p2, ...]}

    def __repr__(self):
        e = ""
        if self.extra:
            if 'arr_size' in self.extra:
                e = f", size={self.extra['arr_size']}"
            elif 'params' in self.extra:
                e = f", params={self.extra['params']}"
        return f"({self.name}, {self.kind}, {self.type}{e})"


# ========== QuadGenerator类：四元式/中间代码生成器 ==========
# 遍历AST生成三地址码形式的四元式序列（op, arg1, arg2, result）
# 采用语法制导翻译（SDT），每个AST节点类型对应一个gen方法
class QuadGenerator:
    def __init__(self):
        self.quads = []          # 四元式列表，每个元素为(op, a1, a2, res)元组
        self.temp_cnt = 0        # 临时变量计数器（t1, t2, t3...）
        self.symbols = {}        # 符号表：{符号名: SymbolEntry对象}
        self.next_quad = 0       # 下一条四元式的索引（用于回填时定位）
        self.func_table = {}     # 函数表：{函数名: {'params': [...], 'entry': 入口行号}}
        self.break_stack = []    # break语句回填栈：每层循环一个列表
        self.continue_stack = [] # continue语句回填栈：每层循环一个列表
        self.current_func = None # 当前正在编译的函数名

    # 创建新的临时变量（t1, t2, ...）
    def new_temp(self):
        self.temp_cnt += 1
        return f"t{self.temp_cnt}"

    # 发射一条四元式到四元式列表
    # 参数 op: 操作符（+, -, *, =, J, J<, call, return等）
    # 参数 a1: 第一个操作数
    # 参数 a2: 第二个操作数
    # 参数 res: 结果/目标
    # 返回值: 该四元式在列表中的索引（用于回填）
    def emit(self, op, a1, a2, res):
        q = (op, str(a1), str(a2), str(res))
        self.quads.append(q)
        idx = self.next_quad
        self.next_quad += 1
        return idx

    # 回填：将索引idx处的四元式的目标位置修改为target
    # 用于实现控制流语句的目标地址回填
    def backpatch(self, idx, target):
        if idx is None:
            return
        q = self.quads[idx]
        self.quads[idx] = (q[0], q[1], q[2], str(target))

    # 生成条件跳转代码
    # 如果条件表达式是简单的关系运算（a <op> b），生成反转条件跳转指令J<inv>到true_target
    # 例如，条件为 a < b 时生成 J>= a, b, true_target（条件为假时跳转）
    # 如果条件为复杂表达式，先计算表达式结果，然后判断是否等于0来跳转
    # 参数 cond: 条件AST节点
    # 参数 true_target: true分支的目标行号
    # 返回值: 应跳转位置的索引（用于后续回填）
    def gen_cond_jump(self, cond, true_target):
        """Generate code for condition, return index of jump-to-false quad.
        If cond is simple relational (a <op> b), emit inverted J<inv> to skip=true_target.
        If cond is complex, emit J== cond_result 0, true_target (skip when false).
        """
        if cond['type'] == 'BinOp' and cond['op'] in INV_COND:
            left = self.gen(cond['left'])
            right = self.gen(cond['right'])
            inv_op = INV_COND[cond['op']]         # 取反操作符（如'<'取反为'>='）
            return self.emit(f'J{inv_op}', left, right, str(true_target))
        else:
            cr = self.gen(cond)
            return self.emit('J==', cr, '0', str(true_target))

    # 核心生成方法：遍历AST节点生成四元式
    # 采用语法制导翻译，每个AST节点类型对应一个处理分支
    # 返回值: 该节点计算结果的临时变量名或None
    def gen(self, node):
        if node is None:
            return None
        t = node['type']

        # Program根节点：遍历所有顶层语句/函数
        if t == 'Program':
            for s in node['body']:
                self.gen(s)

        # 代码块：遍历块内所有语句
        elif t == 'Block':
            for s in node['body']:
                self.gen(s)

        # 函数声明：注册函数到符号表和函数表，不生成执行代码
        elif t == 'FuncDecl':
            self.symbols[node['name']] = SymbolEntry(node['name'], 'function', node['ret'],
                                                       {'params': [p['name'] for p in node['params']]})
            self.func_table[node['name']] = {'params': [p['name'] for p in node['params']], 'entry': None}

        # 函数定义：注册函数，注册参数，生成函数体四元式
        elif t == 'FuncDef':
            self.current_func = node['name']
            # 将函数参数注册到符号表
            for p in node['params']:
                self.symbols[p['name']] = SymbolEntry(p['name'], 'param', 'int')
            params_list = [p['name'] for p in node['params']]
            self.symbols[node['name']] = SymbolEntry(node['name'], 'function', node['ret'],
                                                       {'params': params_list})
            # 记录函数入口行号
            self.func_table[node['name']] = {'params': params_list, 'entry': self.next_quad}
            prev_count = len(self.quads)
            self.gen(node['body'])             # 生成函数体代码
            # 如果函数末尾没有return语句，添加隐式return 0
            if len(self.quads) == prev_count or self.quads[-1][0] != 'return':
                self.emit('return', '0', '_', '_')

        # 变量声明：变量/数组声明及可选的初始化
        elif t == 'VarDecl':
            for d in node['decls']:
                if d['arr_size'] is not None:
                    # 数组声明
                    self.symbols[d['name']] = SymbolEntry(d['name'], 'array', 'int',
                                                           {'arr_size': d['arr_size']})
                else:
                    # 普通变量声明
                    self.symbols[d['name']] = SymbolEntry(d['name'], 'var', 'int')
                if d['init'] is not None:
                    # 有初始化表达式：计算初始值并赋值给变量
                    r = self.gen(d['init'])
                    self.emit('=', r, '_', d['name'])

        # 赋值语句：将表达式结果赋值给变量或数组元素
        elif t == 'Assign':
            val = self.gen(node['expr'])        # 计算右值
            target = node['target']
            if target['type'] == 'Var':
                self.emit('=', val, '_', target['name'])  # 变量赋值
            elif target['type'] == 'ArrayAccess':
                arr_name = target['array']['name']
                idx = self.gen(target['index'])
                self.emit('[]=', val, idx, arr_name)      # 数组元素赋值
            return val

        # 表达式语句（表达式后加分号）
        elif t == 'ExprStmt':
            return self.gen(node['expr'])

        # 二元运算：left op right → tmp
        elif t == 'BinOp':
            left = self.gen(node['left'])
            right = self.gen(node['right'])
            tmp = self.new_temp()
            self.emit(node['op'], left, right, tmp)
            return tmp

        # 后缀自增/自减：x++ 或 x--
        elif t == 'PostOp':
            op = node['op']
            operand = node['operand']
            if operand['type'] == 'Var':
                op_char = '+' if op == '++' else '-'
                tmp = self.new_temp()
                self.emit(op_char, operand['name'], '1', tmp)  # var + 1
                self.emit('=', tmp, '_', operand['name'])      # 赋值回var
                return tmp
            return self.gen(operand)

        # 一元取负：-x → 0 - x
        elif t == 'UnaryOp':
            operand = self.gen(node['operand'])
            if node['op'] == '-':
                tmp = self.new_temp()
                self.emit('-', '0', operand, tmp)   # 0 - operand
                return tmp

        # 数值字面量：返回字符串形式的数值
        elif t == 'Num':
            return str(node['value'])

        # 字符字面量：返回其数值（ASCII码）
        elif t == 'CharVal':
            return str(node['value'])

        # 变量引用：返回变量名
        elif t == 'Var':
            return node['name']

        # 数组访问：arr[i] → 取数组arr的第i个元素
        elif t == 'ArrayAccess':
            arr_name = node['array']['name']
            idx = self.gen(node['index'])
            tmp = self.new_temp()
            self.emit('=[]', arr_name, idx, tmp)    # 读数组元素
            return tmp

        # 函数调用：func(args)
        elif t == 'Call':
            func_name = node['func']['name']
            if func_name == 'read':
                # read()内建函数：生成read指令
                tmp = self.new_temp()
                self.emit('read', '_', '_', tmp)
                return tmp
            # 普通函数调用：先计算所有实参，生成param指令，然后emit call
            for arg in node['args']:
                v = self.gen(arg)
                self.emit('param', v, '_', '_')     # 依次压入参数
            tmp = self.new_temp()
            self.emit('call', func_name, str(len(node['args'])), tmp)
            return tmp

        # write语句：write(expr1, expr2, ...)
        elif t == 'Write':
            for a in node['args']:
                if a['type'] == 'CharVal':
                    # 字符字面量直接生成writec
                    self.emit('writec', str(a['value']), '_', '_')
                else:
                    v = self.gen(a)
                    self.emit('write', v, '_', '_')

        # return语句：return [expr]
        elif t == 'Return':
            if node['expr']:
                r = self.gen(node['expr'])
                self.emit('return', r, '_', '_')
                return r
            else:
                self.emit('return', '_', '_', '_')  # 无返回值return

        # if语句：生成条件跳转 + true分支 + false分支 + 回填
        elif t == 'If':
            jskip_true = self.gen_cond_jump(node['cond'], -1)  # 条件为假时跳转到false分支位置
            self.gen(node['true'])                              # 生成true分支代码
            if node['false']:
                # 有else分支：true分支末尾加无条件跳转到if结束，回填条件跳转目标到false分支
                jend = self.emit('J', '_', '_', '_')           # 跳过false分支
                false_target = self.next_quad
                self.backpatch(jskip_true, false_target)       # 条件为假→跳转到false
                self.gen(node['false'])                         # 生成false分支代码
                self.backpatch(jend, self.next_quad)           # 回填结束后跳转目标
            else:
                # 无else分支：条件为假直接跳到if之后
                self.backpatch(jskip_true, self.next_quad)

        # while循环：条件判断→循环体→回到条件
        # 布局: [条件] [跳转指令] [循环体] [无条件J回条件] [出口]
        elif t == 'While':
            cond_start = self.next_quad                          # 条件判断起始位置
            jexit = self.gen_cond_jump(node['cond'], -1)        # 条件为假时退出循环

            self.break_stack.append([])                          # 新建break回填列表
            self.continue_stack.append([])                       # 新建continue回填列表

            self.gen(node['body'])                               # 生成循环体
            self.emit('J', '_', '_', cond_start)                # 无条件跳回条件判断

            exit_idx = self.next_quad
            self.backpatch(jexit, exit_idx)                      # 回填出口
            for b in self.break_stack.pop():                     # 回填所有break
                self.backpatch(b, exit_idx)
            for c in self.continue_stack.pop():                   # 回填所有continue
                self.backpatch(c, cond_start)

        # for循环：初始化→条件→循环体→步进→回到条件
        # 布局: [init] [条件] [跳转] [循环体] [step] [J回条件] [出口]
        elif t == 'For':
            if node['init']:
                self.gen(node['init'])                           # 初始化（如i=0）
            cond_start = self.next_quad                          # 条件判断位置

            if node['cond']:
                jexit = self.gen_cond_jump(node['cond'], -1)    # 条件为假时退出
            else:
                jexit = None                                     # 无条件→无限循环

            self.break_stack.append([])
            self.continue_stack.append([])

            self.gen(node['body'])                               # 生成循环体
            step_start = self.next_quad
            if node['step']:
                self.gen(node['step'])                           # 步进（如i++）
            self.emit('J', '_', '_', cond_start)                # 跳回条件判断

            exit_idx = self.next_quad
            if jexit:
                self.backpatch(jexit, exit_idx)                  # 回填条件跳转出口
            for b in self.break_stack.pop():                     # 回填break→出口
                self.backpatch(b, exit_idx)
            for c in self.continue_stack.pop():                   # 回填continue→步进
                self.backpatch(c, step_start)

        # do-while循环：先执行循环体，再判断条件
        # 布局: [循环体] [条件: 为真时J回循环体开头] [出口]
        elif t == 'DoWhile':
            body_start = self.next_quad                          # 记录循环体起始位置

            self.break_stack.append([])
            self.continue_stack.append([])

            self.gen(node['body'])                               # 生成循环体

            cond_start = self.next_quad                          # 条件判断位置
            cond = node['cond']
            # 条件为真时跳回循环体开头
            if cond['type'] == 'BinOp' and cond['op'] in INV_COND:
                # 简单关系条件：生成正向跳转（为真则跳回body_start）
                left = self.gen(cond['left'])
                right = self.gen(cond['right'])
                self.emit(f'J{cond["op"]}', left, right, body_start)
            else:
                # 复杂条件：计算结果，不为0则跳回body_start
                cr = self.gen(cond)
                self.emit('J!=', cr, '0', body_start)

            exit_idx = self.next_quad
            for b in self.break_stack.pop():                     # 回填break→出口
                self.backpatch(b, exit_idx)
            for c in self.continue_stack.pop():                   # 回填continue→条件判断
                self.backpatch(c, cond_start)

        # break语句：生成无条件跳转，索引存入break_stack等待回填
        elif t == 'Break':
            idx = self.emit('J', '_', '_', '_')  # 暂放占位目标
            if self.break_stack:
                self.break_stack[-1].append(idx) # 记录到当前循环层

        # continue语句：生成无条件跳转，索引存入continue_stack等待回填
        elif t == 'Continue':
            idx = self.emit('J', '_', '_', '_')
            if self.continue_stack:
                self.continue_stack[-1].append(idx)

        return None  # gen方法默认返回None


# ========== Interpreter类：四元式解释器 ==========
# 遍历四元式序列，模拟执行指令
# 支持的内存模型：变量存储在mem字典中，数组存储在arrays字典中（稀疏存储）
class Interpreter:
    def __init__(self, quads, func_table, inputs=None):
        self.quads = quads              # 四元式列表
        self.func_table = func_table    # 函数表
        self.mem = {}                   # 变量内存：{变量名: 值}
        self.arrays = {}                # 数组内存：{数组名: {索引: 值}}（稀疏存储）
        self.inputs = inputs or []      # 输入数据列表（供read()使用）
        self.input_idx = 0              # 当前输入读取索引
        self.output = []                # 程序输出字符串列表
        self.pc = 0                     # 程序计数器（当前指令索引）
        self.param_stack = []           # 函数调用参数栈
        self.return_stack = []          # 函数返回栈（保存返回地址/内存等）

    # 取值：将四元式中的操作数转为实际值
    # 如果是数字字符串→int，如果是变量名→从mem中获取
    def val(self, x):
        if x == '_':
            return None
        try:
            return int(x)
        except ValueError:
            return self.mem.get(x, 0)  # 未定义变量默认值为0

    # 运行指定函数：从函数表获取入口地址，设置参数值
    # 返回值: (入口行号, 错误信息)
    def run_function(self, func_name):
        if func_name not in self.func_table:
            return -1, f"Error: 未定义函数 '{func_name}'"
        info = self.func_table[func_name]
        entry = info['entry']
        if entry is None:
            return -1, f"Error: 函数 '{func_name}' 只有声明没有定义"
        params = info['params']
        # 从参数栈底部弹出对应数量的参数值赋给形参
        for i, pname in enumerate(params):
            if i < len(self.param_stack):
                self.mem[pname] = self.param_stack[-(len(params) - i)]
        self.param_stack = self.param_stack[:-len(params)] if len(params) > 0 else self.param_stack
        return entry, None

    # 执行单条四元式指令
    # 返回值: (是否继续执行, 跳转标记)
    #         jumped = 'jumped': pc已被修改，不需要自增
    #         jumped = None:    正常执行，pc+1
    def _execute_quad(self, op, a1, a2, res):
        """Execute a single quad. Returns (continue_flag, jump_target)."""
        # 赋值指令：res = a1
        if op == '=':
            v = self.val(a1)
            self.mem[res] = v
            return True, None

        # 算术运算：+ - * / %
        elif op in ('+', '-', '*', '/', '%'):
            v1 = self.val(a1)
            v2 = self.val(a2)
            if op == '+': r = v1 + v2
            elif op == '-': r = v1 - v2
            elif op == '*': r = v1 * v2
            elif op == '/':
                if v2 == 0: self.output.append("Error: 除零错误"); return False, None
                r = v1 // v2     # 整数除法（向零取整）
            elif op == '%':
                if v2 == 0: self.output.append("Error: 模零错误"); return False, None
                r = v1 % v2
            self.mem[res] = r
            return True, None

        # 关系运算：< > <= >= == !=
        elif op in ('<', '>', '<=', '>=', '==', '!='):
            v1 = self.val(a1)
            v2 = self.val(a2)
            if op == '<': r = 1 if v1 < v2 else 0
            elif op == '>': r = 1 if v1 > v2 else 0
            elif op == '<=': r = 1 if v1 <= v2 else 0
            elif op == '>=': r = 1 if v1 >= v2 else 0
            elif op == '==': r = 1 if v1 == v2 else 0
            elif op == '!=': r = 1 if v1 != v2 else 0
            self.mem[res] = r        # 结果0或1（C风格）
            return True, None

        # 逻辑运算：&& 和 ||
        elif op in ('&&', '||'):
            v1 = self.val(a1)
            v2 = self.val(a2)
            if op == '&&': r = 1 if (v1 and v2) else 0
            elif op == '||': r = 1 if (v1 or v2) else 0
            self.mem[res] = r
            return True, None

        # 读取输入
        elif op == 'read':
            if self.input_idx < len(self.inputs):
                v = self.inputs[self.input_idx]   # 读取预设输入
                self.input_idx += 1
            else:
                v = 0                             # 无更多输入时默认0
            self.mem[res] = v
            return True, None

        # 写整数：输出a1的数值
        elif op == 'write':
            v = self.val(a1)
            self.output.append(str(v))
            return True, None

        # 写字符：输出a1数值对应的字符
        elif op == 'writec':
            v = self.val(a1)
            self.output.append(chr(v))
            return True, None

        # 读数组元素：res = arr[a2]
        elif op == '=[]':
            arr = self.arrays.get(a1, {})
            idx = self.val(a2)
            v = arr.get(idx, 0)      # 稀疏存储，未初始化为0
            self.mem[res] = v
            return True, None

        # 写数组元素：arr[res] = a1  （注意：res是数组名，a2是索引，a1是值）
        elif op == '[]=':
            v = self.val(a1)         # 要写入的值
            idx = self.val(a2)       # 索引
            if res not in self.arrays:
                self.arrays[res] = {}
            self.arrays[res][idx] = v
            return True, None

        # 函数调用参数传递：将a1的值压入参数栈
        elif op == 'param':
            v = self.val(a1)
            self.param_stack.append(v)
            return True, None

        # 函数调用：call func_name, num_args, result_temp
        elif op == 'call':
            func_name = a1
            num_args = int(a2)
            # 保存调用者环境：PC位置、内存、数组（用于返回后恢复）
            saved_pc = self.pc + 1
            saved_mem = dict(self.mem)
            saved_arrays = {k: dict(v) for k, v in self.arrays.items()}
            entry, err = self.run_function(func_name)
            if entry >= 0:
                self.pc = entry                    # 跳转到函数入口
                self.return_stack.append((saved_pc, res, saved_mem, saved_arrays))
                return True, 'jumped'
            else:
                if err:
                    self.output.append(err)
                return True, None

        # 函数返回：恢复调用者环境
        elif op == 'return':
            v = self.val(a1)                       # 返回值
            if self.return_stack:
                ret_pc, ret_dest, saved_mem, saved_arrays = self.return_stack.pop()
                saved_val = v
                # 恢复调用者的内存和数组状态
                self.mem = saved_mem
                self.arrays = saved_arrays
                if ret_dest != '_' and saved_val is not None:
                    self.mem[ret_dest] = saved_val # 将返回值写入调用者的临时变量
                self.pc = ret_pc                   # 返回调用点
                return True, 'jumped'
            else:
                self.retval = v                    # 顶层return：保存最终返回值
                return False, None                 # 停止执行

        # 无条件跳转：J _, _, target
        elif op == 'J':
            self.pc = int(res)                     # 直接设置PC
            return True, 'jumped'

        # 条件跳转：J<, J>, J<=, J>=, J==, J!=
        elif op.startswith('J') and len(op) > 1:
            rop = op[1:]                           # 提取关系操作符
            v1 = self.val(a1)
            v2 = self.val(a2)
            cond = False
            if rop == '<': cond = v1 < v2
            elif rop == '>': cond = v1 > v2
            elif rop == '<=': cond = v1 <= v2
            elif rop == '>=': cond = v1 >= v2
            elif rop == '==': cond = v1 == v2
            elif rop == '!=': cond = v1 != v2
            if cond:
                self.pc = int(res)                 # 条件满足：跳转
                return True, 'jumped'
            else:
                return True, None                  # 条件不满足：继续下一条

        return True, None  # 未知操作，忽略并继续

    # 在指定范围内顺序执行四元式（用于全局初始化代码）
    def _execute_range(self, start, end):
        """Execute quads from start to end (exclusive), handling only simple ops."""
        self.pc = start
        while self.pc < end:
            op, a1, a2, res = self.quads[self.pc]
            cont, _ = self._execute_quad(op, a1, a2, res)
            if not cont:
                break
            if _ != 'jumped':       # 不是通过跳转修改的PC，手动自增
                self.pc += 1

    # 运行程序入口：从指定函数开始执行四元式序列
    # 返回值: 程序输出的字符串（拼接所有write输出）
    def run(self, func_name='main'):
        self.retval = 0              # 初始化返回值
        # 获取入口地址
        if func_name in self.func_table and self.func_table[func_name]['entry'] is not None:
            main_entry = self.func_table[func_name]['entry']
        else:
            main_entry = 0           # 默认从第0条开始

        # Execute global init quads (from 0 to main_entry)
        # 执行main函数之前的全局初始化代码（全局变量初始化等）
        if main_entry > 0:
            self._execute_range(0, main_entry)

        self.pc = main_entry

        max_steps = 500000            # 最大执行步数（防止死循环）
        steps = 0

        while self.pc < len(self.quads):
            steps += 1
            if steps > max_steps:
                self.output.append("Error: 执行步数超限")
                break
            op, a1, a2, res = self.quads[self.pc]
            cont, jumped = self._execute_quad(op, a1, a2, res)
            if not cont:
                break                  # 遇到顶层return或错误
            if jumped != 'jumped':
                self.pc += 1           # 正常执行，pc自增

        return ''.join(self.output)   # 拼接所有输出字符串


# ========== ast_to_str函数：将AST转为可读字符串 ==========
# 递归遍历AST节点，生成缩进格式的文本表示
# 用于在.int文件和Web界面中展示语法树
def ast_to_str(node, indent=0):
    if node is None:
        return 'None'
    lines = []
    t = node['type']
    prefix = '  ' * indent    # 缩进（每级2空格）
    ln = node.get('line', 0)  # 对应源代码行号

    # 辅助函数：生成行号标签 [line]
    def ln_tag(line):
        return f'[{line}]' if line else ''

    # 程序根节点
    if t == 'Program':
        lines.append(f"{prefix}Program")
        for s in node['body']:
            lines.append(ast_to_str(s, indent + 1))

    # 函数声明
    elif t == 'FuncDecl':
        ret = node.get('ret', 'int')
        lines.append(f"{prefix}FunctionDecl({ret} {node['name']}){ln_tag(ln)}")
        for p in node['params']:
            lines.append(f"{prefix}  Param({p['type']} {p['name']})[{p.get('line', 0)}]")

    # 函数定义
    elif t == 'FuncDef':
        ret = node.get('ret', 'int')
        lines.append(f"{prefix}FunctionDef({ret} {node['name']}){ln_tag(ln)}")
        for p in node['params']:
            lines.append(f"{prefix}  Param({p['type']} {p['name']})[{p.get('line', 0)}]")
        body = node['body']
        lines.append(ast_to_str(body, indent + 1))

    # 代码块
    elif t == 'Block':
        lines.append(f"{prefix}Compound")
        for s in node['body']:
            lines.append(ast_to_str(s, indent + 1))

    # 变量声明
    elif t == 'VarDecl':
        for d in node['decls']:
            dln = d.get('line', 0)
            if d['arr_size']:
                lines.append(f"{prefix}VarDecl(int {d['name']}[{d['arr_size']}]){ln_tag(dln)}")
            else:
                lines.append(f"{prefix}VarDecl(int {d['name']}){ln_tag(dln)}")
            if d['init'] is not None:
                lines.append(f"{prefix}  Init")
                lines.append(ast_to_str(d['init'], indent + 2))

    # 赋值表达式
    elif t == 'Assign':
        lines.append(f"{prefix}AssignExpr{ln_tag(ln)}")
        lines.append(ast_to_str(node['target'], indent + 1))
        lines.append(ast_to_str(node['expr'], indent + 1))

    # if语句
    elif t == 'If':
        lines.append(f"{prefix}IfStmt")
        lines.append(ast_to_str(node['cond'], indent + 1))
        lines.append(ast_to_str(node['true'], indent + 1))
        if node['false']:
            lines.append(f"{prefix}ElseStmt")
            lines.append(ast_to_str(node['false'], indent + 1))

    # while循环
    elif t == 'While':
        lines.append(f"{prefix}WhileStmt")
        lines.append(ast_to_str(node['cond'], indent + 1))
        lines.append(ast_to_str(node['body'], indent + 1))

    # for循环
    elif t == 'For':
        lines.append(f"{prefix}ForStmt")
        if node['init']:
            lines.append(f"{prefix}  Init")
            lines.append(ast_to_str(node['init'], indent + 2))
        if node['cond']:
            lines.append(f"{prefix}  Condition")
            lines.append(ast_to_str(node['cond'], indent + 2))
        if node['step']:
            lines.append(f"{prefix}  Step")
            lines.append(ast_to_str(node['step'], indent + 2))
        lines.append(ast_to_str(node['body'], indent + 1))

    # do-while循环
    elif t == 'DoWhile':
        lines.append(f"{prefix}DoWhileStmt")
        lines.append(ast_to_str(node['body'], indent + 1))
        lines.append(f"{prefix}  Condition")
        lines.append(ast_to_str(node['cond'], indent + 2))

    # break语句
    elif t == 'Break':
        lines.append(f"{prefix}BreakStmt{ln_tag(ln)}")

    # continue语句
    elif t == 'Continue':
        lines.append(f"{prefix}ContinueStmt{ln_tag(ln)}")

    # return语句
    elif t == 'Return':
        if node.get('expr'):
            lines.append(f"{prefix}ReturnStmt")
            lines.append(ast_to_str(node['expr'], indent + 1))
        else:
            lines.append(f"{prefix}ReturnStmt")

    # write语句：展开为CallExpr(write)形式
    elif t == 'Write':
        for a in node['args']:
            lines.append(f"{prefix}ExprStmt")
            lines.append(f"{prefix}  CallExpr(write){ln_tag(ln)}")
            lines.append(ast_to_str(a, indent + 2))

    # 表达式语句
    elif t == 'ExprStmt':
        lines.append(f"{prefix}ExprStmt")
        lines.append(ast_to_str(node['expr'], indent + 1))

    # 二元运算
    elif t == 'BinOp':
        lines.append(f"{prefix}BinaryExpr({node['op']}){ln_tag(ln)}")
        lines.append(ast_to_str(node['left'], indent + 1))
        lines.append(ast_to_str(node['right'], indent + 1))

    # 一元运算
    elif t == 'UnaryOp':
        lines.append(f"{prefix}UnaryExpr({node['op']}){ln_tag(ln)}")
        lines.append(ast_to_str(node['operand'], indent + 1))

    # 后缀自增自减
    elif t == 'PostOp':
        lines.append(f"{prefix}PostExpr({node['op']}){ln_tag(ln)}")
        lines.append(ast_to_str(node['operand'], indent + 1))

    # 字符字面量
    elif t == 'CharVal':
        ch = chr(node['value'])
        esc = repr(ch)[1:-1]  # repr获取转义表示（如'\n'）
        lines.append(f"{prefix}Literal('{esc}'){ln_tag(ln)}")

    # 数值字面量
    elif t == 'Num':
        lines.append(f"{prefix}Literal({node['value']}){ln_tag(ln)}")

    # 标识符（变量）
    elif t == 'Var':
        lines.append(f"{prefix}Identifier({node['name']}){ln_tag(ln)}")

    # 数组访问
    elif t == 'ArrayAccess':
        lines.append(f"{prefix}ArrayAccess{ln_tag(ln)}")
        lines.append(ast_to_str(node['array'], indent + 1))
        lines.append(ast_to_str(node['index'], indent + 1))

    # 函数调用
    elif t == 'Call':
        func_name = node['func']['name'] if isinstance(node['func'], dict) else '?'
        lines.append(f"{prefix}CallExpr({func_name}){ln_tag(ln)}")
        for a in node['args']:
            lines.append(ast_to_str(a, indent + 1))

    # 条件节点
    elif t == 'Condition':
        lines.append(f"{prefix}Condition")
        lines.append(ast_to_str(node['cond'], indent + 1))

    # 未知节点类型：直接输出类型名
    else:
        lines.append(f"{prefix}{t}{ln_tag(ln)}")

    return '\n'.join(lines)


# ========== token_code函数：将Token映射为预定义编码 ==========
# 返回Token的类型编码，用于生成统一格式的Token序列输出
# KEYWORD→102-112, PUNCT→201-306, OP→211-226, NUM→400, STRING→500, ID/其他→700
def token_code(t):
    val = t.value
    typ = t.type

    if val == 'write':
        return 700

    if typ == 'KEYWORD':
        if val == 'int':
            return 102                                       # int关键字
        kw_map = {'if': 103, 'else': 104, 'while': 105, 'return': 106, 'void': 107,
                  'for': 108, 'do': 109, 'continue': 110, 'break': 111, 'read': 112}
        if val in kw_map:
            return kw_map[val]
        return 700                                           # 其他关键字

    if typ == 'ID':
        return 700                                           # 标识符

    if typ == 'NUM':
        return 400                                           # 数值

    if typ == 'STRING':
        return 500                                           # 字符串

    if typ == 'OP':
        # 运算符编码映射
        op_map = {
            '=': 219, '&&': 217, '||': 218,
            '+': 211, '-': 212, '*': 213, '/': 214, '%': 215,
            '<': 216, '>': 220, '<=': 221, '>=': 222, '==': 223, '!=': 224,
            '++': 225, '--': 226
        }
        return op_map.get(val, 0)

    if typ == 'PUNCT':
        # 标点符号编码映射
        punct_map = {
            '(': 201, ')': 202, '{': 301, '}': 302, ';': 303, ',': 304,
            '[': 305, ']': 306
        }
        return punct_map.get(val, 0)

    return 0  # 未知类型


# ========== process_32函数：任务3.2主处理接口 ==========
# 完整编译流程：词法分析→语法分析→AST生成→四元式生成→解释执行
# 参数 code: 源代码字符串
# 参数 inputs: read()需要的输入整数列表
# 返回值: 字典，包含tokens, ast, symbol_table, quadruples, func_table_info, output, retval等
def process_32(code, inputs=None):
    try:
        # 第一步：词法分析
        lexer = Lexer(code)
        tokens = lexer.tokenize()

        # 构造Token序列字符串（格式：值\t编码\t行号）
        tokens_str = "===== Token 序列 =====\n" + '\n'.join(
            f"{t.value}\t{token_code(t)}\t{t.line}" for t in tokens
        )

        # 第二步：语法分析——生成AST
        parser = Parser(tokens)
        ast = parser.parse()

        # 将AST转为可读字符串
        ast_str = ast_to_str(ast)

        # 第三步：语义分析与四元式生成
        gen = QuadGenerator()
        gen.gen(ast)

        # 构造符号表字符串（每行格式：名称: (name, kind, type)）
        sym_str = '\n'.join(f"{k}: {v}" for k, v in gen.symbols.items())

        # 构造四元式字符串（每行格式：索引: (op, a1, a2, res)）
        quads_str = '\n'.join(f"{i}: ({q[0]}, {q[1]}, {q[2]}, {q[3]})" for i, q in enumerate(gen.quads))

        # 构造函数表信息字符串（格式：函数名=入口行号,参数1,参数2; ...）
        ft_parts = []
        for name, info in gen.func_table.items():
            if info.get('entry') is not None:
                params_str = ','.join(info.get('params', []))
                ft_parts.append(f'{name}={info["entry"]},{params_str}' if params_str else f'{name}={info["entry"]}')
        func_table_info = '=== 函数表: ' + '; '.join(ft_parts) if ft_parts else '=== 函数表: main=0'

        # 第四步：解释执行四元式
        interp = Interpreter(gen.quads, gen.func_table, inputs)
        output = interp.run()         # 程序输出字符串
        retval = interp.retval        # 程序返回值

        # 返回完整结果字典
        return {
            'source': code,
            'tokens': tokens_str,           # Token序列文本
            'ast': ast_str,                 # AST文本
            'symbol_table': sym_str,        # 符号表文本
            'quadruples': quads_str,        # 四元式文本
            'func_table_info': func_table_info,  # 函数表信息文本
            'quads_list': gen.quads,        # 四元式原始列表（供4.2使用）
            'func_table': gen.func_table,   # 函数表原始字典（供4.2使用）
            'output': output,               # 程序输出
            'retval': retval,               # 返回值
        }
    except Exception as e:
        # 捕获所有异常，返回错误信息和完整堆栈
        import traceback
        return {'error': str(e) + '\n' + traceback.format_exc()}
