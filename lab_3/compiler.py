"""A small C subset: PLY lexer -> LALR parser -> AST -> interpreter/Python/HTML."""
import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
import ply.lex as lex
import ply.yacc as yacc

reserved = {w: w.upper() for w in ('int', 'main', 'if', 'else', 'while', 'return', 'void')}
tokens = ['ID', 'NUMBER', 'EQ', 'NE', 'LE', 'GE', 'AND', 'OR'] + list(reserved.values())
literals = '+-*/%(){};=<>!'
t_EQ = r'=='
t_NE = r'!='
t_LE = r'<='
t_GE = r'>='
t_AND = r'&&'
t_OR = r'\|\|'
t_ignore = ' \t\r'

def t_comment(t):
    r'//[^\n]*|/\*[\s\S]*?\*/'
    t.lexer.lineno += t.value.count('\n')

def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)

def t_NUMBER(t):
    r'\d+'
    t.value = int(t.value)
    return t

def t_ID(t):
    r'[a-zA-Z_][a-zA-Z_0-9]*'
    t.type = reserved.get(t.value, 'ID')
    return t

def t_error(t):
    raise SyntaxError(f'Line {t.lineno}: unexpected character {t.value[0]!r}')

def node(kind, *children, value=None):
    return dict(kind=kind, value=value, children=list(children))

precedence = (
    ('nonassoc', 'IFX'), ('nonassoc', 'ELSE'),
    ('left', 'OR'), ('left', 'AND'),
    ('left', 'EQ', 'NE'), ('left', '<', '>', 'LE', 'GE'),
    ('left', '+', '-'), ('left', '*', '/', '%'),
    ('right', 'UMINUS', '!'),
)

def p_program(p):
    '''program : INT MAIN '(' ')' block
               | INT MAIN '(' VOID ')' block'''
    p[0] = node('program', p[len(p)-1])

def p_block(p):
    "block : '{' statements '}'"
    p[0] = node('block', *p[2])

def p_statements(p):
    '''statements : statements statement
                  | empty'''
    p[0] = p[1] + [p[2]] if len(p) == 3 else []

def p_empty(p):
    'empty :'
    p[0] = None

def p_statement_block(p):
    'statement : block'
    p[0] = p[1]

def p_declaration(p):
    '''statement : INT ID '=' expression ';'
                 | INT ID ';' '''
    p[0] = node('declare', p[4] if len(p) == 6 else node('number', value=0), value=p[2])

def p_assignment(p):
    "statement : ID '=' expression ';'"
    p[0] = node('assign', p[3], value=p[1])

def p_return(p):
    "statement : RETURN expression ';'"
    p[0] = node('return', p[2])

def p_if(p):
    "statement : IF '(' expression ')' statement %prec IFX"
    p[0] = node('if', p[3], p[5])

def p_if_else(p):
    "statement : IF '(' expression ')' statement ELSE statement"
    p[0] = node('if', p[3], p[5], p[7])

def p_while(p):
    "statement : WHILE '(' expression ')' statement"
    p[0] = node('while', p[3], p[5])

def p_binary(p):
    '''expression : expression '+' expression
                  | expression '-' expression
                  | expression '*' expression
                  | expression '/' expression
                  | expression '%' expression
                  | expression '<' expression
                  | expression '>' expression
                  | expression LE expression
                  | expression GE expression
                  | expression EQ expression
                  | expression NE expression
                  | expression AND expression
                  | expression OR expression'''
    p[0] = node('binary', p[1], p[3], value=p[2])

def p_unary(p):
    '''expression : '-' expression %prec UMINUS
                  | '!' expression'''
    p[0] = node('unary', p[2], value=p[1])

def p_group(p):
    "expression : '(' expression ')'"
    p[0] = p[2]

def p_number(p):
    'expression : NUMBER'
    p[0] = node('number', value=p[1])

def p_name(p):
    'expression : ID'
    p[0] = node('name', value=p[1])

def p_error(t):
    if t:
        raise SyntaxError(f'Line {t.lineno}: unexpected {t.value!r} ({t.type})')
    raise SyntaxError('Unexpected end of file')

def parse(source, report=False):
    lexer = lex.lex()
    parser = yacc.yacc(start='program', method='LALR', debug=report,
                       debugfile='parser.out', outputdir=str(Path(__file__).parent), write_tables=False)
    return parser.parse(source, lexer=lexer, tracking=True)

def check(tree):
    """Static name checking, including code in branches that never execute."""
    scopes = []
    def visit(n):
        k, v, cs = n['kind'], n['value'], n['children']
        if k in ('program', 'block'):
            scopes.append(set())
            for c in cs: visit(c)
            scopes.pop()
        elif k == 'declare':
            if v in scopes[-1]: raise ValueError(f'Duplicate declaration: {v}')
            visit(cs[0])
            scopes[-1].add(v)
        else:
            if k in ('name', 'assign') and not any(v in s for s in scopes):
                raise ValueError(f'Undeclared variable: {v}')
            # A naked declaration as an if/while body is not a C statement.
            if k in ('if', 'while') and any(c['kind'] == 'declare' for c in cs[1:]):
                raise ValueError('Put declarations in a braced block')
            for c in cs: visit(c)
    visit(tree)

def cdiv(a, b):
    if b == 0: raise ValueError('Division by zero')
    return (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)

class Returned(Exception):
    def __init__(self, value): self.value = value

def run(tree, limit=100000):
    scopes, steps = [], 0
    def scope(name):
        return next(s for s in reversed(scopes) if name in s)
    def ev(n):
        nonlocal steps
        steps += 1
        if steps > limit: raise ValueError('Execution step limit exceeded')
        k, v, c = n['kind'], n['value'], n['children']
        if k in ('program', 'block'):
            scopes.append({})
            try:
                for child in c: ev(child)
            finally: scopes.pop()
        elif k == 'number': return v
        elif k == 'name': return scope(v)[v]
        elif k == 'declare': scopes[-1][v] = ev(c[0])
        elif k == 'assign': scope(v)[v] = ev(c[0])
        elif k == 'return': raise Returned(ev(c[0]))
        elif k == 'if':
            if ev(c[0]): ev(c[1])
            elif len(c) == 3: ev(c[2])
        elif k == 'while':
            while ev(c[0]): ev(c[1])
        elif k == 'unary':
            a = ev(c[0]); return -a if v == '-' else int(not a)
        elif k == 'binary':
            a = ev(c[0])
            if v == '&&': return int(bool(a) and bool(ev(c[1])))
            if v == '||': return int(bool(a) or bool(ev(c[1])))
            b = ev(c[1])
            if v == '/': return cdiv(a, b)
            if v == '%': return a - cdiv(a, b) * b
            return {'+': lambda:a+b, '-':lambda:a-b, '*':lambda:a*b,
                    '<':lambda:int(a<b), '>':lambda:int(a>b), '<=':lambda:int(a<=b),
                    '>=':lambda:int(a>=b), '==':lambda:int(a==b), '!=':lambda:int(a!=b)}[v]()
    try: ev(tree)
    except Returned as r: return r.value
    return 0

def generate(tree):
    """Resolve C block scopes into unique Python variable names."""
    scopes, serial, lines = [], 0, []
    def lookup(v): return next(s[v] for s in reversed(scopes) if v in s)
    def expr(n):
        k, v, c = n['kind'], n['value'], n['children']
        if k == 'number': return str(v)
        if k == 'name': return lookup(v)
        if k == 'unary':
            return f'(-{expr(c[0])})' if v == '-' else f'int(not {expr(c[0])})'
        a, b = expr(c[0]), expr(c[1])
        if v == '/': return f'cdiv({a}, {b})'
        if v == '%': return f'cmod({a}, {b})'
        if v in ('&&', '||'):
            return f'int(bool({a}) {"and" if v == "&&" else "or"} bool({b}))'
        out = f'({a} {v} {b})'
        return f'int({out})' if v in ('<','>','<=','>=','==','!=') else out
    def emit(n, depth):
        nonlocal serial
        k, v, c = n['kind'], n['value'], n['children']
        def line(s): lines.append('    '*depth+s)
        if k in ('program','block'):
            scopes.append({}); before = len(lines)
            for child in c: emit(child, depth)
            if len(lines) == before: line('pass')
            scopes.pop()
        elif k == 'declare':
            rhs = expr(c[0]); serial += 1
            name = f'v_{serial}_{v}'; scopes[-1][v] = name
            line(f'{name} = {rhs}')
        elif k == 'assign': line(f'{lookup(v)} = {expr(c[0])}')
        elif k == 'return': line('return '+expr(c[0]))
        elif k in ('if','while'):
            line(f'{k} {expr(c[0])}:'); emit(c[1], depth+1)
            if len(c) == 3:
                line('else:'); emit(c[2], depth+1)
    emit(tree, 1)
    return ('# Generated from the Mini-C AST. Run with Python 3.\n'
            'def cdiv(a, b):\n'
            '    if b == 0: raise ValueError("Division by zero")\n'
            '    return (abs(a)//abs(b)) * (-1 if (a < 0) != (b < 0) else 1)\n\n'
            'def cmod(a, b):\n    return a - cdiv(a, b)*b\n\n'
            'def main():\n'+'\n'.join(lines)+'\n    return 0\n\n'
            'if __name__ == "__main__":\n    print(main())\n')

def visualize(tree, source):
    template = (Path(__file__).parent / 'ast-viewer.html').read_text(encoding='utf-8')
    payload = json.dumps(dict(tree=tree, source=source), ensure_ascii=True).replace('<', '\\u003c')
    return template.replace('__PAYLOAD__', payload)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--out', type=Path, default=Path('build'))
    ap.add_argument('--report', action='store_true', help='Write LALR states to parser.out')
    args = ap.parse_args()
    try:
        source = args.source.read_text(encoding='utf-8')
        tree = parse(source, args.report)
        check(tree)
        result = run(tree)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out/'ast.json').write_text(json.dumps(tree, indent=2), encoding='utf-8')
        (args.out/'generated.py').write_text(generate(tree), encoding='utf-8')
        (args.out/'ast.html').write_text(visualize(tree, source), encoding='utf-8')
        print(f'Syntax and semantics: OK\nResult: {result}\nArtifacts: {args.out}')
    except (SyntaxError, ValueError, OSError) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
