import re

INV_COND = {'<': '>=', '>': '<=', '<=': '>', '>=': '<', '==': '!=', '!=': '=='}


class Token:
    def __init__(self, type, value, line):
        self.type = type
        self.value = value
        self.line = line
    def __repr__(self):
        return f"<{self.type}, {self.value}, line {self.line}>"


class Lexer:
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.line = 1
        self.tokens = []

    def tokenize(self):
        rules = [
            ('COMMENT', r'//[^\n]*'),
            ('WHITESPACE', r'[ \t\r]+'),
            ('NEWLINE', r'\n'),
            ('KEYWORD', r'\b(int|if|else|while|return|void|main|for|do|continue|break|read|write)\b'),
            ('OP', r'==|!=|<=|>=|\|\||&&|<|>|\+\+|\-\-|\+|-|\*|/|%|='),
            ('PUNCT', r'[(){}\[\];,\uff1b]'),
            ('STRING', r"'[^']*'"),
            ('STRING_DQ', r'"[^"]*"'),
            ('NUM', r'\d+'),
            ('ID', r'[a-zA-Z_]\w*'),
        ]
        while self.pos < len(self.text):
            matched = False
            for name, pattern in rules:
                m = re.compile(pattern).match(self.text, self.pos)
                if m:
                    val = m.group(0)
                    if name == 'NEWLINE':
                        self.line += 1
                    elif name not in ('WHITESPACE', 'COMMENT'):
                        ttype = 'ID'
                        if name == 'KEYWORD':
                            ttype = 'KEYWORD'
                        elif name == 'OP':
                            ttype = 'OP'
                        elif name == 'PUNCT':
                            ttype = 'PUNCT'
                            if val == '\uff1b':
                                val = ';'
                        elif name == 'NUM':
                            ttype = 'NUM'
                        elif name in ('CHAR', 'STRING', 'STRING_DQ'):
                            ttype = 'STRING'
                        self.tokens.append(Token(ttype, val, self.line))
                    self.pos = m.end(0)
                    matched = True
                    break
            if not matched:
                snippet = self.text[self.pos:self.pos+20]
                raise Exception(f"词法错误 第{self.line}行: 无法识别 '{snippet}'")
        return self.tokens


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def cur(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def _line(self):
        t = self.cur()
        return t.line if t else 0

    def eat(self, typ=None, val=None):
        t = self.cur()
        if t:
            type_ok = typ is None or t.type == typ or (typ == 'ID' and t.type == 'KEYWORD')
            val_ok = val is None or t.value == val
            if type_ok and val_ok:
                self.pos += 1
                return t
        exp = val if val else (typ or 'token')
        raise Exception(f"语法错误 第{t.line if t else 'EOF'}行: 期望{exp}, 得到{t}")

    def parse(self):
        stmts = []
        while self.cur():
            s = self.parse_external_decl()
            if s:
                stmts.append(s)
        return {'type': 'Program', 'body': stmts}

    def parse_external_decl(self):
        t = self.cur()
        if not t:
            return None
        if t.type == 'KEYWORD' and t.value in ('int', 'void'):
            if self.pos + 2 < len(self.tokens) and self.tokens[self.pos + 2].value == '(':
                return self.parse_func_def()
        if t.type in ('ID', 'KEYWORD') and self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].value == '(':
            return self.parse_func_def_no_type()
        return self.parse_statement()

    def parse_func_def(self):
        start_line = self._line()
        ret_type = self.eat('KEYWORD').value
        name = self.eat('ID').value
        self.eat('PUNCT', '(')
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
            self.eat('PUNCT', ';')
            return {'type': 'FuncDecl', 'name': name, 'ret': ret_type, 'params': params, 'line': start_line}
        body = self.parse_block()
        return {'type': 'FuncDef', 'name': name, 'ret': ret_type, 'params': params, 'body': body, 'line': start_line}

    def parse_func_def_no_type(self):
        start_line = self._line()
        name = self.eat('ID').value
        self.eat('PUNCT', '(')
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
            self.eat('PUNCT', ';')
            return {'type': 'FuncDecl', 'name': name, 'ret': 'int', 'params': params, 'line': start_line}
        body = self.parse_block()
        return {'type': 'FuncDef', 'name': name, 'ret': 'int', 'params': params, 'body': body, 'line': start_line}

    def parse_block(self):
        stmts = []
        self.eat('PUNCT', '{')
        while self.cur() and self.cur().value != '}':
            s = self.parse_statement()
            if s:
                stmts.append(s)
        self.eat('PUNCT', '}')
        return {'type': 'Block', 'body': stmts}

    def parse_statement(self):
        t = self.cur()
        if not t:
            return None
        if t.value == 'int':
            return self.parse_var_decl()
        if t.value == '{':
            return self.parse_block()
        if t.value == 'if':
            return self.parse_if()
        if t.value == 'while':
            return self.parse_while()
        if t.value == 'for':
            return self.parse_for()
        if t.value == 'do':
            return self.parse_do_while()
        if t.value == 'return':
            return self.parse_return()
        if t.value == 'break':
            line = t.line
            self.eat('KEYWORD', 'break')
            self.eat('PUNCT', ';')
            return {'type': 'Break', 'line': line}
        if t.value == 'continue':
            line = t.line
            self.eat('KEYWORD', 'continue')
            self.eat('PUNCT', ';')
            return {'type': 'Continue', 'line': line}
        if t.value == 'write':
            return self.parse_write()
        return self.parse_expr_stmt()

    def parse_var_decl(self):
        start_line = self._line()
        self.eat('KEYWORD', 'int')
        decls = []
        while True:
            name_line = self._line()
            name = self.eat('ID').value
            arr_size = None
            if self.cur() and self.cur().value == '[':
                self.eat('PUNCT', '[')
                arr_size = int(self.eat('NUM').value)
                self.eat('PUNCT', ']')
            init = None
            if self.cur() and self.cur().value == '=':
                self.eat('OP', '=')
                init = self.parse_expr()
            decls.append({'name': name, 'arr_size': arr_size, 'init': init, 'line': name_line})
            if self.cur() and self.cur().value == ',':
                self.eat('PUNCT', ',')
            else:
                break
        self.eat('PUNCT', ';')
        return {'type': 'VarDecl', 'decls': decls, 'line': start_line}

    def parse_if(self):
        start_line = self._line()
        self.eat('KEYWORD', 'if')
        self.eat('PUNCT', '(')
        cond = self.parse_expr()
        self.eat('PUNCT', ')')
        tb = self.parse_block_or_stmt()
        fb = None
        if self.cur() and self.cur().value == 'else':
            self.eat('KEYWORD', 'else')
            fb = self.parse_block_or_stmt()
        return {'type': 'If', 'cond': cond, 'true': tb, 'false': fb, 'line': start_line}

    def parse_while(self):
        start_line = self._line()
        self.eat('KEYWORD', 'while')
        self.eat('PUNCT', '(')
        cond = self.parse_expr()
        self.eat('PUNCT', ')')
        body = self.parse_block_or_stmt()
        return {'type': 'While', 'cond': cond, 'body': body, 'line': start_line}

    def parse_for(self):
        start_line = self._line()
        self.eat('KEYWORD', 'for')
        self.eat('PUNCT', '(')
        init = self.parse_expr() if self.cur() and self.cur().value != ';' else None
        self.eat('PUNCT', ';')
        cond = self.parse_expr() if self.cur() and self.cur().value != ';' else None
        self.eat('PUNCT', ';')
        step = self.parse_expr() if self.cur() and self.cur().value != ')' else None
        self.eat('PUNCT', ')')
        body = self.parse_block_or_stmt()
        return {'type': 'For', 'init': init, 'cond': cond, 'step': step, 'body': body, 'line': start_line}

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

    def parse_return(self):
        start_line = self._line()
        self.eat('KEYWORD', 'return')
        expr = self.parse_expr() if self.cur() and self.cur().value != ';' else None
        self.eat('PUNCT', ';')
        return {'type': 'Return', 'expr': expr, 'line': start_line}

    def parse_write(self):
        start_line = self._line()
        self.eat('KEYWORD', 'write')
        self.eat('PUNCT', '(')
        args = []
        while self.cur() and self.cur().value != ')':
            args.append(self.parse_expr())
            if self.cur() and self.cur().value == ',':
                self.eat('PUNCT', ',')
        self.eat('PUNCT', ')')
        self.eat('PUNCT', ';')
        return {'type': 'Write', 'args': args, 'line': start_line}

    def parse_expr_stmt(self):
        start_line = self._line()
        expr = self.parse_expr()
        self.eat('PUNCT', ';')
        return {'type': 'ExprStmt', 'expr': expr, 'line': start_line}

    def parse_block_or_stmt(self):
        if self.cur() and self.cur().value == '{':
            return self.parse_block()
        else:
            return {'type': 'Block', 'body': [self.parse_statement()]}

    def parse_expr(self):
        return self.parse_assign()

    def parse_assign(self):
        node = self.parse_or()
        if self.cur() and self.cur().value == '=':
            op_line = self._line()
            self.eat('OP', '=')
            right = self.parse_assign()
            return {'type': 'Assign', 'target': node, 'expr': right, 'line': op_line}
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.cur() and self.cur().value == '||':
            op = self.eat('OP')
            right = self.parse_and()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    def parse_and(self):
        node = self.parse_eq()
        while self.cur() and self.cur().value == '&&':
            op = self.eat('OP')
            right = self.parse_eq()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    def parse_eq(self):
        node = self.parse_rel()
        while self.cur() and self.cur().value in ('==', '!='):
            op = self.eat('OP')
            right = self.parse_rel()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    def parse_rel(self):
        node = self.parse_add()
        while self.cur() and self.cur().value in ('<', '>', '<=', '>='):
            op = self.eat('OP')
            right = self.parse_add()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    def parse_add(self):
        node = self.parse_mul()
        while self.cur() and self.cur().value in ('+', '-'):
            op = self.eat('OP')
            right = self.parse_mul()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    def parse_mul(self):
        node = self.parse_unary()
        while self.cur() and self.cur().value in ('*', '/', '%'):
            op = self.eat('OP')
            right = self.parse_unary()
            node = {'type': 'BinOp', 'op': op.value, 'left': node, 'right': right, 'line': op.line}
        return node

    def parse_unary(self):
        t = self.cur()
        if t and t.value == '-':
            line = t.line
            self.eat('OP', '-')
            operand = self.parse_unary()
            return {'type': 'UnaryOp', 'op': '-', 'operand': operand, 'line': line}
        return self.parse_postfix()

    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            t = self.cur()
            if t and t.value == '[':
                self.eat('PUNCT', '[')
                idx = self.parse_expr()
                self.eat('PUNCT', ']')
                node = {'type': 'ArrayAccess', 'array': node, 'index': idx, 'line': t.line}
            elif t and t.value == '(':
                self.eat('PUNCT', '(')
                args = []
                while self.cur() and self.cur().value != ')':
                    args.append(self.parse_expr())
                    if self.cur() and self.cur().value == ',':
                        self.eat('PUNCT', ',')
                self.eat('PUNCT', ')')
                node = {'type': 'Call', 'func': node, 'args': args, 'line': t.line}
            elif t and t.value in ('++', '--'):
                op = self.eat('OP').value
                node = {'type': 'PostOp', 'op': op, 'operand': node, 'line': t.line}
            else:
                break
        return node

    def parse_primary(self):
        t = self.cur()
        if t.type == 'NUM':
            self.eat('NUM')
            return {'type': 'Num', 'value': int(t.value), 'line': t.line}
        elif t.type == 'STRING':
            self.eat('STRING')
            val_str = t.value
            quote_char = val_str[0]
            inner = val_str[1:-1]
            if quote_char == '"':
                val = sum(ord(c) for c in inner) % 65536
                return {'type': 'Num', 'value': val, 'line': t.line}
            if len(inner) == 1:
                val = ord(inner)
            elif inner.startswith('\\') and len(inner) == 2:
                ch_map = {'n': '\n', 't': '\t', '0': '\0', '\\': '\\', '\'': '\''}
                ch = ch_map.get(inner[1], inner[1])
                val = ord(ch)
            else:
                val = sum(ord(c) for c in inner) % 256
            return {'type': 'CharVal', 'value': val, 'line': t.line}
        elif t.type in ('ID', 'KEYWORD'):
            self.eat(t.type)
            return {'type': 'Var', 'name': t.value, 'line': t.line}
        elif t.value == '(':
            self.eat('PUNCT', '(')
            node = self.parse_expr()
            self.eat('PUNCT', ')')
            return node
        raise Exception(f"语法错误 第{t.line}行: 意外的token {t}")


class SymbolEntry:
    def __init__(self, name, kind, typ, extra=None):
        self.name = name
        self.kind = kind
        self.type = typ
        self.extra = extra

    def __repr__(self):
        e = ""
        if self.extra:
            if 'arr_size' in self.extra:
                e = f", size={self.extra['arr_size']}"
            elif 'params' in self.extra:
                e = f", params={self.extra['params']}"
        return f"({self.name}, {self.kind}, {self.type}{e})"


class QuadGenerator:
    def __init__(self):
        self.quads = []
        self.temp_cnt = 0
        self.symbols = {}
        self.next_quad = 0
        self.func_table = {}
        self.break_stack = []
        self.continue_stack = []
        self.current_func = None

    def new_temp(self):
        self.temp_cnt += 1
        return f"t{self.temp_cnt}"

    def emit(self, op, a1, a2, res):
        q = (op, str(a1), str(a2), str(res))
        self.quads.append(q)
        idx = self.next_quad
        self.next_quad += 1
        return idx

    def backpatch(self, idx, target):
        if idx is None:
            return
        q = self.quads[idx]
        self.quads[idx] = (q[0], q[1], q[2], str(target))

    def gen_cond_jump(self, cond, true_target):
        """Generate code for condition, return index of jump-to-false quad.
        If cond is simple relational (a <op> b), emit inverted J<inv> to skip=true_target.
        If cond is complex, emit J== cond_result 0, true_target (skip when false).
        """
        if cond['type'] == 'BinOp' and cond['op'] in INV_COND:
            left = self.gen(cond['left'])
            right = self.gen(cond['right'])
            inv_op = INV_COND[cond['op']]
            return self.emit(f'J{inv_op}', left, right, str(true_target))
        else:
            cr = self.gen(cond)
            return self.emit('J==', cr, '0', str(true_target))

    def gen(self, node):
        if node is None:
            return None
        t = node['type']

        if t == 'Program':
            for s in node['body']:
                self.gen(s)

        elif t == 'Block':
            for s in node['body']:
                self.gen(s)

        elif t == 'FuncDecl':
            self.symbols[node['name']] = SymbolEntry(node['name'], 'function', node['ret'],
                                                      {'params': [p['name'] for p in node['params']]})
            self.func_table[node['name']] = {'params': [p['name'] for p in node['params']], 'entry': None}

        elif t == 'FuncDef':
            self.current_func = node['name']
            for p in node['params']:
                self.symbols[p['name']] = SymbolEntry(p['name'], 'param', 'int')
            params_list = [p['name'] for p in node['params']]
            self.symbols[node['name']] = SymbolEntry(node['name'], 'function', node['ret'],
                                                      {'params': params_list})
            self.func_table[node['name']] = {'params': params_list, 'entry': self.next_quad}
            self.gen(node['body'])
            if not self.quads or self.quads[-1][0] != 'return':
                self.emit('return', '0', '_', '_')

        elif t == 'VarDecl':
            for d in node['decls']:
                if d['arr_size'] is not None:
                    self.symbols[d['name']] = SymbolEntry(d['name'], 'array', 'int',
                                                          {'arr_size': d['arr_size']})
                else:
                    self.symbols[d['name']] = SymbolEntry(d['name'], 'var', 'int')
                if d['init'] is not None:
                    r = self.gen(d['init'])
                    self.emit('=', r, '_', d['name'])

        elif t == 'Assign':
            val = self.gen(node['expr'])
            target = node['target']
            if target['type'] == 'Var':
                self.emit('=', val, '_', target['name'])
            elif target['type'] == 'ArrayAccess':
                arr_name = target['array']['name']
                idx = self.gen(target['index'])
                self.emit('[]=', val, idx, arr_name)
            return val

        elif t == 'ExprStmt':
            return self.gen(node['expr'])

        elif t == 'BinOp':
            left = self.gen(node['left'])
            right = self.gen(node['right'])
            tmp = self.new_temp()
            self.emit(node['op'], left, right, tmp)
            return tmp

        elif t == 'PostOp':
            op = node['op']
            operand = node['operand']
            if operand['type'] == 'Var':
                op_char = '+' if op == '++' else '-'
                tmp = self.new_temp()
                self.emit(op_char, operand['name'], '1', tmp)
                self.emit('=', tmp, '_', operand['name'])
                return tmp
            return self.gen(operand)
        elif t == 'UnaryOp':
            operand = self.gen(node['operand'])
            if node['op'] == '-':
                tmp = self.new_temp()
                self.emit('-', '0', operand, tmp)
                return tmp

        elif t == 'Num':
            return str(node['value'])

        elif t == 'CharVal':
            return str(node['value'])

        elif t == 'Var':
            return node['name']

        elif t == 'ArrayAccess':
            arr_name = node['array']['name']
            idx = self.gen(node['index'])
            tmp = self.new_temp()
            self.emit('=[]', arr_name, idx, tmp)
            return tmp

        elif t == 'Call':
            func_name = node['func']['name']
            if func_name == 'read':
                tmp = self.new_temp()
                self.emit('read', '_', '_', tmp)
                return tmp
            for arg in node['args']:
                v = self.gen(arg)
                self.emit('param', v, '_', '_')
            tmp = self.new_temp()
            self.emit('call', func_name, str(len(node['args'])), tmp)
            return tmp

        elif t == 'Write':
            for a in node['args']:
                if a['type'] == 'CharVal':
                    self.emit('writec', str(a['value']), '_', '_')
                else:
                    v = self.gen(a)
                    self.emit('write', v, '_', '_')

        elif t == 'Return':
            if node['expr']:
                r = self.gen(node['expr'])
                self.emit('return', r, '_', '_')
                return r
            else:
                self.emit('return', '_', '_', '_')

        elif t == 'If':
            jskip_true = self.gen_cond_jump(node['cond'], -1)
            self.gen(node['true'])
            if node['false']:
                jend = self.emit('J', '_', '_', '_')
                false_target = self.next_quad
                self.backpatch(jskip_true, false_target)
                self.gen(node['false'])
                self.backpatch(jend, self.next_quad)
            else:
                self.backpatch(jskip_true, self.next_quad)

        elif t == 'While':
            cond_start = self.next_quad
            jexit = self.gen_cond_jump(node['cond'], -1)

            self.break_stack.append([])
            self.continue_stack.append([])

            self.gen(node['body'])
            self.emit('J', '_', '_', cond_start)

            exit_idx = self.next_quad
            self.backpatch(jexit, exit_idx)
            for b in self.break_stack.pop():
                self.backpatch(b, exit_idx)
            for c in self.continue_stack.pop():
                self.backpatch(c, cond_start)

        elif t == 'For':
            if node['init']:
                self.gen(node['init'])
            cond_start = self.next_quad

            if node['cond']:
                jexit = self.gen_cond_jump(node['cond'], -1)
            else:
                jexit = None

            self.break_stack.append([])
            self.continue_stack.append([])

            self.gen(node['body'])
            step_start = self.next_quad
            if node['step']:
                self.gen(node['step'])
            self.emit('J', '_', '_', cond_start)

            exit_idx = self.next_quad
            if jexit:
                self.backpatch(jexit, exit_idx)
            for b in self.break_stack.pop():
                self.backpatch(b, exit_idx)
            for c in self.continue_stack.pop():
                self.backpatch(c, step_start)

        elif t == 'DoWhile':
            body_start = self.next_quad

            self.break_stack.append([])
            self.continue_stack.append([])

            self.gen(node['body'])

            cond_start = self.next_quad
            cond = node['cond']
            if cond['type'] == 'BinOp' and cond['op'] in INV_COND:
                left = self.gen(cond['left'])
                right = self.gen(cond['right'])
                self.emit(f'J{cond["op"]}', left, right, body_start)
            else:
                cr = self.gen(cond)
                self.emit('J!=', cr, '0', body_start)

            exit_idx = self.next_quad
            for b in self.break_stack.pop():
                self.backpatch(b, exit_idx)
            for c in self.continue_stack.pop():
                self.backpatch(c, cond_start)

        elif t == 'Break':
            idx = self.emit('J', '_', '_', '_')
            if self.break_stack:
                self.break_stack[-1].append(idx)

        elif t == 'Continue':
            idx = self.emit('J', '_', '_', '_')
            if self.continue_stack:
                self.continue_stack[-1].append(idx)

        return None


class Interpreter:
    def __init__(self, quads, func_table, inputs=None):
        self.quads = quads
        self.func_table = func_table
        self.mem = {}
        self.arrays = {}
        self.inputs = inputs or []
        self.input_idx = 0
        self.output = []
        self.pc = 0
        self.param_stack = []
        self.return_stack = []

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
        for i, pname in enumerate(params):
            if i < len(self.param_stack):
                self.mem[pname] = self.param_stack[-(len(params) - i)]
        self.param_stack = self.param_stack[:-len(params)] if len(params) > 0 else self.param_stack
        return entry, None

    def _execute_quad(self, op, a1, a2, res):
        """Execute a single quad. Returns (continue_flag, jump_target)."""
        if op == '=':
            v = self.val(a1)
            self.mem[res] = v
            return True, None

        elif op in ('+', '-', '*', '/', '%'):
            v1 = self.val(a1)
            v2 = self.val(a2)
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
            v1 = self.val(a1)
            v2 = self.val(a2)
            if op == '<': r = 1 if v1 < v2 else 0
            elif op == '>': r = 1 if v1 > v2 else 0
            elif op == '<=': r = 1 if v1 <= v2 else 0
            elif op == '>=': r = 1 if v1 >= v2 else 0
            elif op == '==': r = 1 if v1 == v2 else 0
            elif op == '!=': r = 1 if v1 != v2 else 0
            self.mem[res] = r
            return True, None

        elif op in ('&&', '||'):
            v1 = self.val(a1)
            v2 = self.val(a2)
            if op == '&&': r = 1 if (v1 and v2) else 0
            elif op == '||': r = 1 if (v1 or v2) else 0
            self.mem[res] = r
            return True, None

        elif op == 'read':
            if self.input_idx < len(self.inputs):
                v = self.inputs[self.input_idx]
                self.input_idx += 1
            else:
                v = 0
            self.mem[res] = v
            return True, None

        elif op == 'write':
            v = self.val(a1)
            self.output.append(str(v))
            return True, None

        elif op == 'writec':
            v = self.val(a1)
            self.output.append(chr(v))
            return True, None

        elif op == '=[]':
            arr = self.arrays.get(a1, {})
            idx = self.val(a2)
            v = arr.get(idx, 0)
            self.mem[res] = v
            return True, None

        elif op == '[]=':
            v = self.val(a1)
            idx = self.val(a2)
            if res not in self.arrays:
                self.arrays[res] = {}
            self.arrays[res][idx] = v
            return True, None

        elif op == 'param':
            v = self.val(a1)
            self.param_stack.append(v)
            return True, None

        elif op == 'call':
            func_name = a1
            num_args = int(a2)
            saved_pc = self.pc + 1
            saved_mem = dict(self.mem)
            saved_arrays = {k: dict(v) for k, v in self.arrays.items()}
            entry, err = self.run_function(func_name)
            if entry >= 0:
                self.pc = entry
                self.return_stack.append((saved_pc, res, saved_mem, saved_arrays))
                return True, 'jumped'
            else:
                if err:
                    self.output.append(err)
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
                self.pc = int(res)
                return True, 'jumped'
            else:
                return True, None

        return True, None

    def _execute_range(self, start, end):
        """Execute quads from start to end (exclusive), handling only simple ops."""
        self.pc = start
        while self.pc < end:
            op, a1, a2, res = self.quads[self.pc]
            cont, _ = self._execute_quad(op, a1, a2, res)
            if not cont:
                break
            if _ != 'jumped':
                self.pc += 1

    def run(self, func_name='main'):
        self.retval = 0
        if func_name in self.func_table and self.func_table[func_name]['entry'] is not None:
            main_entry = self.func_table[func_name]['entry']
        else:
            main_entry = 0

        # Execute global init quads (from 0 to main_entry)
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
            if not cont:
                break
            if jumped != 'jumped':
                self.pc += 1

        return ''.join(self.output)


def ast_to_str(node, indent=0):
    if node is None:
        return 'None'
    lines = []
    t = node['type']
    prefix = '  ' * indent
    ln = node.get('line', 0)

    def ln_tag(line):
        return f'[{line}]' if line else ''

    if t == 'Program':
        lines.append(f"{prefix}Program")
        for s in node['body']:
            lines.append(ast_to_str(s, indent + 1))

    elif t == 'FuncDecl':
        ret = node.get('ret', 'int')
        lines.append(f"{prefix}FunctionDecl({ret} {node['name']}){ln_tag(ln)}")
        for p in node['params']:
            lines.append(f"{prefix}  Param({p['type']} {p['name']})[{p.get('line', 0)}]")

    elif t == 'FuncDef':
        ret = node.get('ret', 'int')
        lines.append(f"{prefix}FunctionDef({ret} {node['name']}){ln_tag(ln)}")
        for p in node['params']:
            lines.append(f"{prefix}  Param({p['type']} {p['name']})[{p.get('line', 0)}]")
        body = node['body']
        lines.append(ast_to_str(body, indent + 1))

    elif t == 'Block':
        lines.append(f"{prefix}Compound")
        for s in node['body']:
            lines.append(ast_to_str(s, indent + 1))

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

    elif t == 'Assign':
        lines.append(f"{prefix}AssignExpr{ln_tag(ln)}")
        lines.append(ast_to_str(node['target'], indent + 1))
        lines.append(ast_to_str(node['expr'], indent + 1))

    elif t == 'If':
        lines.append(f"{prefix}IfStmt")
        lines.append(ast_to_str(node['cond'], indent + 1))
        lines.append(ast_to_str(node['true'], indent + 1))
        if node['false']:
            lines.append(f"{prefix}ElseStmt")
            lines.append(ast_to_str(node['false'], indent + 1))

    elif t == 'While':
        lines.append(f"{prefix}WhileStmt")
        lines.append(ast_to_str(node['cond'], indent + 1))
        lines.append(ast_to_str(node['body'], indent + 1))

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

    elif t == 'DoWhile':
        lines.append(f"{prefix}DoWhileStmt")
        lines.append(ast_to_str(node['body'], indent + 1))
        lines.append(f"{prefix}  Condition")
        lines.append(ast_to_str(node['cond'], indent + 2))

    elif t == 'Break':
        lines.append(f"{prefix}BreakStmt{ln_tag(ln)}")

    elif t == 'Continue':
        lines.append(f"{prefix}ContinueStmt{ln_tag(ln)}")

    elif t == 'Return':
        if node.get('expr'):
            lines.append(f"{prefix}ReturnStmt")
            lines.append(ast_to_str(node['expr'], indent + 1))
        else:
            lines.append(f"{prefix}ReturnStmt")

    elif t == 'Write':
        for a in node['args']:
            lines.append(f"{prefix}ExprStmt")
            lines.append(f"{prefix}  CallExpr(write){ln_tag(ln)}")
            lines.append(ast_to_str(a, indent + 2))

    elif t == 'ExprStmt':
        lines.append(f"{prefix}ExprStmt")
        lines.append(ast_to_str(node['expr'], indent + 1))

    elif t == 'BinOp':
        lines.append(f"{prefix}BinaryExpr({node['op']}){ln_tag(ln)}")
        lines.append(ast_to_str(node['left'], indent + 1))
        lines.append(ast_to_str(node['right'], indent + 1))

    elif t == 'UnaryOp':
        lines.append(f"{prefix}UnaryExpr({node['op']}){ln_tag(ln)}")
        lines.append(ast_to_str(node['operand'], indent + 1))

    elif t == 'PostOp':
        lines.append(f"{prefix}PostExpr({node['op']}){ln_tag(ln)}")
        lines.append(ast_to_str(node['operand'], indent + 1))

    elif t == 'CharVal':
        ch = chr(node['value'])
        esc = repr(ch)[1:-1]
        lines.append(f"{prefix}Literal('{esc}'){ln_tag(ln)}")

    elif t == 'Num':
        lines.append(f"{prefix}Literal({node['value']}){ln_tag(ln)}")

    elif t == 'Var':
        lines.append(f"{prefix}Identifier({node['name']}){ln_tag(ln)}")

    elif t == 'ArrayAccess':
        lines.append(f"{prefix}ArrayAccess{ln_tag(ln)}")
        lines.append(ast_to_str(node['array'], indent + 1))
        lines.append(ast_to_str(node['index'], indent + 1))

    elif t == 'Call':
        func_name = node['func']['name'] if isinstance(node['func'], dict) else '?'
        lines.append(f"{prefix}CallExpr({func_name}){ln_tag(ln)}")
        for a in node['args']:
            lines.append(ast_to_str(a, indent + 1))

    elif t == 'Condition':
        lines.append(f"{prefix}Condition")
        lines.append(ast_to_str(node['cond'], indent + 1))

    else:
        lines.append(f"{prefix}{t}{ln_tag(ln)}")

    return '\n'.join(lines)


def token_code(t):
    val = t.value
    typ = t.type

    if val == 'write':
        return 700

    if typ == 'KEYWORD':
        if val == 'int':
            return 102
        kw_map = {'if': 103, 'else': 104, 'while': 105, 'return': 106, 'void': 107,
                  'for': 108, 'do': 109, 'continue': 110, 'break': 111, 'read': 112}
        if val in kw_map:
            return kw_map[val]
        return 700

    if typ == 'ID':
        return 700

    if typ == 'NUM':
        return 400

    if typ == 'STRING':
        return 500

    if typ == 'OP':
        op_map = {
            '=': 219, '&&': 217, '||': 218,
            '+': 211, '-': 212, '*': 213, '/': 214, '%': 215,
            '<': 216, '>': 220, '<=': 221, '>=': 222, '==': 223, '!=': 224,
            '++': 225, '--': 226
        }
        return op_map.get(val, 0)

    if typ == 'PUNCT':
        punct_map = {
            '(': 201, ')': 202, '{': 301, '}': 302, ';': 303, ',': 304,
            '[': 305, ']': 306
        }
        return punct_map.get(val, 0)

    return 0


def process_32(code, inputs=None):
    try:
        lexer = Lexer(code)
        tokens = lexer.tokenize()

        tokens_str = "===== Token 序列 =====\n" + '\n'.join(
            f"{t.value}\t{token_code(t)}\t{t.line}" for t in tokens
        )

        parser = Parser(tokens)
        ast = parser.parse()

        ast_str = ast_to_str(ast)

        gen = QuadGenerator()
        gen.gen(ast)

        sym_str = '\n'.join(f"{k}: {v}" for k, v in gen.symbols.items())

        quads_str = '\n'.join(f"{i}: ({q[0]}, {q[1]}, {q[2]}, {q[3]})" for i, q in enumerate(gen.quads))

        interp = Interpreter(gen.quads, gen.func_table, inputs)
        output = interp.run()
        retval = interp.retval

        return {
            'source': code,
            'tokens': tokens_str,
            'ast': ast_str,
            'symbol_table': sym_str,
            'quadruples': quads_str,
            'quads_list': gen.quads,
            'func_table': gen.func_table,
            'output': output,
            'retval': retval,
        }
    except Exception as e:
        import traceback
        return {'error': str(e) + '\n' + traceback.format_exc()}
